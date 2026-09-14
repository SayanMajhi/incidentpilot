from unittest.mock import patch

import pytest

from backend.agent.controller import controller, IncidentController
from backend.agent.decision import DecisionEngine
from backend.infrastructure import Infrastructure
from backend.shared import slo
from backend.simulator.environment import simulator
from backend.tools import remediation


@pytest.fixture(autouse=True)
def reset_simulator_state():
    """Ensure every test starts and ends on the same deterministic,
    healthy baseline, since backend/simulator/remediation state is shared
    module-level state."""
    simulator.reset()
    simulator.state.current_version = slo.INITIAL_VERSION
    remediation.reset_replicas()

    yield

    simulator.reset()
    simulator.state.current_version = slo.INITIAL_VERSION
    remediation.reset_replicas()


def test_controller_collects_incident_observations():

    observations = controller.investigate()

    assert "metrics" in observations
    assert "health" in observations
    assert "logs" in observations
    assert "current_version" in observations
    assert "deployment_history" in observations


def test_controller_can_make_a_decision():

    observations = controller.investigate()

    decision = controller.decide(observations)

    assert "action" in decision
    assert "reason" in decision
    assert "confidence" in decision


def test_unsafe_action_is_blocked():

    decision = {
        "action": "delete_database",
        "target": None,
        "reason": "Test dangerous action",
        "confidence": 1.0,
    }

    result = controller.execute(decision)

    assert result["success"] is False
    assert result["status"] == "blocked"


def test_unsafe_action_is_blocked_before_remediation_is_called():
    """The safety check must happen BEFORE execution: a blocked action
    must never reach the remediation layer."""

    decision = {
        "action": "delete_database",
        "target": None,
        "reason": "Test dangerous action",
        "confidence": 1.0,
    }

    with patch.object(remediation, "rollback_deployment") as mock_rollback, \
            patch.object(remediation, "scale_service") as mock_scale, \
            patch.object(remediation, "restart_service") as mock_restart:

        result = controller.execute(decision)

    assert result["success"] is False
    assert result["status"] == "blocked"
    mock_rollback.assert_not_called()
    mock_scale.assert_not_called()
    mock_restart.assert_not_called()


def test_valid_rollback_reaches_remediation_layer():
    """A valid rollback_deployment action, once approved by
    SafetyPolicy, must actually reach tools.remediation."""

    simulator.inject_bad_deployment()

    decision = {
        "action": "rollback_deployment",
        "target": "v41",
        "reason": "Test valid rollback",
        "confidence": 0.9,
    }

    with patch.object(
            remediation,
            "rollback_deployment",
            wraps=remediation.rollback_deployment,
    ) as mock_rollback:

        result = controller.execute(decision)

    mock_rollback.assert_called_once_with("v41")
    assert result["action"] == "rollback_deployment"
    assert result["success"] is True


def test_verification_after_successful_rollback_shows_recovery():
    """After a rollback that removes the cause of the bad-deployment
    incident, fresh metrics collected by verify() must show a healthy
    service, and the verifier must report recovered=True."""

    simulator.inject_bad_deployment()

    decision = {
        "action": "rollback_deployment",
        "target": "v41",
        "reason": "Test rollback verification",
        "confidence": 0.9,
    }

    action_result = controller.execute(decision)

    assert action_result["success"] is True

    verification = controller.verify()

    assert verification.recovered is True


def test_run_incident_resolves_bad_deployment_end_to_end():
    """Full flow: simulate a bad deployment, run the controller
    end-to-end, and confirm the incident is actually resolved - not
    merely that some action was taken."""

    simulator.inject_bad_deployment()

    result = controller.run_incident()

    assert result["decision"]["action"] == "rollback_deployment"
    assert result["decision"]["target"] == "v41"
    assert result["action_result"]["success"] is True
    assert result["verification"] is not None
    assert result["verification"].recovered is True
    assert result["status"] == "resolved"


def test_action_success_does_not_imply_incident_recovery():
    """A remediation action can report success as an action (the
    scaling request was applied) without that meaning the underlying
    incident is fixed - success must never be conflated with
    recovery."""

    # An outage NOT tied to the deployed version - scaling replicas
    # does not touch status/error_rate/latency, so it cannot fix this.
    simulator.inject_outage()

    decision = {
        "action": "scale_service",
        "target": 3,
        "reason": "Test action-success vs recovery",
        "confidence": 0.9,
    }

    action_result = controller.execute(decision)

    assert action_result["success"] is True

    verification = controller.verify()

    assert verification.recovered is False


def test_run_incident_escalates_when_action_never_fixes_incident():
    """Repeated command success cannot hide exhausted verification attempts."""

    simulator.inject_outage()

    forced_decision = {
        "action": "scale_service",
        "target": 3,
        "reason": "Forced decision for action-success-vs-recovery test",
        "confidence": 0.9,
    }

    with patch.object(controller, "decide", return_value=forced_decision):
        result = controller.run_incident()

    assert result["action_result"]["success"] is True
    assert result["status"] == "escalated"
    assert result["reason"] == "Maximum remediation attempts exhausted"


def test_run_incident_status_is_blocked_for_unsafe_decision():
    """run_incident() must report "blocked" (not "resolved" or
    "unresolved") when the safety policy rejects the chosen action, and
    must not attempt verification in that case."""

    unsafe_decision = {
        "action": "delete_database",
        "target": None,
        "reason": "Forced unsafe decision for blocked-status test",
        "confidence": 1.0,
    }
    simulator.inject_outage()

    with patch.object(controller, "decide", return_value=unsafe_decision):
        result = controller.run_incident()

    assert result["action_result"]["status"] == "blocked"
    assert result["verification"] is None
    assert result["status"] == "blocked"


def test_run_incident_status_is_no_incident_for_healthy_service():
    """Healthy telemetry must stop before investigation or remediation."""

    result = controller.run_incident()

    assert result["decision"] is None
    assert result["action_result"] is None
    assert result["verification"] is None
    assert result["attempts"] == []
    assert result["status"] == "no_incident"
    assert any(event["event_type"] == "no_incident" for event in result["timeline"])


# ---------------------------------------------------------------------------
# Adaptation loop: OBSERVE -> DECIDE -> SAFETY -> ACT -> VERIFY, retrying
# with a fresh decision when verification fails, bounded by MAX_ATTEMPTS.
# ---------------------------------------------------------------------------

def test_run_incident_retries_with_new_decision_after_failed_verification():
    """First action appears successful but doesn't fix the incident;
    the controller investigates again, gets a DIFFERENT decision, and
    that second action actually resolves it."""

    # Bad deployment: service is down and tied to the current (v42)
    # version. scale_service only changes replica count - it can never
    # touch status/error_rate/latency, so it cannot fix this by itself.
    simulator.inject_bad_deployment()

    first_decision = {
        "action": "scale_service",
        "target": 3,
        "reason": "First attempt: looks like a fix but doesn't address the root cause",
        "confidence": 0.9,
    }

    second_decision = {
        "action": "rollback_deployment",
        "target": "v41",
        "reason": "Second attempt: correct fix for the bad deployment",
        "confidence": 0.9,
    }

    with patch.object(
            controller,
            "decide",
            side_effect=[first_decision, second_decision],
    ):
        result = controller.run_incident()

    assert len(result["attempts"]) == 2

    attempt_1 = result["attempts"][0]

    assert attempt_1["attempt"] == 1
    assert attempt_1["decision"]["action"] == "scale_service"

    # The action itself "succeeded" (the scaling request was applied)...
    assert attempt_1["action_result"]["success"] is True

    # ...but that is not the same thing as the incident being fixed.
    assert attempt_1["verification"] is not None
    assert attempt_1["verification"].recovered is False

    attempt_2 = result["attempts"][1]

    assert attempt_2["attempt"] == 2

    # Attempt 2 investigated again and got a genuinely different decision.
    assert attempt_2["decision"]["action"] == "rollback_deployment"
    assert attempt_2["decision"]["target"] == "v41"
    assert attempt_2["action_result"]["success"] is True
    assert attempt_2["verification"].recovered is True

    # Top-level fields mirror the final (successful) attempt.
    assert result["decision"]["action"] == "rollback_deployment"
    assert result["action_result"]["success"] is True
    assert result["verification"].recovered is True
    assert result["status"] == "resolved"


def test_run_incident_stops_after_max_attempts_without_looping_forever():
    """If verification keeps failing, the loop must stop after
    MAX_ATTEMPTS instead of retrying indefinitely."""

    # An outage NOT tied to the deployed version - scale_service can
    # never fix this, so verification will fail on every attempt.
    simulator.inject_outage()

    forced_decision = {
        "action": "scale_service",
        "target": 3,
        "reason": "Deliberately non-resolving decision for MAX_ATTEMPTS test",
        "confidence": 0.9,
    }

    with patch.object(
            controller,
            "decide",
            return_value=forced_decision,
    ) as mock_decide:

        result = controller.run_incident()

    assert mock_decide.call_count == controller.MAX_ATTEMPTS
    assert len(result["attempts"]) == controller.MAX_ATTEMPTS

    for attempt in result["attempts"]:
        assert attempt["action_result"]["success"] is True
        assert attempt["verification"].recovered is False

    assert result["status"] == "escalated"
    assert result["reason"] == "Maximum remediation attempts exhausted"
    escalation = next(
        event for event in result["trace_events"]
        if event["event_type"] == "incident_escalated"
    )
    assert escalation["phase"] == "escalated"
    assert "Maximum remediation attempts" in escalation["message"]


def test_verification_waits_between_samples_without_waiting_after_last_sample():
    delays = []
    ctl = IncidentController(
        use_llm=False,
        infrastructure=controller.infrastructure,
        verification_interval_seconds=0.25,
        sleep_func=delays.append,
    )

    result = ctl.verify()

    assert result.telemetry["samples"] == ctl.VERIFICATION_SAMPLES
    assert delays == [0.25, 0.25]


def test_incident_result_exposes_goal_and_unique_run_identity():
    first = IncidentController(use_llm=False, verification_interval_seconds=0).run_incident()
    second = IncidentController(use_llm=False, verification_interval_seconds=0).run_incident()

    assert first["run_id"].startswith("inc-")
    assert first["run_id"] != second["run_id"]
    assert first["goal"]
    assert first["started_at"]
    assert first["phase"] == "complete"
    assert first["attempt"] == len(first["history"])


def test_run_incident_unsafe_action_stays_blocked_across_the_loop():
    """An unsafe decision must be blocked by SafetyPolicy every time
    the loop encounters it, and must never reach the remediation
    layer, even inside the adaptation loop."""

    unsafe_decision = {
        "action": "delete_database",
        "target": None,
        "reason": "Forced unsafe decision for blocked-in-loop test",
        "confidence": 1.0,
    }
    simulator.inject_outage()

    with patch.object(
            controller,
            "decide",
            return_value=unsafe_decision,
    ), patch.object(
        remediation,
        "rollback_deployment",
    ) as mock_rollback, patch.object(
        remediation,
        "scale_service",
    ) as mock_scale, patch.object(
        remediation,
        "restart_service",
    ) as mock_restart:

        result = controller.run_incident()

    # Blocked on the very first attempt - the loop does not keep
    # retrying a decision the safety policy already rejected.
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["safety_result"]["allowed"] is False
    assert result["action_result"]["status"] == "blocked"
    assert result["verification"] is None
    assert result["status"] == "blocked"

    mock_rollback.assert_not_called()
    mock_scale.assert_not_called()
    mock_restart.assert_not_called()


def test_adaptive_incident_changes_strategy_after_failed_verification():
    """The agent must adapt after a restart fails verification:
    first restart, then scale after new resource evidence appears."""

    simulator.inject_adaptive_incident()

    test_controller = IncidentController(
        use_llm=False,
        deterministic_engine=DecisionEngine(),
    )

    result = test_controller.run_incident()

    assert result["status"] == "resolved"
    assert len(result["attempts"]) == 2

    first_attempt = result["attempts"][0]
    second_attempt = result["attempts"][1]

    assert first_attempt["decision"]["action"] == "restart_service"
    assert first_attempt["verification"].recovered is False

    assert second_attempt["decision"]["action"] == "scale_service"
    assert second_attempt["decision"]["target"] == 3
    assert second_attempt["verification"].recovered is True


class NeverReadyInfrastructure(Infrastructure):
    """Recovers its metrics after a restart but never reports ready replicas.

    Detection reads metrics only, so it reports a healthy service, while
    verification also requires readiness and keeps failing. The loop has to
    resolve that disagreement within its own budget.
    """

    name = "never_ready"

    def __init__(self):
        self.restarted = False
        self.observations = 0

    def describe(self):
        return {"environment": self.name}

    def get_metrics(self):
        self.observations += 1
        if self.restarted:
            return {"status": "healthy", "error_rate": 0.0, "latency_ms": 20}
        return {"status": "down", "error_rate": 0.5, "latency_ms": 900}

    def check_health(self):
        healthy = self.restarted
        return {"status": "healthy" if healthy else "down", "is_healthy": healthy}

    def get_current_version(self):
        return "v1"

    def get_capacity(self):
        return {"replicas": 3, "ready_replicas": 1, "utilization": None}

    def query_logs(self):
        return [{"timestamp": "t", "level": "ERROR", "message": "upstream request timeout"}]

    def get_deployment_history(self):
        return [{"version": "v1", "order": 1, "timestamp": "t", "status": "current"}]

    def restart_service(self):
        self.restarted = True
        return {"action": "restart_service", "success": True, "status": "completed", "message": "ok"}

    def rollback_deployment(self, version):
        raise AssertionError("not expected")

    def scale_service(self, replicas):
        raise AssertionError("not expected")


def test_unconfirmable_recovery_escalates_instead_of_looping_forever():
    infrastructure = NeverReadyInfrastructure()
    agent = IncidentController(
        use_llm=False,
        deterministic_engine=DecisionEngine(),
        infrastructure=infrastructure,
        verification_interval_seconds=0,
    )

    result = agent.run_incident()

    assert result["status"] == "escalated"
    assert result["reason"]
    # The bound is the attempt budget, so observation cannot run unbounded.
    assert infrastructure.observations <= (
        agent.MAX_ATTEMPTS * (agent.VERIFICATION_SAMPLES + 2) * 2
    )
    assert any(
        event["event_type"] == "verification_inconclusive"
        for event in result["timeline"]
    )
