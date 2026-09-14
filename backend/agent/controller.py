import itertools
import time
from datetime import datetime, timezone
from uuid import uuid4

from backend.agent.decision import collect_evidence, decision_engine, find_failed_attempt
from backend.agent.llm_decision import llm_decision_engine
from backend.config import get_settings
from backend.safety.policy import SafetyPolicy, policy
from backend.infrastructure import InfrastructureError, get_infrastructure
from backend.models import (
    AgentPhase,
    AttemptRecord,
    IncidentRun,
    IncidentStatus,
    TimelineEvent,
    VerificationCheck,
    VerificationResult,
    VerificationStatus,
)
from backend.verification.verifier import Verifier, verifier


DEFAULT_GOAL = "Restore the service to configured SLOs while respecting safety constraints."
MAX_ATTEMPTS_REASON = "Maximum remediation attempts exhausted"


class IncidentController:
    """Bounded observe, diagnose, act and verify loop for one incident.

    Every instance reads its own budget from settings, so ``MAX_ATTEMPTS`` and
    ``VERIFICATION_SAMPLES`` are instance attributes set in ``__init__``.
    """

    def __init__(
            self,
            use_llm=None,
            llm_engine=None,
            deterministic_engine=None,
        infrastructure=None,
        verification_interval_seconds=None,
        sleep_func=None,
        settings=None,
    ):
        supplied_settings = settings
        self.settings = settings or get_settings()
        self.safety_policy = policy if supplied_settings is None else SafetyPolicy(self.settings)
        self.verification_engine = verifier if supplied_settings is None else Verifier(self.settings)
        if use_llm is None:
            use_llm = self.settings.llm_enabled

        self.use_llm = use_llm
        self.llm_engine = llm_engine if llm_engine is not None else llm_decision_engine
        self.deterministic_engine = (
            deterministic_engine
            if deterministic_engine is not None
            else decision_engine
        )
        self._infrastructure = infrastructure
        self._observation_ids = itertools.count(1)
        self.MAX_ATTEMPTS = self.settings.max_attempts
        self.VERIFICATION_SAMPLES = self.settings.verification_samples
        if verification_interval_seconds is None:
            verification_interval_seconds = self.settings.verification_interval_seconds
        self.verification_interval_seconds = float(verification_interval_seconds)
        if self.verification_interval_seconds < 0:
            raise ValueError("VERIFICATION_INTERVAL_SECONDS cannot be negative")
        self._sleep = sleep_func or time.sleep

    @property
    def infrastructure(self):
        if self._infrastructure is None:
            self._infrastructure = get_infrastructure()
        return self._infrastructure

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

    def decide(self, observations, diagnosis=None):
        """Choose an action, treating an optional LLM as advisory only."""
        metrics = observations.get("metrics", {})

        if (
                metrics.get("status") == "healthy"
                and metrics.get("error_rate", 1.0)
                <= self.settings.recovery_max_error_rate
                and metrics.get("latency_ms", 999999)
                <= self.settings.recovery_max_latency_ms
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

        if not self.use_llm:
            deterministic_decision["source"] = "deterministic"
            return deterministic_decision

        llm_decision = self.llm_engine.decide(observations)

        if getattr(self.llm_engine, "last_status", None) == "success":
            llm_decision = dict(llm_decision)

            # Where the model's action conflicts with the deterministic
            # reading of the same evidence, the evidence wins.
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
                deterministic_decision["deterministic_validation"] = {
                    "status": "rejected",
                    "reason": deterministic_decision["arbitration_reason"],
                }
                return deterministic_decision

            # A remediation that already failed verification in this run is
            # never repeated.
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
                deterministic_decision["deterministic_validation"] = {
                    "status": "rejected",
                    "reason": deterministic_decision["arbitration_reason"],
                }
                return deterministic_decision

            # The actions agree. The target still comes from the evidence,
            # because a matching action name is not agreement on a replica
            # count or a rollback version.
            deterministic_target = deterministic_decision.get("target")
            llm_target = llm_decision.get("target")

            llm_decision.setdefault("parameters", {})
            llm_decision["target"] = deterministic_target
            llm_decision["diagnosis"] = deterministic_decision.get("diagnosis")
            llm_decision["evidence"] = deterministic_decision.get("evidence", [])
            llm_decision["source"] = "llm"
            llm_decision["deterministic_validation"] = {
                "status": "accepted",
                "reason": "The proposal matched the action supported by deterministic evidence.",
            }
            if llm_target != deterministic_target:
                llm_decision["proposed_target"] = llm_target
                llm_decision["deterministic_validation"] = {
                    "status": "accepted_with_corrected_target",
                    "reason": (
                        f"The proposed action was supported, but its target "
                        f"{llm_target!r} was replaced with the evidence-derived "
                        f"target {deterministic_target!r}."
                    ),
                }

            return llm_decision

        fallback = deterministic_decision
        fallback["source"] = "deterministic_fallback"
        fallback["fallback_reason"] = getattr(
            self.llm_engine,
            "last_error",
            "Unknown LLM failure",
        )

        return fallback

    def _deterministic_decision(self, observations, diagnosis):
        decision = dict(self.deterministic_engine.decide(observations, diagnosis))
        decision.setdefault("parameters", {})
        decision.setdefault("evidence", [])
        return decision

    def check_safety(self, decision, *, attempt=1, observations=None):
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
                "target": target,
                "namespace": self.safety_policy.ALLOWED_NAMESPACE,
                "checked": False,
                "allowed": None,
                "rule_id": "non_mutating_controller_decision",
                "reason": "Escalation does not execute an infrastructure action.",
                "bounds": {
                    "min_replicas": self.safety_policy.MIN_REPLICAS,
                    "max_replicas": self.safety_policy.MAX_REPLICAS,
                },
                "budget": {
                    "attempt": max(1, attempt),
                    "maximum": self.MAX_ATTEMPTS,
                    "remaining_after_this_attempt": max(self.MAX_ATTEMPTS - attempt, 0),
                },
                "context": {},
            }

        namespace = self.safety_policy.ALLOWED_NAMESPACE
        # ``None`` means "history could not be read", which the policy treats
        # differently from an empty history: an unreachable environment must
        # not be reported as a rollback to an unknown version.
        history = None
        current_version = None
        if observations:
            history = observations.get("deployment_history")
            current_version = observations.get("current_version")
        elif action == "rollback_deployment":
            # Direct ``execute`` callers get the same checks as the full loop.
            try:
                history = self.infrastructure.get_deployment_history()
                current_version = self.infrastructure.get_current_version()
            except InfrastructureError:
                history = None

        decision = self.safety_policy.evaluate(
            action,
            target=target,
            namespace=namespace,
            replicas=target if action == "scale_service" else None,
            version=target if action == "rollback_deployment" else None,
            attempt=attempt,
            max_attempts=self.MAX_ATTEMPTS,
            deployment_history=history,
            current_version=current_version,
        )
        return decision.to_dict()

    def execute(self, decision, safety_result=None):
        """Execute an approved decision.

        Every remediation passes through the deterministic safety policy
        first. A caller that has already run :meth:`check_safety` passes its
        verdict in, so the policy is evaluated exactly once per action.
        """
        action = decision["action"]
        target = decision.get("target")

        if action == "escalate":
            return {
                "action": "escalate",
                "success": True,
                "status": "escalated",
                "message": decision["reason"],
            }

        if safety_result is None:
            safety_result = self.check_safety(decision)

        if not safety_result.get("allowed"):
            return {
                "action": action,
                "target": target,
                "success": False,
                "status": "blocked",
                "policy_allowed": False,
                "message": safety_result.get(
                    "reason",
                    "Action blocked by safety policy.",
                ),
            }

        if action == "rollback_deployment":
            result = self.infrastructure.rollback_deployment(target)
        elif action == "scale_service":
            result = self.infrastructure.scale_service(target)
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

        # The policy verdict and the execution result stay separate fields:
        # an approved action can still fail.
        result = {**result, "policy_allowed": True}

        # Some backends accept a Deployment patch before the replacement Pods
        # are ready. Give asynchronous reconciliation a bounded chance to
        # settle before the verifier reads fresh telemetry.
        if result.get("success"):
            reconciliation = self.infrastructure.wait_for_reconciliation(result)
            if reconciliation is not None:
                result["reconciliation"] = reconciliation

        return result

    def verify(self, metrics_before=None):
        """Verify the current service state from fresh telemetry.

        A successful action is not a resolved incident. Several independent
        samples are read after the action, together with the health check,
        and every one of them must be healthy.
        """
        samples = []
        for sample_number in range(self.VERIFICATION_SAMPLES):
            if sample_number and self.verification_interval_seconds:
                self._sleep(self.verification_interval_seconds)
            samples.append(self.infrastructure.get_metrics())
        health = self.infrastructure.check_health()
        capacity = self.infrastructure.get_capacity()

        result = self.verification_engine.verify_sustained(
            samples,
            health=health,
            capacity=capacity,
            metrics_before=metrics_before,
        )

        result.metrics_after = {
            **samples[-1],
            "replicas": capacity.get("replicas"),
            "ready_replicas": capacity.get("ready_replicas"),
        }
        result.telemetry = {
            "metrics": samples[-1],
            "health": health,
            "capacity": capacity,
            "samples": len(samples),
        }

        return result

    def detect(self, observations):
        """Classify whether fresh telemetry represents an active incident."""
        metrics = observations.get("metrics", {})
        health = observations.get("health", {})
        signals = []
        if health.get("status") != "healthy":
            signals.append("health_check_failed")
        if metrics.get("error_rate", 0) > self.settings.recovery_max_error_rate:
            signals.append("error_rate_breach")
        if metrics.get("latency_ms", 0) > self.settings.recovery_max_latency_ms:
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
        """Store the audit record for one attempt."""
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

    def run_incident(
        self,
        on_event=None,
        run_id=None,
        goal=DEFAULT_GOAL,
        started_at=None,
    ):
        """Run a validated, observable, and bounded response loop.

        Timeline events belong to the run itself. ``on_event`` is merely a
        live projection hook; omitting it never changes the audit history.
        """

        run_id = run_id or f"inc-{uuid4().hex}"
        started_at = started_at or datetime.now(timezone.utc).isoformat()
        run = IncidentRun(
            incident_id=run_id,
            goal=goal,
            started_at=started_at,
            status=IncidentStatus.RUNNING,
            phase=AgentPhase.IDLE,
            max_attempts=self.MAX_ATTEMPTS,
        )
        history = []
        evidence_history = []
        seen_evidence = set()
        detected_once = False
        infrastructure_failures = 0
        inconclusive_rechecks = 0

        observations = None
        decision = None
        action_result = None
        verification = None
        reason = None

        def event_data(value):
            if hasattr(value, "to_dict"):
                return value.to_dict()
            if isinstance(value, dict):
                return {key: event_data(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [event_data(item) for item in value]
            return value

        def emit(phase, event_type, message, *, attempt=None, data=None, status=None):
            phase = phase if isinstance(phase, AgentPhase) else AgentPhase(phase)
            if status is not None:
                run.status = status if isinstance(status, IncidentStatus) else IncidentStatus(status)
            run.phase = phase
            if attempt is not None:
                run.attempt = max(0, int(attempt))
            timeline_event = TimelineEvent(
                incident_id=run_id,
                attempt=run.attempt if attempt is None else attempt,
                phase=phase,
                event_type=event_type,
                message=message,
                data=event_data(data or {}),
            )
            run.timeline.append(timeline_event)
            run.revision += 1
            if on_event is not None:
                on_event(
                    phase.value,
                    {
                        "run_id": run_id,
                        "goal": goal,
                        "started_at": started_at,
                        "status": run.status.value,
                        "attempt": run.attempt,
                        "reason": run.reason,
                        "history": history,
                        "event": timeline_event.to_dict(),
                    },
                )
            return timeline_event

        def record_attempt(
            attempt_number,
            current_observations,
            detection,
            current_diagnosis,
            current_decision,
            safety_result,
            current_action_result,
            current_verification,
            new_evidence,
        ):
            record = self._record_attempt(
                attempt_number,
                current_observations,
                detection,
                current_diagnosis,
                current_decision,
                safety_result,
                current_action_result,
                current_verification,
                new_evidence,
            )
            # Validate the production record before it becomes persistent run
            # state, while retaining VerificationResult objects for callers of
            # the Python controller API.
            validated = AttemptRecord.model_validate(event_data(record))
            history.append(record)
            run.attempts.append(validated)
            evidence_history.append(self._summarize_attempt(record))
            run.attempt = len(history)
            if current_verification is not None:
                run.verification_results.append(current_verification)
            return record

        def failed_verification(message, *, before=None):
            return VerificationResult(
                status=VerificationStatus.FAILED,
                recovered=False,
                reason=message,
                checks=[
                    VerificationCheck(
                        name="telemetry_available",
                        passed=False,
                        observed=False,
                        expected=True,
                        message=message,
                    )
                ],
                samples=[],
                sample_count=0,
                metrics_before=before,
                metrics_after=None,
                telemetry={"error": message},
            )

        def finish(status, terminal_reason):
            run.status = status if isinstance(status, IncidentStatus) else IncidentStatus(status)
            run.reason = terminal_reason
            run.outcome = run.status.value
            run.completed_at = datetime.now(timezone.utc)
            emit(
                AgentPhase.COMPLETE,
                "run_completed",
                f"Incident run completed with status {run.status.value}.",
                attempt=len(history),
                data={"status": run.status.value, "reason": terminal_reason},
            )
            validated = run.to_dict()
            # The flattened fields below mirror the latest attempt so the API
            # and the dashboard can read a run without walking the history.
            return {
                **validated,
                "run_id": run_id,
                "incident_id": run_id,
                "phase": "complete",
                "attempt": len(history),
                "history": history,
                "attempts": history,
                "evidence_history": evidence_history,
                "timeline": [item.to_dict() for item in run.timeline],
                "trace_events": [item.to_dict() for item in run.timeline],
                "observations": observations,
                "decision": decision,
                "action_result": action_result,
                "verification": verification,
                "status": run.status.value,
                "reason": terminal_reason,
            }

        emit(
            AgentPhase.OBSERVING,
            "run_started",
            "Incident response started; collecting a fresh service snapshot.",
            attempt=0,
        )

        observation = None
        detection = {"incident_detected": False, "signals": []}

        while len(history) < self.MAX_ATTEMPTS:
            next_attempt = len(history) + 1
            if observation is None:
                emit(
                    AgentPhase.OBSERVING,
                    "observation_started",
                    "Reading fresh metrics, health, version, and capacity.",
                    attempt=next_attempt,
                )
                try:
                    observation = self.observe()
                except InfrastructureError as error:
                    infrastructure_failures += 1
                    reason = f"Observation failed: {error}"
                    emit(
                        AgentPhase.REPLANNING,
                        "tool_error",
                        reason,
                        attempt=len(history),
                        data={"tool": "observe", "error_type": type(error).__name__},
                    )
                    if infrastructure_failures >= self.MAX_ATTEMPTS:
                        break
                    continue

                detection = self.detect(observation)
                run.telemetry = dict(observation)
                run.symptoms = list(detection["signals"])
                emit(
                    AgentPhase.OBSERVING,
                    "observation_collected",
                    "Fresh service state collected.",
                    attempt=next_attempt,
                    data={"observation": observation, "detection": detection},
                )

                if not detection["incident_detected"]:
                    if not detected_once:
                        reason = "Service is within configured recovery SLOs; no action is required."
                        emit(
                            AgentPhase.COMPLETE,
                            "no_incident",
                            reason,
                            attempt=0,
                            status=IncidentStatus.NO_INCIDENT,
                            data={"detection": detection},
                        )
                        return finish(IncidentStatus.NO_INCIDENT, reason)

                    # The incident disappeared between attempts. One healthy
                    # observation is not recovery proof, so verify instead.
                    emit(
                        AgentPhase.VERIFYING,
                        "verification_started",
                        "Service looks healthy; confirming sustained recovery.",
                        attempt=len(history),
                    )
                    try:
                        verification = self.verify(
                            metrics_before=dict(observation.get("metrics", {}))
                        )
                    except InfrastructureError as error:
                        verification = failed_verification(
                            f"Verification telemetry unavailable: {error}",
                            before=observation.get("metrics"),
                        )
                    if verification.recovered:
                        reason = verification.reason
                        emit(
                            AgentPhase.RESOLVED,
                            "incident_resolved",
                            reason,
                            attempt=len(history),
                            status=IncidentStatus.RESOLVED,
                            data={"verification": verification},
                        )
                        return finish(IncidentStatus.RESOLVED, reason)

                    # Detection and verification disagree: the incident
                    # boundary is clear but sustained recovery is not
                    # confirmed. Re-observe, but spend budget doing it so the
                    # loop cannot circle here indefinitely.
                    inconclusive_rechecks += 1
                    emit(
                        AgentPhase.REPLANNING,
                        "verification_inconclusive",
                        (
                            "Telemetry is inside the incident boundary but "
                            "recovery is not yet sustained; observing again."
                        ),
                        attempt=len(history),
                        data={
                            "verification": verification,
                            "rechecks": inconclusive_rechecks,
                            "maximum_rechecks": self.MAX_ATTEMPTS,
                        },
                    )
                    if inconclusive_rechecks >= self.MAX_ATTEMPTS:
                        reason = (
                            "Recovery could not be confirmed after "
                            f"{inconclusive_rechecks} verification attempts."
                        )
                        emit(
                            AgentPhase.COMPLETE,
                            "escalated",
                            reason,
                            attempt=len(history),
                            status=IncidentStatus.ESCALATED,
                            data={"verification": verification},
                        )
                        return finish(IncidentStatus.ESCALATED, reason)
                    observation = None
                    continue

                detected_once = True
                emit(
                    AgentPhase.INCIDENT_DETECTED,
                    "incident_detected",
                    "Telemetry breaches the configured incident boundary.",
                    attempt=next_attempt,
                    data={"signals": detection["signals"]},
                )

            emit(
                AgentPhase.INVESTIGATING,
                "investigation_started",
                "Querying diagnostic logs and deployment history.",
                attempt=next_attempt,
            )
            try:
                observations = self.investigate(observation)
            except InfrastructureError as error:
                infrastructure_failures += 1
                reason = f"Investigation failed: {error}"
                emit(
                    AgentPhase.REPLANNING,
                    "tool_error",
                    reason,
                    attempt=len(history),
                    data={"tool": "investigate", "error_type": type(error).__name__},
                )
                observation = None
                if infrastructure_failures >= self.MAX_ATTEMPTS:
                    break
                continue

            observations["attempt_history"] = [dict(entry) for entry in evidence_history]
            if evidence_history:
                observations["previous_attempt"] = dict(evidence_history[-1])

            evidence_ids = [item["id"] for item in observations.get("evidence", [])]
            new_evidence = [item_id for item_id in evidence_ids if item_id not in seen_evidence]
            if history:
                history[-1]["evidence_after_action"] = list(observations.get("evidence", []))
                history[-1]["new_evidence_after_action"] = list(new_evidence)
                evidence_history[-1]["evidence_after_action"] = list(evidence_ids)
                evidence_history[-1]["new_evidence_after_action"] = list(new_evidence)
            seen_evidence.update(evidence_ids)

            emit(
                AgentPhase.INVESTIGATING,
                "evidence_collected",
                f"Collected {len(evidence_ids)} evidence item(s).",
                attempt=next_attempt,
                data={"evidence": observations.get("evidence", []), "new_evidence": new_evidence},
            )
            emit(
                AgentPhase.DIAGNOSING,
                "diagnosis_started",
                "Ranking causal hypotheses from observed evidence.",
                attempt=next_attempt,
            )
            diagnosis = self.diagnose(observations)
            run.diagnosis = diagnosis
            emit(
                AgentPhase.DIAGNOSING,
                "diagnosis_completed",
                diagnosis.get("summary", "Diagnosis completed."),
                attempt=next_attempt,
                data={"diagnosis": diagnosis},
            )

            emit(
                AgentPhase.PLANNING,
                "planning_started",
                "Selecting an evidence-backed bounded response.",
                attempt=next_attempt,
            )
            decision = dict(self.decide(observations, diagnosis))
            decision.setdefault("parameters", {})
            decision.setdefault("evidence", [])
            run.selected_action = decision
            emit(
                AgentPhase.PLANNING,
                "action_proposed" if decision.get("action") != "escalate" else "no_safe_action",
                decision.get("reason", "Decision completed."),
                attempt=next_attempt if decision.get("action") != "escalate" else len(history),
                data={"decision": decision},
            )

            if decision.get("action") == "escalate":
                reason = decision.get("reason", "No safe remediation could be determined.")
                emit(
                    AgentPhase.ESCALATED,
                    "incident_escalated",
                    reason,
                    attempt=len(history),
                    status=IncidentStatus.ESCALATED,
                    data={"decision": decision},
                )
                return finish(IncidentStatus.ESCALATED, reason)

            attempt_number = len(history) + 1
            emit(
                AgentPhase.SAFETY_CHECK,
                "safety_check_started",
                "Evaluating the proposed action against deterministic policy.",
                attempt=attempt_number,
                data={"action": decision.get("action"), "target": decision.get("target")},
            )
            safety_result = self.check_safety(
                decision,
                attempt=attempt_number,
                observations=observations,
            )
            safety_event = "safety_approved" if safety_result.get("allowed") else "safety_rejected"
            emit(
                AgentPhase.SAFETY_CHECK,
                safety_event,
                safety_result.get("reason", "Safety policy evaluated."),
                attempt=attempt_number,
                data={"safety": safety_result},
            )

            if not safety_result.get("allowed"):
                action_result = self.execute(decision, safety_result=safety_result)
                record_attempt(
                    attempt_number,
                    observations,
                    detection,
                    diagnosis,
                    decision,
                    safety_result,
                    action_result,
                    None,
                    new_evidence,
                )
                reason = safety_result.get("reason", action_result.get("message"))
                emit(
                    AgentPhase.BLOCKED,
                    "action_blocked",
                    reason,
                    attempt=attempt_number,
                    status=IncidentStatus.BLOCKED,
                    data={"safety": safety_result, "action_result": action_result},
                )
                return finish(IncidentStatus.BLOCKED, reason)

            emit(
                AgentPhase.EXECUTING,
                "action_started",
                f"Executing {decision['action']} after policy approval.",
                attempt=attempt_number,
                data={"decision": decision},
            )
            try:
                action_result = self.execute(decision, safety_result=safety_result)
            except InfrastructureError as error:
                action_result = {
                    "action": decision["action"],
                    "target": decision.get("target"),
                    "success": False,
                    "status": "failed",
                    "policy_allowed": True,
                    "message": f"Infrastructure action failed: {error}",
                    "error_type": type(error).__name__,
                }

            run.attempted_actions.append({
                "attempt": attempt_number,
                "action": decision.get("action"),
                "target": decision.get("target"),
                "success": bool(action_result.get("success")),
            })
            event_type = "action_completed" if action_result.get("success") else "action_failed"
            emit(
                AgentPhase.EXECUTING,
                event_type,
                action_result.get("message", "Infrastructure action completed."),
                attempt=attempt_number,
                data={"action_result": action_result},
            )

            if not action_result.get("success"):
                run.failed_actions.append(dict(run.attempted_actions[-1]))
                record_attempt(
                    attempt_number,
                    observations,
                    detection,
                    diagnosis,
                    decision,
                    safety_result,
                    action_result,
                    None,
                    new_evidence,
                )
                if len(history) >= self.MAX_ATTEMPTS:
                    reason = MAX_ATTEMPTS_REASON
                    break
                emit(
                    AgentPhase.REPLANNING,
                    "replanning",
                    "The action did not execute successfully; observing again before replanning.",
                    attempt=attempt_number,
                    data={"previous_attempt": evidence_history[-1]},
                )
                observation = None
                continue

            emit(
                AgentPhase.VERIFYING,
                "verification_started",
                "Action completed; collecting independent fresh recovery evidence.",
                attempt=attempt_number,
                data={"action_result": action_result},
            )
            try:
                verification = self.verify(
                    metrics_before=dict(observation.get("metrics", {}))
                )
                if verification.metrics_after:
                    verification.deltas = {
                        "error_rate": round(
                            float(verification.metrics_after.get("error_rate", 0))
                            - float(verification.metrics_before.get("error_rate", 0)),
                            4,
                        ),
                        "latency_ms": (
                            verification.metrics_after.get("latency_ms", 0)
                            - verification.metrics_before.get("latency_ms", 0)
                        ),
                    }
            except InfrastructureError as error:
                verification = failed_verification(
                    f"Verification telemetry unavailable: {error}",
                    before=observation.get("metrics", {}),
                )

            record_attempt(
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
            verification_status = (
                verification.status.value
                if hasattr(verification.status, "value")
                else str(verification.status)
            )
            emit(
                AgentPhase.VERIFYING,
                f"verification_{verification_status}",
                verification.reason,
                attempt=attempt_number,
                data={"verification": verification},
            )

            if verification.recovered:
                reason = verification.reason
                emit(
                    AgentPhase.RESOLVED,
                    "incident_resolved",
                    reason,
                    attempt=attempt_number,
                    status=IncidentStatus.RESOLVED,
                    data={"verification": verification},
                )
                return finish(IncidentStatus.RESOLVED, reason)

            run.failed_actions.append(dict(run.attempted_actions[-1]))
            if len(history) >= self.MAX_ATTEMPTS:
                reason = MAX_ATTEMPTS_REASON
                break

            emit(
                AgentPhase.REPLANNING,
                "replanning",
                "Recovery was not verified; collecting fresh evidence before choosing again.",
                attempt=attempt_number,
                data={
                    "verification_status": verification_status,
                    "previous_attempt": evidence_history[-1],
                },
            )
            observation = None

        reason = reason or MAX_ATTEMPTS_REASON
        emit(
            AgentPhase.ESCALATED,
            "incident_escalated",
            reason,
            attempt=len(history),
            status=IncidentStatus.ESCALATED,
            data={"attempts": len(history), "infrastructure_failures": infrastructure_failures},
        )
        return finish(IncidentStatus.ESCALATED, reason)


controller = IncidentController()
