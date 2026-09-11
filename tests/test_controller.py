from unittest.mock import patch

import pytest

from agent.controller import controller, IncidentController
from agent.decision import DecisionEngine
from simulator import service
from tools import remediation


@pytest.fixture(autouse=True)
def reset_simulator_state():
    """Ensure every test starts and ends on the same deterministic,
    healthy baseline, since simulator/remediation state is shared
    module-level state."""
    service.simulate_recover()
    service.state.current_version = service.INITIAL_VERSION
    remediation._current_replicas = 1

    yield

    service.simulate_recover()
    service.state.current_version = service.INITIAL_VERSION
    remediation._current_replicas = 1


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

    service.simulate_bad_deployment()

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

    service.simulate_bad_deployment()

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

    service.simulate_bad_deployment()

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
    service.simulate_outage()

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


def test_run_incident_status_is_unresolved_when_action_does_not_fix_incident():
    """run_incident() must report "unresolved", not "resolved", when
    the chosen action succeeds as an action but verification still
    fails."""

    service.simulate_outage()

    forced_decision = {
        "action": "scale_service",
        "target": 3,
        "reason": "Forced decision for action-success-vs-recovery test",
        "confidence": 0.9,
    }

    with patch.object(controller, "decide", return_value=forced_decision):
        result = controller.run_incident()

    assert result["action_result"]["success"] is True
    assert result["status"] == "unresolved"


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

    with patch.object(controller, "decide", return_value=unsafe_decision):
        result = controller.run_incident()

    assert result["action_result"]["status"] == "blocked"
    assert result["verification"] is None
    assert result["status"] == "blocked"


def test_run_incident_status_is_escalated_for_unknown_incident():
    """run_incident() must report "escalated" for an escalate decision,
    without attempting any remediation or verification."""

    result = controller.run_incident()

    assert result["decision"]["action"] == "escalate"
    assert result["action_result"]["status"] == "escalated"
    assert result["verification"] is None
    assert result["status"] == "escalated"


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
    service.simulate_bad_deployment()

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
    service.simulate_outage()

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

    # Never resolved, and never escalated either - it simply ran out of
    # bounded attempts.
    assert result["status"] == "unresolved"


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

    service.simulate_adaptive_incident()

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