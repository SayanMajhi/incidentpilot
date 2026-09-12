import os

from backend.agent.decision import decision_engine
from backend.agent.llm_decision import llm_decision_engine
from backend.safety.policy import policy
from backend.tools import diagnostics, remediation
from backend.verification.verifier import verifier


MAX_ATTEMPTS = 3


class IncidentController:
    MAX_ATTEMPTS = MAX_ATTEMPTS

    def __init__(
            self,
            use_llm=None,
            llm_engine=None,
            deterministic_engine=None,
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

    # ---------------------------------------------------------
    # OBSERVE
    # ---------------------------------------------------------

    def investigate(self):
        """
        Collect a fresh snapshot of the simulated service.

        Every incident attempt performs a new observation so that
        the controller can adapt after remediation failure.
        """
        return {
            "metrics": diagnostics.get_metrics(),
            "health": diagnostics.check_health(),
            "logs": diagnostics.query_logs(),
            "current_version": diagnostics.get_current_version(),
            "deployment_history": diagnostics.get_deployment_history(),
        }

    # ---------------------------------------------------------
    # DECIDE
    # ---------------------------------------------------------

    def decide(self, observations):
        """
        Decide what to do next.

        Architecture:

            Observation
                ↓
            Deterministic evidence
                ↓
            LLM proposal
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
                "reason": (
                    "The service is currently healthy. "
                    "No remediation is required."
                ),
                "confidence": 1.0,
                "source": "deterministic_health_check",
            }

        # -----------------------------------------------------
        # DETERMINISTIC MODE
        # -----------------------------------------------------

        if not self.use_llm:
            decision = self.deterministic_engine.decide(
                observations
            )

            decision = dict(decision)
            decision["source"] = "deterministic"

            return decision

        # -----------------------------------------------------
        # GET DETERMINISTIC EVIDENCE
        # -----------------------------------------------------

        deterministic_decision = (
            self.deterministic_engine.decide(
                observations
            )
        )

        deterministic_decision = dict(
            deterministic_decision
        )

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
            # simulator evidence, prefer the evidence-backed action.
            #
            # Example:
            #
            # Attempt 1:
            #   restart → verification fails
            #
            # Attempt 2:
            #   logs reveal resource exhaustion
            #   Qwen proposes rollback
            #   deterministic engine proposes scale
            #
            # Final:
            #   scale_service
            #
            # This is intentional.
            # -------------------------------------------------

            deterministic_action = (
                deterministic_decision.get(
                    "action"
                )
            )

            llm_action = llm_decision.get(
                "action"
            )

            if deterministic_action != llm_action:
                deterministic_decision[
                    "source"
                ] = "deterministic_arbitration"

                deterministic_decision[
                    "llm_proposal"
                ] = llm_decision

                deterministic_decision[
                    "arbitration_reason"
                ] = (
                    "The model proposal conflicted with the action supported "
                    "by deterministic simulator evidence, so the evidence-backed "
                    "action was selected."
                )

                return deterministic_decision

            # -------------------------------------------------
            # OTHERWISE ACCEPT THE LLM PROPOSAL
            # -------------------------------------------------

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

    # ---------------------------------------------------------
    # SAFETY + ACT
    # ---------------------------------------------------------

    def execute(self, decision):
        """
        Execute an approved decision.

        The LLM never directly executes an action.

        Every remediation must pass through the deterministic
        safety policy before execution.
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

        if action == "rollback_deployment":
            allowed = policy.allows(
                "rollback_deployment",
                version=target,
            )

        elif action == "scale_service":
            allowed = policy.allows(
                "scale_service",
                replicas=target,
            )

        elif action == "restart_service":
            allowed = policy.allows(
                "restart_service"
            )

        else:
            allowed = False

        # -----------------------------------------------------
        # BLOCK UNSAFE ACTION
        # -----------------------------------------------------

        if not allowed:
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
            result = remediation.rollback_deployment(
                target
            )

        elif action == "scale_service":
            result = remediation.scale_service(
                target
            )

        elif action == "restart_service":
            result = remediation.restart_service()

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
        Verify the current service state using fresh metrics.

        IMPORTANT:
        Successful execution of an action does NOT mean that the
        incident has been resolved.
        """

        metrics = diagnostics.get_metrics()

        return verifier.verify(metrics)

    # ---------------------------------------------------------
    # FULL INCIDENT LOOP
    # ---------------------------------------------------------

    def run_incident(self, on_event=None):
        """
        Run the autonomous incident-response loop.

        Observe
            ↓
        Decide
            ↓
        Safety
            ↓
        Act
            ↓
        Verify
            ↓
        Adapt
            ↓
        Observe again
        """

        history = []

        status = "unresolved"

        observations = None
        decision = None
        action_result = None
        verification = None

        previous_attempt = None

        def emit(phase, **details):
            if on_event is not None:
                on_event(phase, details)

        for attempt_number in range(
                1,
                self.MAX_ATTEMPTS + 1,
        ):

            # ================================================
            # OBSERVE
            # ================================================

            observations = self.investigate()
            detection = self.detect(observations)
            emit("investigating", attempt=attempt_number, detection=detection)

            # Give the next decision-making step context about
            # what happened during the previous attempt.
            if previous_attempt is not None:
                observations[
                    "previous_attempt"
                ] = previous_attempt

            # ================================================
            # DECIDE
            # ================================================

            decision = self.decide(
                observations
            )
            diagnosis = self.diagnose(observations, decision)
            emit(
                "deciding",
                attempt=attempt_number,
                diagnosis=diagnosis,
                decision=decision,
            )

            # ================================================
            # ACT
            # ================================================

            emit("safety_check", attempt=attempt_number, action=decision.get("action"))
            action_result = self.execute(
                decision
            )
            emit("remediating", attempt=attempt_number, action_result=action_result)

            # ================================================
            # ESCALATION
            # ================================================

            if decision["action"] == "escalate":

                safety_result = {
                    "action": "escalate",
                    "checked": False,
                    "allowed": None,
                }

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
                    )
                )

                break

            # ================================================
            # SAFETY RESULT
            # ================================================

            # The verdict comes from the deterministic policy gate itself,
            # not from the action's outcome string - an approved action that
            # then fails to execute must not be reported as "blocked", and a
            # blocked action must never be reported as allowed.
            safety_result = {
                "action": decision["action"],
                "checked": True,
                "allowed": bool(
                    action_result.get("policy_allowed")
                ),
            }

            # ================================================
            # SAFETY BLOCK
            # ================================================

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
                    )
                )

                break

            # ================================================
            # VERIFY
            # ================================================

            verification = self.verify()
            emit(
                "verifying",
                attempt=attempt_number,
                verification=verification.to_dict(),
            )

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
                )
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

            previous_attempt = {
                "action": decision.get(
                    "action"
                ),
                "target": decision.get(
                    "target"
                ),
                "action_status": action_result.get(
                    "status"
                ),
                "verification_recovered": (
                    verification.recovered
                ),
                "verification_reason": (
                    verification.reason
                ),
            }

            status = "unresolved"
            emit("adapting", attempt=attempt_number, previous_attempt=previous_attempt)

            # The next iteration performs:
            #
            # OBSERVE AGAIN
            #      ↓
            # NEW EVIDENCE
            #      ↓
            # LLM PROPOSAL
            #      ↓
            # DETERMINISTIC ARBITRATION
            #      ↓
            # SAFETY
            #      ↓
            # ACT
            #      ↓
            # VERIFY

        # ================================================
        # FINAL RESULT
        # ================================================

        emit("complete", status=status, attempts=len(history))
        return {
            "attempts": history,
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
    def diagnose(observations, decision):
        """Summarize evidence without exposing private model reasoning."""
        action = decision.get("action")
        if action == "rollback_deployment":
            cause = "deployment_regression"
        elif action == "scale_service":
            cause = "resource_exhaustion"
        elif action == "restart_service":
            cause = "transient_service_failure"
        elif observations.get("metrics", {}).get("status") == "healthy":
            cause = "no_active_incident"
        else:
            cause = "undetermined"
        return {
            "probable_cause": cause,
            "summary": decision.get("reason", "No diagnosis available."),
            "confidence": decision.get("confidence", 0),
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
    ):
        """
        Store a complete audit record for one attempt.
        """

        return {
            "attempt": attempt_number,
            "observations": observations,
            "detection": detection,
            "diagnosis": diagnosis,
            "decision": decision,
            "safety_result": safety_result,
            "action_result": action_result,
            "verification": verification,
        }


controller = IncidentController()
