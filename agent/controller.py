from agent.decision import decision_engine
from safety.policy import policy
from tools import diagnostics, remediation
from verification.verifier import verifier

# Maximum number of OBSERVE -> DECIDE -> SAFETY -> ACT -> VERIFY attempts
# run_incident() will make for a single incident before giving up. This is
# what keeps the adaptation loop from retrying forever: attempts are
# strictly bounded, not open-ended.
MAX_ATTEMPTS = 3


class IncidentController:

    # Exposed as a class attribute (not just the module constant) so a
    # caller/test can override it per-instance if needed, while still
    # defaulting to the module-level MAX_ATTEMPTS.
    MAX_ATTEMPTS = MAX_ATTEMPTS

    def investigate(self):
        """Collect the evidence needed to make an incident decision."""

        observations = {
            "metrics": diagnostics.get_metrics(),
            "health": diagnostics.check_health(),
            "logs": diagnostics.query_logs(),
            "current_version": diagnostics.get_current_version(),
            "deployment_history": diagnostics.get_deployment_history(),
        }

        return observations

    def decide(self, observations):
        """Ask the decision engine what action should be taken."""

        return decision_engine.decide(observations)

    def execute(self, decision):
        """Validate and execute the proposed action."""

        action = decision["action"]
        target = decision.get("target")

        # Escalation does not require a remediation tool.
        if action == "escalate":
            return {
                "action": "escalate",
                "success": True,
                "status": "escalated",
                "message": decision["reason"],
            }

        # Safety check BEFORE executing anything.
        if action == "rollback_deployment":
            allowed = policy.allows(
                "rollback_deployment",
                version=target
            )
        elif action == "scale_service":
            allowed = policy.allows(
                "scale_service",
                replicas=target
            )
        elif action == "restart_service":
            allowed = policy.allows("restart_service")
        else:
            allowed = False

        if not allowed:
            return {
                "action": action,
                "success": False,
                "status": "blocked",
                "message": "Action blocked by safety policy.",
            }

        # Execute the approved action.
        if action == "rollback_deployment":
            return remediation.rollback_deployment(target)

        if action == "scale_service":
            return remediation.scale_service(target)

        if action == "restart_service":
            return remediation.restart_service()

        return {
            "action": action,
            "success": False,
            "status": "unsupported",
            "message": "Unsupported action.",
        }

    def verify(self):
        """Check whether the service is actually healthy.

        Always re-reads metrics from diagnostics at call time, so this
        reflects the service's state *after* remediation ran - never
        the stale observations collected during investigate().
        """

        metrics = diagnostics.get_metrics()
        return verifier.verify(metrics)

    def run_incident(self):
        """Run the adaptive incident-response loop, end to end:

            OBSERVE -> DECIDE -> SAFETY -> ACT -> VERIFY
                             |
                    verification fails
                             |
                        OBSERVE AGAIN
                             |
                        NEW DECISION -> ACT -> VERIFY
                             |
                     ... up to MAX_ATTEMPTS ...

        Each pass re-investigates from scratch (fresh observations,
        never the previous attempt's stale data), asks the existing
        DecisionEngine for a new decision, and runs it through the same
        safety-check-then-execute path as a single-shot call to
        execute(). The safety check always happens BEFORE any
        remediation tool is invoked - a blocked action never reaches
        tools.remediation and the loop stops immediately (no point
        retrying a decision the policy already rejected).

        A verification failure is the only thing that triggers another
        lap of the loop. Attempts are strictly bounded by
        self.MAX_ATTEMPTS, so the loop can never retry forever - once
        attempts are exhausted, the run ends "unresolved" rather than
        looping endlessly on a decision that keeps failing to fix the
        incident.

        Whether an action "succeeded" (the remediation tool executed
        as requested) and whether the incident "recovered" (a fresh
        verification pass says the service is actually healthy) are
        always tracked separately per attempt - a successful action is
        never treated as proof of recovery.

        Returns:
            dict: A structured result with keys:
                - "attempts": list of per-attempt records, each with
                  "attempt" (1-indexed attempt number), "observations",
                  "decision", "safety_result", "action_result", and
                  "verification".
                - "observations", "decision", "action_result",
                  "verification": the same values as the last attempt
                  made (kept at the top level for convenience/backward
                  compatibility with a single-attempt call site).
                - "status": one of "resolved", "unresolved", "blocked",
                  or "escalated".
        """
        history = []
        status = "unresolved"

        observations = None
        decision = None
        action_result = None
        verification = None

        for attempt_number in range(1, self.MAX_ATTEMPTS + 1):
            observations = self.investigate()
            decision = self.decide(observations)
            action_result = self.execute(decision)

            if decision["action"] == "escalate":
                # No remediation tool involved, so there's nothing to
                # verify - the decision engine itself couldn't find a
                # confident action.
                safety_result = {"action": "escalate", "checked": False, "allowed": None}
                verification = None
                status = "escalated"
                history.append(
                    self._record_attempt(
                        attempt_number, observations, decision, safety_result,
                        action_result, verification,
                    )
                )
                break

            safety_result = {
                "action": decision["action"],
                "checked": True,
                "allowed": action_result.get("status") != "blocked",
            }

            if action_result.get("status") == "blocked":
                # Rejected by SafetyPolicy before remediation ran. Retrying
                # the identical decision would just be blocked again, so
                # stop rather than burn further attempts.
                verification = None
                status = "blocked"
                history.append(
                    self._record_attempt(
                        attempt_number, observations, decision, safety_result,
                        action_result, verification,
                    )
                )
                break

            # The action was allowed and reached the remediation layer.
            # action_result["success"] only says the action itself ran -
            # it is NOT the same thing as the incident being fixed. Only
            # a fresh verification pass (never the observations collected
            # before this action ran) can say that.
            verification = self.verify()
            history.append(
                self._record_attempt(
                    attempt_number, observations, decision, safety_result,
                    action_result, verification,
                )
            )

            if verification.recovered:
                status = "resolved"
                break

            # Verification failed - the loop's retry trigger. Go around
            # again (fresh OBSERVE, new DECIDE) unless attempts are
            # exhausted, in which case the for-loop simply ends and
            # status stays "unresolved".
            status = "unresolved"

        return {
            "attempts": history,
            "observations": observations,
            "decision": decision,
            "action_result": action_result,
            "verification": verification,
            "status": status,
        }

    @staticmethod
    def _record_attempt(attempt_number, observations, decision, safety_result, action_result, verification):
        """Build one entry of the execution history for run_incident().

        Kept as a small dedicated helper so the shape of a history
        entry is defined in exactly one place.

        Returns:
            dict: with keys "attempt", "observations", "decision",
            "safety_result", "action_result", "verification".
        """
        return {
            "attempt": attempt_number,
            "observations": observations,
            "decision": decision,
            "safety_result": safety_result,
            "action_result": action_result,
            "verification": verification,
        }


controller = IncidentController()