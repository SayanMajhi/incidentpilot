import itertools
import os
from datetime import datetime, timezone

from backend.agent.decision import collect_evidence, decision_engine, find_failed_attempt
from backend.agent.llm_decision import llm_decision_engine
from backend.safety.policy import policy
from backend.infrastructure import get_infrastructure
from backend.verification.verifier import verifier


MAX_ATTEMPTS = 3

# Independent fresh telemetry samples taken after every action. Recovery is
# only confirmed when every one of them is healthy.
VERIFICATION_SAMPLES = 3


class IncidentController:
    MAX_ATTEMPTS = MAX_ATTEMPTS
    VERIFICATION_SAMPLES = VERIFICATION_SAMPLES

    def __init__(
            self,
            use_llm=None,
            llm_engine=None,
            deterministic_engine=None,
            infrastructure=None,
    ):
        if use_llm is None:
            use_llm = (
                    os.getenv(
                        "LLM_ENABLED",
                        "false",
                    ).lower()
                    == "true"
            )

        self.use_llm = use_llm

        self.llm_engine = (
            llm_engine
            if llm_engine is not None
            else llm_decision_engine
        )

        self.deterministic_engine = (
            deterministic_engine
            if deterministic_engine is not None
            else decision_engine
        )

        # The execution environment this controller observes and acts on,
        # chosen by configuration. The controller never knows which one it is.
        self._infrastructure = infrastructure

        self._observation_ids = itertools.count(1)

    @property
    def infrastructure(self):
        if self._infrastructure is None:
            self._infrastructure = get_infrastructure()
        return self._infrastructure

    # ---------------------------------------------------------
    # OBSERVE
    # ---------------------------------------------------------

    def observe(self):
        """
        Collect a fresh telemetry snapshot of the service.

        Every call reads the live environment again and is stamped with a new,
        monotonically increasing ``observation_id``, so the audit trail shows
        that each attempt reasoned over its own observation rather than a
        cached one.
        """
        return {
            "observation_id": next(self._observation_ids),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "metrics": self.infrastructure.get_metrics(),
            "health": self.infrastructure.check_health(),
            "current_version": self.infrastructure.get_current_version(),
            "capacity": self.infrastructure.get_capacity(),
        }

    # ---------------------------------------------------------
    # INVESTIGATE
    # ---------------------------------------------------------

    def investigate(self, observation=None):
        """
        Gather diagnostic evidence on top of a telemetry snapshot.

        Queries logs and deployment history, then extracts discrete evidence
        items from everything observed. When no snapshot is supplied a fresh
        one is taken first.
        """
        observations = dict(observation) if observation is not None else self.observe()

        observations["logs"] = self.infrastructure.query_logs()
        observations["deployment_history"] = self.infrastructure.get_deployment_history()
        observations["evidence"] = collect_evidence(observations)

        return observations

    # ---------------------------------------------------------
    # DIAGNOSE
    # ---------------------------------------------------------

    def diagnose(self, observations):
        """
        Rank the causes the evidence supports, before any action is chosen.

        Hypotheses whose remediation already failed verification during this
        run are ruled out, which is what makes a re-diagnosis after a failed
        attempt differ from the first one when - and only when - the fresh
        evidence supports something else.
        """
        diagnose = getattr(self.deterministic_engine, "diagnose", None)
        if diagnose is None:
            return {
                "probable_cause": "undetermined",
                "summary": "The configured decision engine does not produce a diagnosis.",
                "confidence": 0,
                "hypotheses": [],
                "evidence": observations.get("evidence", []),
            }
        return diagnose(observations)

    # ---------------------------------------------------------
    # DECIDE
    # ---------------------------------------------------------

    def decide(self, observations, diagnosis=None):
        """
        Decide what to do next.

        Architecture:

            Observation
                ↓
            Evidence + diagnosis
                ↓
            Deterministic proposal
                ↓
            LLM proposal (optional)
                ↓
            Arbitration
                ↓
            Final decision

        The LLM proposes actions, but deterministic evidence can
        override the proposal when there is strong evidence for a
        safer/more appropriate remediation.

        This prevents the LLM from becoming the sole authority for
        remediation decisions.
        """

        # -----------------------------------------------------
        # HEALTHY SERVICE
        # -----------------------------------------------------

        metrics = observations.get("metrics", {})

        if (
                metrics.get("status") == "healthy"
                and metrics.get("error_rate", 1.0)
                <= verifier.MAX_ERROR_RATE
                and metrics.get("latency_ms", 999999)
                <= verifier.MAX_LATENCY_MS
        ):
            return {
                "action": "escalate",
                "target": None,
                "parameters": {},
                "reason": (
                    "The service is currently healthy. "
                    "No remediation is required."
                ),
                "confidence": 1.0,
                "diagnosis": "no_active_incident",
                "evidence": [],
                "source": "deterministic_health_check",
            }

        deterministic_decision = self._deterministic_decision(
            observations,
            diagnosis,
        )

        # -----------------------------------------------------
        # DETERMINISTIC MODE
        # -----------------------------------------------------

        if not self.use_llm:
            deterministic_decision["source"] = "deterministic"
            return deterministic_decision

        # -----------------------------------------------------
        # TRY QWEN
        # -----------------------------------------------------

        llm_decision = self.llm_engine.decide(
            observations
        )

        # -----------------------------------------------------
        # LLM SUCCESS
        # -----------------------------------------------------

        if (
                getattr(
                    self.llm_engine,
                    "last_status",
                    None,
                )
                == "success"
        ):
            llm_decision = dict(llm_decision)

            # -------------------------------------------------
            # DETERMINISTIC ARBITRATION
            # -------------------------------------------------
            #
            # The model remains advisory. When its action conflicts
            # with the deterministic interpretation of the same
            # observed evidence, prefer the evidence-backed action.
            # -------------------------------------------------

            deterministic_action = deterministic_decision.get("action")
            llm_action = llm_decision.get("action")

            if deterministic_action != llm_action:
                deterministic_decision["source"] = "deterministic_arbitration"
                deterministic_decision["llm_proposal"] = llm_decision
                deterministic_decision["arbitration_reason"] = (
                    "The model proposal conflicted with the action supported "
                    "by deterministic evidence, so the evidence-backed "
                    "action was selected."
                )
                return deterministic_decision

            # -------------------------------------------------
            # A proposal that repeats a remediation which already
            # failed verification in this run is never accepted.
            # -------------------------------------------------

            failed = find_failed_attempt(
                llm_action,
                llm_decision.get("target"),
                observations.get("attempt_history", []) or [],
            )
            if failed is not None and llm_action != "escalate":
                deterministic_decision["source"] = "deterministic_arbitration"
                deterministic_decision["llm_proposal"] = llm_decision
                deterministic_decision["arbitration_reason"] = (
                    "The model proposed a remediation that already failed "
                    "verification in this run, so the evidence-backed "
                    "action was selected."
                )
                return deterministic_decision

            # -------------------------------------------------
            # OTHERWISE ACCEPT THE LLM PROPOSAL
            # -------------------------------------------------

            llm_decision.setdefault("parameters", {})
            llm_decision["diagnosis"] = deterministic_decision.get("diagnosis")
            llm_decision["evidence"] = deterministic_decision.get("evidence", [])
            llm_decision["source"] = "llm"

            return llm_decision

        # -----------------------------------------------------
        # QWEN FAILED → DETERMINISTIC FALLBACK
        # -----------------------------------------------------

        fallback = deterministic_decision

        fallback["source"] = (
            "deterministic_fallback"
        )

        fallback["fallback_reason"] = getattr(
            self.llm_engine,
            "last_error",
            "Unknown LLM failure",
        )

        return fallback

    def _deterministic_decision(self, observations, diagnosis):
        if diagnosis is not None:
            try:
                decision = self.deterministic_engine.decide(observations, diagnosis)
            except TypeError:
                decision = self.deterministic_engine.decide(observations)
        else:
            decision = self.deterministic_engine.decide(observations)

        decision = dict(decision)
        decision.setdefault("parameters", {})
        decision.setdefault("evidence", [])
        return decision

    # ---------------------------------------------------------
    # SAFETY
    # ---------------------------------------------------------

    @staticmethod
    def check_safety(decision):
        """
        Evaluate a proposed remediation against the deterministic policy.

        Runs for every proposed action, on every attempt, before anything is
        executed. Escalation mutates nothing, so it needs no check.
        """
        action = decision.get("action")
        target = decision.get("target")

        if action == "escalate":
            return {
                "action": "escalate",
                "checked": False,
                "allowed": None,
            }

        if action == "rollback_deployment":
            allowed = policy.allows("rollback_deployment", version=target)
        elif action == "scale_service":
            allowed = policy.allows("scale_service", replicas=target)
        else:
            # Restart takes no arguments; anything unknown is denied by the
            # policy's allow-list.
            allowed = policy.allows(action)

        return {
            "action": action,
            "checked": True,
            "allowed": bool(allowed),
        }

    # ---------------------------------------------------------
    # SAFETY + ACT
    # ---------------------------------------------------------

    def execute(self, decision, safety_result=None):
        """
        Execute an approved decision.

        The LLM never directly executes an action.

        Every remediation must pass through the deterministic
        safety policy before execution. A caller that has already run
        :meth:`check_safety` passes its verdict in, so the policy is
        evaluated exactly once per action.
        """

        action = decision["action"]
        target = decision.get("target")

        # -----------------------------------------------------
        # ESCALATION
        # -----------------------------------------------------

        if action == "escalate":
            return {
                "action": "escalate",
                "success": True,
                "status": "escalated",
                "message": decision["reason"],
            }

        # -----------------------------------------------------
        # SAFETY CHECK
        # -----------------------------------------------------

        if safety_result is None:
            safety_result = self.check_safety(decision)

        # -----------------------------------------------------
        # BLOCK UNSAFE ACTION
        # -----------------------------------------------------

        if not safety_result.get("allowed"):
            return {
                "action": action,
                "success": False,
                "status": "blocked",
                "policy_allowed": False,
                "message": (
                    "Action blocked by safety policy."
                ),
            }

        # -----------------------------------------------------
        # EXECUTE APPROVED ACTION
        # -----------------------------------------------------

        if action == "rollback_deployment":
            result = self.infrastructure.rollback_deployment(
                target
            )

        elif action == "scale_service":
            result = self.infrastructure.scale_service(
                target
            )

        elif action == "restart_service":
            result = self.infrastructure.restart_service()

        else:
            return {
                "action": action,
                "success": False,
                "status": "unsupported",
                "policy_allowed": False,
                "message": "Unsupported action.",
            }

        # The policy approved this action, so record that verdict
        # alongside whatever the executor reported. The two are
        # deliberately separate: an approved action can still fail.
        return {**result, "policy_allowed": True}

    # ---------------------------------------------------------
    # VERIFY
    # ---------------------------------------------------------

    def verify(self):
        """
        Verify the current service state using fresh telemetry.

        IMPORTANT:
        Successful execution of an action does NOT mean that the
        incident has been resolved. Several independent samples are read
        after the action, together with the health check, and every one of
        them must be healthy.
        """

        samples = [
            self.infrastructure.get_metrics()
            for _ in range(self.VERIFICATION_SAMPLES)
        ]
        health = self.infrastructure.check_health()

        result = verifier.verify_sustained(samples)

        if result.recovered and not health.get("is_healthy", False):
            result.recovered = False
            result.reason = "Health check still reports the service as unhealthy"

        result.telemetry = {
            "metrics": samples[-1],
            "health": health,
            "samples": len(samples),
        }

        return result

    # ---------------------------------------------------------
    # FULL INCIDENT LOOP
    # ---------------------------------------------------------

    def run_incident(self, on_event=None):
        """
        Run the autonomous incident-response loop.

        Observe
            ↓
        Detect
            ↓
        Investigate
            ↓
        Diagnose
            ↓
        Decide
            ↓
        Safety
            ↓
        Act
            ↓
        Verify (fresh telemetry)
            ↓
        Adapt: record the failed attempt, then observe again

        Nothing about the next attempt is decided when an attempt fails. The
        failure is recorded, and the next iteration starts from a completely
        fresh observation; whatever it decides follows from that new
        evidence, with already-failed remediations ruled out.
        """

        history = []
        evidence_history = []
        seen_evidence = set()

        status = "unresolved"

        observations = None
        decision = None
        action_result = None
        verification = None

        def emit(phase, **details):
            if on_event is not None:
                on_event(phase, details)

        for attempt_number in range(
                1,
                self.MAX_ATTEMPTS + 1,
        ):

            # ================================================
            # OBSERVE + DETECT
            # ================================================

            emit("observing", attempt=attempt_number)
            observation = self.observe()
            detection = self.detect(observation)

            # ================================================
            # INVESTIGATE
            # ================================================

            emit("investigating", attempt=attempt_number, detection=detection)
            observations = self.investigate(observation)
            observations["attempt_history"] = [
                dict(entry) for entry in evidence_history
            ]
            if evidence_history:
                # Kept for consumers of the original single-attempt field.
                observations["previous_attempt"] = dict(evidence_history[-1])

            evidence_ids = [item["id"] for item in observations["evidence"]]
            new_evidence = [
                item_id for item_id in evidence_ids if item_id not in seen_evidence
            ]

            if history:
                # What the previous action left behind is exactly what this
                # re-investigation found.
                history[-1]["evidence_after_action"] = list(observations["evidence"])
                history[-1]["new_evidence_after_action"] = list(new_evidence)
                evidence_history[-1]["evidence_after_action"] = list(evidence_ids)
                evidence_history[-1]["new_evidence_after_action"] = list(new_evidence)

            seen_evidence.update(evidence_ids)

            # ================================================
            # DIAGNOSE
            # ================================================

            emit("diagnosing", attempt=attempt_number)
            diagnosis = self.diagnose(observations)

            # ================================================
            # DECIDE
            # ================================================

            emit("deciding", attempt=attempt_number, diagnosis=self._summary(diagnosis))
            decision = dict(self.decide(observations, diagnosis))
            decision.setdefault("parameters", {})
            decision.setdefault("evidence", [])

            # ================================================
            # ESCALATION
            # ================================================

            if decision["action"] == "escalate":
                safety_result = self.check_safety(decision)
                action_result = self.execute(decision)
                verification = None
                status = "escalated"

                history.append(
                    self._record_attempt(
                        attempt_number,
                        observations,
                        detection,
                        diagnosis,
                        decision,
                        safety_result,
                        action_result,
                        verification,
                        new_evidence,
                    )
                )
                evidence_history.append(
                    self._summarize_attempt(history[-1])
                )

                break

            # ================================================
            # SAFETY CHECK
            # ================================================

            # The verdict comes from the deterministic policy gate itself,
            # not from the action's outcome string - an approved action that
            # then fails to execute must not be reported as "blocked", and a
            # blocked action must never be reported as allowed.
            emit("checking_safety", attempt=attempt_number, action=decision.get("action"))
            safety_result = self.check_safety(decision)

            # ================================================
            # ACT (or block)
            # ================================================

            if safety_result["allowed"]:
                emit("executing", attempt=attempt_number, action=decision.get("action"))

            action_result = self.execute(decision, safety_result=safety_result)

            if not safety_result["allowed"]:

                verification = None

                status = "blocked"

                history.append(
                    self._record_attempt(
                        attempt_number,
                        observations,
                        detection,
                        diagnosis,
                        decision,
                        safety_result,
                        action_result,
                        verification,
                        new_evidence,
                    )
                )
                evidence_history.append(
                    self._summarize_attempt(history[-1])
                )

                break

            # ================================================
            # VERIFY
            # ================================================

            emit("verifying", attempt=attempt_number, action_result=action_result)
            verification = self.verify()

            history.append(
                self._record_attempt(
                    attempt_number,
                    observations,
                    detection,
                    diagnosis,
                    decision,
                    safety_result,
                    action_result,
                    verification,
                    new_evidence,
                )
            )
            evidence_history.append(
                self._summarize_attempt(history[-1])
            )

            # ================================================
            # SUCCESS
            # ================================================

            if verification.recovered:
                status = "resolved"
                break

            # ================================================
            # ADAPT
            # ================================================

            status = "unresolved"
            emit(
                "adapting",
                attempt=attempt_number,
                previous_attempt=evidence_history[-1],
            )

            # The next iteration observes again from scratch. It does not
            # know - and is not told - what to do next.

        # ================================================
        # FINAL RESULT
        # ================================================

        emit("complete", status=status, attempts=len(history))
        return {
            "attempts": history,
            "evidence_history": evidence_history,
            "observations": observations,
            "decision": decision,
            "action_result": action_result,
            "verification": verification,
            "status": status,
        }

    @staticmethod
    def detect(observations):
        """Classify whether fresh telemetry represents an active incident."""
        metrics = observations.get("metrics", {})
        health = observations.get("health", {})
        signals = []
        if health.get("status") != "healthy":
            signals.append("health_check_failed")
        if metrics.get("error_rate", 0) > verifier.MAX_ERROR_RATE:
            signals.append("error_rate_breach")
        if metrics.get("latency_ms", 0) > verifier.MAX_LATENCY_MS:
            signals.append("latency_slo_breach")
        return {
            "incident_detected": bool(signals),
            "signals": signals,
        }

    @staticmethod
    def _summary(diagnosis):
        return {
            "probable_cause": diagnosis.get("probable_cause"),
            "confidence": diagnosis.get("confidence"),
        }

    # ---------------------------------------------------------
    # HISTORY
    # ---------------------------------------------------------

    @staticmethod
    def _record_attempt(
            attempt_number,
            observations,
            detection,
            diagnosis,
            decision,
            safety_result,
            action_result,
            verification,
            new_evidence=None,
    ):
        """
        Store a complete audit record for one attempt.
        """

        return {
            "attempt": attempt_number,
            "observations": observations,
            "detection": detection,
            "evidence": observations.get("evidence", []),
            "new_evidence": list(new_evidence or []),
            "diagnosis": diagnosis,
            "decision": decision,
            "safety_result": safety_result,
            "action_result": action_result,
            "verification": verification,
            "evidence_after_action": None,
            "new_evidence_after_action": None,
        }

    @staticmethod
    def _summarize_attempt(record):
        """
        Compact evidence-history entry for one attempt.

        This is what the next diagnosis sees about earlier attempts: what was
        believed, what was done, whether the action ran, and whether fresh
        telemetry confirmed recovery. It carries no instruction about what to
        try next.
        """
        decision = record["decision"]
        action_result = record["action_result"] or {}
        verification = record["verification"]

        return {
            "attempt": record["attempt"],
            "diagnosis": record["diagnosis"].get("probable_cause"),
            "action": decision.get("action"),
            "target": decision.get("target"),
            "evidence": [item["id"] for item in record["evidence"]],
            "action_status": action_result.get("status"),
            "action_success": action_result.get("success"),
            "policy_allowed": record["safety_result"].get("allowed"),
            "verification_recovered": (
                verification.recovered if verification is not None else None
            ),
            "verification_reason": (
                verification.reason if verification is not None else None
            ),
            "evidence_after_action": None,
            "new_evidence_after_action": None,
        }


controller = IncidentController()
