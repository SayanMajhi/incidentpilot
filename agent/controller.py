import os

from agent.decision import decision_engine
from agent.llm_decision import llm_decision_engine
from safety.policy import policy
from tools import diagnostics, remediation
from verification.verifier import verifier


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
            use_llm = os.getenv(
                "LLM_ENABLED",
                "true",
            ).lower() == "true"

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

        # LLM disabled → deterministic mode.
        if not self.use_llm:

            decision = self.deterministic_engine.decide(
                observations
            )

            decision = dict(decision)
            decision["source"] = "deterministic"

            return decision

        # -----------------------------------------------------
        # Try Qwen first.
        # -----------------------------------------------------

        llm_decision = self.llm_engine.decide(
            observations
        )

        # LLMDecisionEngine exposes whether the call succeeded.
        if getattr(
                self.llm_engine,
                "last_status",
                None,
        ) == "success":

            decision = dict(llm_decision)
            decision["source"] = "llm"

            return decision

        # -----------------------------------------------------
        # Qwen failed → deterministic fallback.
        # -----------------------------------------------------

        fallback = self.deterministic_engine.decide(
            observations
        )

        fallback = dict(fallback)

        fallback["source"] = "deterministic_fallback"

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

        action = decision["action"]
        target = decision.get("target")

        # Escalation is not a remediation action.
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
                "message": "Action blocked by safety policy.",
            }

        # -----------------------------------------------------
        # EXECUTE APPROVED ACTION
        # -----------------------------------------------------

        if action == "rollback_deployment":

            return remediation.rollback_deployment(
                target
            )

        if action == "scale_service":

            return remediation.scale_service(
                target
            )

        if action == "restart_service":

            return remediation.restart_service()

        return {
            "action": action,
            "success": False,
            "status": "unsupported",
            "message": "Unsupported action.",
        }

    # ---------------------------------------------------------
    # VERIFY
    # ---------------------------------------------------------

    def verify(self):

        # IMPORTANT:
        # Read fresh metrics AFTER remediation.

        metrics = diagnostics.get_metrics()

        return verifier.verify(metrics)

    # ---------------------------------------------------------
    # FULL INCIDENT LOOP
    # ---------------------------------------------------------

    def run_incident(self):

        history = []

        status = "unresolved"

        observations = None
        decision = None
        action_result = None
        verification = None
        previous_attempt = None

        for attempt_number in range(
                1,
                self.MAX_ATTEMPTS + 1,
        ):

            # ================================================
            # OBSERVE
            # ================================================

            observations = self.investigate()

            # ================================================
            # DECIDE
            # ================================================

            decision = self.decide(
                observations
            )

            # ================================================
            # ACT
            # execute() performs safety check first.
            # ================================================

            action_result = self.execute(
                decision
            )

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

            safety_result = {
                "action": decision["action"],
                "checked": True,
                "allowed": (
                        action_result.get("status")
                        != "blocked"
                ),
            }

            # ================================================
            # SAFETY BLOCK
            # ================================================

            if action_result.get("status") == "blocked":

                verification = None

                status = "blocked"

                history.append(
                    self._record_attempt(
                        attempt_number,
                        observations,
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

            history.append(
                self._record_attempt(
                    attempt_number,
                    observations,
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

            status = "unresolved"

            # Next iteration performs:
            #
            # OBSERVE AGAIN
            #      ↓
            # NEW QWEN DECISION
            #      ↓
            # SAFETY
            #      ↓
            # ACT
            #      ↓
            # VERIFY

        # ================================================
        # FINAL RESULT
        # ================================================

        return {
            "attempts": history,
            "observations": observations,
            "decision": decision,
            "action_result": action_result,
            "verification": verification,
            "status": status,
        }

    # ---------------------------------------------------------
    # HISTORY
    # ---------------------------------------------------------

    @staticmethod
    def _record_attempt(
            attempt_number,
            observations,
            decision,
            safety_result,
            action_result,
            verification,
    ):

        return {
            "attempt": attempt_number,
            "observations": observations,
            "decision": decision,
            "safety_result": safety_result,
            "action_result": action_result,
            "verification": verification,
        }


controller = IncidentController()