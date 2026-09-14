"""Closed-loop adaptation tests for IncidentController.

These tests drive the real controller, decision engine, safety policy,
remediation tools and simulator together. Mocks are used only to spy on calls
or to force a single decision, never to script what the environment does next.

The central claim under test: after a verified failure, the next action is
chosen from *freshly observed evidence*, not from the identity of the
scenario or of the previous action.
"""

import inspect
from unittest.mock import patch

import pytest

from backend.agent import controller as controller_module
from backend.agent import decision as decision_module
from backend.agent.controller import IncidentController
from backend.agent.decision import DecisionEngine
from backend.safety.policy import policy
from backend.shared import slo
from backend.simulator import environment
from backend.simulator.environment import simulator
from tests.helpers import reset_simulator
from backend.tools import diagnostics, remediation


@pytest.fixture(autouse=True)
def clean_simulator():
    reset_simulator()
    yield
    reset_simulator()


def make_controller(**kwargs):
    kwargs.setdefault("use_llm", False)
    kwargs.setdefault("deterministic_engine", DecisionEngine())
    return IncidentController(**kwargs)


def actions(result):
    return [
        (attempt["decision"]["action"], attempt["decision"]["target"])
        for attempt in result["attempts"]
    ]


def force_first_decision(ctl, forced):
    """Force attempt 1's decision; every later decision is the real one."""
    real_decide = ctl.decide
    calls = {"n": 0}

    def decide(observations, diagnosis=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return dict(forced)
        return real_decide(observations, diagnosis)

    return patch.object(ctl, "decide", side_effect=decide)


# ---------------------------------------------------------------------------
# World builders. Each one sets up hidden *causes* in the simulator; the
# symptoms an agent can observe are always derived from those causes.
# ---------------------------------------------------------------------------

def _set_causes(*, transient=False, load=environment.BASELINE_LOAD_UNITS, bad_version=False):
    simulator.state._transient_fault = transient
    simulator.state._load_units = load
    if bad_version:
        simulator.state.current_version = slo.BAD_DEPLOYMENT_VERSION
        simulator.state._deployment_regression = True
    simulator.recompute()


# ===========================================================================
# 1. Verification can reject a technically successful action.
# ===========================================================================

def test_verification_rejects_a_technically_successful_action():
    simulator.inject_adaptive_incident()

    result = make_controller().run_incident()

    first = result["attempts"][0]
    assert first["decision"]["action"] == "restart_service"
    assert first["action_result"]["success"] is True
    assert first["action_result"]["status"] == "completed"

    # The restart ran, but fresh post-action telemetry says it did not recover.
    assert first["verification"].recovered is False
    assert first["verification"].telemetry["metrics"]["status"] == "down"
    assert first["verification"].telemetry["samples"] == make_controller().VERIFICATION_SAMPLES


# ===========================================================================
# 2. Failed verification causes re-observation.
# ===========================================================================

def test_failed_verification_causes_fresh_re_observation():
    simulator.inject_adaptive_incident()
    ctl = make_controller()

    with patch.object(ctl, "observe", wraps=ctl.observe) as observe:
        result = ctl.run_incident()

    assert result["status"] == "resolved"
    assert observe.call_count == len(result["attempts"]) == 2

    before = result["attempts"][0]["observations"]
    after = result["attempts"][1]["observations"]

    # A new observation, not a reused one...
    assert after["observation_id"] > before["observation_id"]
    # ...that reflects the world *after* attempt 1's action.
    assert before["metrics"] == {
        "status": "down",
        "error_rate": 0.70,
        "latency_ms": 1000,
        "cpu_percent": 94,
        "memory_percent": 82,
    }
    assert after["metrics"] == result["attempts"][0]["verification"].telemetry["metrics"]
    assert after["metrics"] != before["metrics"]
    assert before["capacity"]["utilization"] is None
    assert after["capacity"]["utilization"] == 2.5


# ===========================================================================
# 3. Re-investigation occurs.
# ===========================================================================

def test_failed_verification_causes_re_investigation_and_re_diagnosis():
    simulator.inject_adaptive_incident()
    ctl = make_controller()

    with patch.object(diagnostics, "query_logs", wraps=diagnostics.query_logs) as query_logs, \
            patch.object(diagnostics, "get_deployment_history", wraps=diagnostics.get_deployment_history) as history, \
            patch.object(ctl, "diagnose", wraps=ctl.diagnose) as diagnose:
        result = ctl.run_incident()

    assert len(result["attempts"]) == 2
    assert query_logs.call_count == 2
    assert history.call_count == 2
    assert diagnose.call_count == 2

    first, second = result["attempts"]
    assert first["observations"]["logs"] != second["observations"]["logs"]
    assert first["diagnosis"]["probable_cause"] == "transient_service_failure"
    assert second["diagnosis"]["probable_cause"] == "resource_exhaustion"

    # The re-diagnosis is built from the new evidence alone.
    viable = [h["cause"] for h in second["diagnosis"]["hypotheses"] if h["status"] == "viable"]
    assert viable == ["resource_exhaustion"]


# ===========================================================================
# 4 + 5. MOST IMPORTANT: new evidence decides the next action.
#
# Every world below looks IDENTICAL during attempt 1 (hung workers mask
# everything behind them), so attempt 1 always restarts. They differ only in
# the hidden cause that the restart exposes. A controller hardcoded to
# "restart -> scale" (or "if previous action was restart, scale") passes at
# most one of these worlds; only a controller whose second decision follows
# the newly observed evidence passes all of them.
# ===========================================================================

def _world_capacity_shortfall():
    simulator.inject_adaptive_incident()  # hung workers + 2.5x demand on 1 replica


def _world_hidden_bad_deployment():
    simulator.inject_adaptive_incident()
    _set_causes(transient=True, bad_version=True)


_WORLDS = {
    "capacity_shortfall": (
        _world_capacity_shortfall,
        [("restart_service", None), ("scale_service", 3)],
        "resolved",
    ),
    "hidden_bad_deployment": (
        _world_hidden_bad_deployment,
        [("restart_service", None), ("rollback_deployment", "v41")],
        "resolved",
    ),
}


def test_second_decision_depends_on_newly_observed_evidence_not_on_a_fixed_sequence():
    results = {}

    for name, (build_world, _, _) in _WORLDS.items():
        reset_simulator()
        build_world()
        results[name] = make_controller().run_incident()

    # World where the restart "succeeds" but has no effect at all: the fresh
    # evidence is unchanged, so there is nothing new to justify any action.
    reset_simulator()
    simulator.inject_adaptive_incident()
    _set_causes(transient=True)
    no_effect = {
        "action": "restart_service",
        "success": True,
        "status": "completed",
        "message": "Restart executed but deliberately left simulator causes unchanged.",
    }
    with patch.object(remediation, "restart_service", return_value=no_effect):
        results["restart_had_no_effect"] = make_controller().run_incident()

    expected = {name: (sequence, status) for name, (_, sequence, status) in _WORLDS.items()}
    expected["restart_had_no_effect"] = ([("restart_service", None)], "escalated")

    # --- Attempt 1 saw exactly the same evidence in every world -------------
    first_attempts = [result["attempts"][0] for result in results.values()]
    reference = first_attempts[0]
    for attempt in first_attempts[1:]:
        assert attempt["observations"]["metrics"] == reference["observations"]["metrics"]
        assert attempt["observations"]["logs"] == reference["observations"]["logs"]
        assert attempt["observations"]["capacity"] == reference["observations"]["capacity"]
        assert [e["id"] for e in attempt["evidence"]] == [e["id"] for e in reference["evidence"]]
        assert attempt["decision"]["action"] == "restart_service"
        assert attempt["verification"].recovered is False

    # --- ...yet the second decision differs, following the new evidence -----
    for name, result in results.items():
        sequence, status = expected[name]
        assert actions(result) == sequence, name
        assert result["status"] == status, name

    second_actions = {
        (
            (result["attempts"][1]["decision"]["action"], result["attempts"][1]["decision"]["target"])
            if len(result["attempts"]) > 1
            else (result["decision"]["action"], result["decision"].get("target"))
        )
        for result in results.values()
    }
    assert len(second_actions) == len(results), "every world must produce a different second decision"

    # --- The justification for each second action is evidence that did not
    #     exist in attempt 1 ---------------------------------------------------
    for name, result in results.items():
        first = result["attempts"][0]
        if len(result["attempts"]) == 1:
            assert result["decision"]["action"] == "escalate"
            assert first["new_evidence_after_action"] == []
            continue
        second = result["attempts"][1]
        first_ids = {e["id"] for e in first["evidence"]}
        justification = set(second["decision"]["evidence"])
        assert justification, name
        assert justification.isdisjoint(first_ids), name
        assert justification <= set(second["new_evidence"]), name
        assert first["new_evidence_after_action"] == second["new_evidence"], name


# ===========================================================================
# 6. The controller eventually recovers when the second action is appropriate.
# ===========================================================================

def test_adaptive_incident_recovers_with_complete_evidence_history():
    simulator.inject_adaptive_incident()

    result = make_controller().run_incident()

    assert result["status"] == "resolved"
    assert simulator.state.status == "healthy"
    assert remediation.get_current_replicas() == 3

    first, second = result["evidence_history"]

    assert first["action"] == "restart_service"
    assert first["action_success"] is True
    assert first["policy_allowed"] is True
    assert first["verification_recovered"] is False
    assert "capacity:over_utilized" in first["new_evidence_after_action"]
    assert "logs:resource_pressure" in first["new_evidence_after_action"]

    assert second["attempt"] == 2
    assert second["action"] == "scale_service"
    assert second["target"] == 3
    assert second["action_success"] is True
    assert second["verification_recovered"] is True

    # The scale target was derived from measured utilization, not a constant.
    parameters = result["attempts"][1]["decision"]["parameters"]
    assert parameters["utilization"] == 2.5
    assert parameters["current_replicas"] == 1


def test_adaptation_is_order_independent():
    """If attempt 1 scales instead of restarting, the fresh evidence still
    shows hung workers, so the controller restarts next and recovers. The
    environment rewards removing causes, not a particular order."""
    simulator.inject_adaptive_incident()
    ctl = make_controller()

    forced = {"action": "scale_service", "target": 3, "reason": "forced", "confidence": 0.9}
    with force_first_decision(ctl, forced):
        result = ctl.run_incident()

    assert actions(result) == [("scale_service", 3), ("restart_service", None)]
    assert result["attempts"][0]["verification"].recovered is False
    assert result["status"] == "resolved"


def test_insufficient_scaling_is_followed_by_a_larger_step_sized_from_fresh_telemetry():
    """The same action type may be proposed again, but only with a target the
    new utilization reading justifies - never as a blind repeat."""
    simulator.inject_adaptive_incident()
    _set_causes(transient=False, load=2.5)
    ctl = make_controller()

    forced = {"action": "scale_service", "target": 2, "reason": "forced", "confidence": 0.9}
    with force_first_decision(ctl, forced):
        result = ctl.run_incident()

    assert actions(result) == [("scale_service", 2), ("scale_service", 3)]
    assert result["attempts"][1]["observations"]["capacity"]["utilization"] == 1.25
    assert result["status"] == "resolved"


# ===========================================================================
# 7. Maximum attempts are respected.
# ===========================================================================

def test_engine_driven_loop_escalates_at_max_attempts():
    """Hung workers, a bad deployment and an 8x traffic surge (more than the
    3-replica safe maximum can absorb). Each attempt removes one cause the
    fresh evidence reveals, but the incident can never fully recover."""
    simulator.inject_adaptive_incident()
    _set_causes(transient=True, load=8.0, bad_version=True)

    result = make_controller().run_incident()

    assert len(result["attempts"]) == make_controller().MAX_ATTEMPTS == 3
    assert actions(result) == [
        ("restart_service", None),
        ("rollback_deployment", "v41"),
        ("scale_service", 3),
    ]
    assert all(attempt["verification"].recovered is False for attempt in result["attempts"])
    assert result["status"] == "escalated"
    assert result["reason"] == "Maximum remediation attempts exhausted"


def test_lower_attempt_budget_is_honoured():
    simulator.inject_adaptive_incident()
    _set_causes(transient=True, load=8.0, bad_version=True)
    ctl = make_controller()
    ctl.MAX_ATTEMPTS = 2

    with patch.object(remediation, "scale_service", wraps=remediation.scale_service) as scale:
        result = ctl.run_incident()

    assert len(result["attempts"]) == 2
    scale.assert_not_called()
    assert result["status"] == "escalated"


# ===========================================================================
# 8. Unsupported evidence causes escalation.
# ===========================================================================

def test_unsupported_evidence_escalates_without_inventing_an_action():
    simulator.inject_outage()
    unrecognised_logs = [
        {"timestamp": "t1", "level": "ERROR", "message": "Unexpected internal fault in billing module."},
    ]

    with patch.object(diagnostics, "query_logs", return_value=unrecognised_logs), \
            patch.object(policy, "evaluate", wraps=policy.evaluate) as evaluate, \
            patch.object(remediation, "restart_service") as restart, \
            patch.object(remediation, "scale_service") as scale, \
            patch.object(remediation, "rollback_deployment") as rollback:
        result = make_controller().run_incident()

    assert actions(result) == []
    assert result["status"] == "escalated"
    assert result["diagnosis"]["probable_cause"] == "undetermined"
    assert result["decision"]["action"] == "escalate"
    evaluate.assert_not_called()
    restart.assert_not_called()
    scale.assert_not_called()
    rollback.assert_not_called()


def test_capacity_shortfall_beyond_safe_maximum_escalates():
    simulator.inject_adaptive_incident()
    _set_causes(transient=False, load=9.0)
    remediation.scale_service(3)

    result = make_controller().run_incident()

    assert actions(result) == []
    assert result["decision"]["action"] == "escalate"
    assert "safe maximum" in result["decision"]["reason"]


# ===========================================================================
# 9. Safety policy is evaluated for every action.
# ===========================================================================

def test_safety_policy_is_evaluated_before_every_executed_action():
    simulator.inject_adaptive_incident()

    call_order = []
    real_evaluate = policy.evaluate
    real_restart = remediation.restart_service
    real_scale = remediation.scale_service

    def spy_evaluate(*args, **kwargs):
        action = kwargs.get("action") or (args[0] if args else None)
        call_order.append(("policy", action))
        return real_evaluate(*args, **kwargs)

    def spy_restart():
        call_order.append(("execute", "restart_service"))
        return real_restart()

    def spy_scale(replicas):
        call_order.append(("execute", "scale_service"))
        return real_scale(replicas)

    with patch.object(policy, "evaluate", side_effect=spy_evaluate), \
            patch.object(remediation, "restart_service", side_effect=spy_restart), \
            patch.object(remediation, "scale_service", side_effect=spy_scale):
        result = make_controller().run_incident()

    assert call_order == [
        ("policy", "restart_service"),
        ("execute", "restart_service"),
        ("policy", "scale_service"),
        ("execute", "scale_service"),
    ]
    for attempt in result["attempts"]:
        assert attempt["safety_result"]["action"] == attempt["decision"]["action"]
        assert attempt["safety_result"]["checked"] is True
        assert attempt["safety_result"]["allowed"] is True
        assert attempt["safety_result"]["rule_id"]


def test_unsafe_proposal_in_a_later_attempt_is_blocked_before_execution():
    simulator.inject_adaptive_incident()
    ctl = make_controller()
    real_decide = ctl.decide
    calls = {"n": 0}

    def decide(observations, diagnosis=None):
        calls["n"] += 1
        if calls["n"] == 2:
            return {"action": "scale_service", "target": 50, "reason": "forced", "confidence": 1.0}
        return real_decide(observations, diagnosis)

    with patch.object(ctl, "decide", side_effect=decide), \
            patch.object(remediation, "scale_service") as scale:
        result = ctl.run_incident()

    assert actions(result) == [("restart_service", None), ("scale_service", 50)]
    assert result["attempts"][1]["safety_result"]["allowed"] is False
    assert result["attempts"][1]["verification"] is None
    assert result["status"] == "blocked"
    scale.assert_not_called()


# ===========================================================================
# Optional LLM stays advisory and cannot bypass the evidence history.
# ===========================================================================

class _FakeLLM:
    """Always proposes the same action, as a stubborn model might."""

    last_status = "success"
    last_error = None

    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = 0

    def decide(self, observations):
        self.calls += 1
        return dict(self.proposal)


def test_llm_cannot_repeat_a_remediation_that_already_failed_verification():
    simulator.inject_adaptive_incident()
    _set_causes(transient=False, load=4.5)
    llm = _FakeLLM({"action": "scale_service", "target": 3, "reason": "model", "confidence": 0.8})
    ctl = make_controller(use_llm=True, llm_engine=llm)

    result = ctl.run_incident()

    first, = result["attempts"]
    # Attempt 1: the model agreed on the action; its target was accepted.
    assert first["decision"]["source"] == "llm"
    assert (first["decision"]["action"], first["decision"]["target"]) == ("scale_service", 3)
    assert first["verification"].recovered is False
    # The next proposal repeats the failed maximum; arbitration escalates.
    # Escalation is a controller decision, so it does not consume a remediation
    # attempt record.
    assert result["decision"]["source"] == "deterministic_arbitration"
    assert result["decision"]["llm_proposal"]["target"] == 3
    assert (result["decision"]["action"], result["decision"]["target"]) == ("escalate", None)
    assert result["status"] == "escalated"
    assert llm.calls == 2


def test_deterministic_loop_needs_no_llm_credentials(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_MODEL", raising=False)
    simulator.inject_adaptive_incident()

    result = make_controller(use_llm=False).run_incident()

    assert result["status"] == "resolved"
    assert {attempt["decision"]["source"] for attempt in result["attempts"]} == {"deterministic"}


# ===========================================================================
# Guard: the agent layer must never branch on the scenario.
# ===========================================================================

@pytest.mark.parametrize(
    "module",
    [controller_module, decision_module, remediation, diagnostics],
    ids=lambda module: module.__name__,
)
def test_agent_and_tool_code_never_references_the_adaptive_scenario(module):
    source = inspect.getsource(module).lower()
    assert "adaptive" not in source
    assert "active_scenario" not in source
