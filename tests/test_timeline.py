"""Backend-owned incident timeline and no-incident semantics."""

from __future__ import annotations

from unittest.mock import patch

from backend.agent.controller import IncidentController
from backend.agent.decision import DecisionEngine
from backend.simulator.environment import simulator
from backend.tools import remediation


def make_controller() -> IncidentController:
    return IncidentController(
        use_llm=False,
        deterministic_engine=DecisionEngine(),
        verification_interval_seconds=0,
    )


def setup_function():
    simulator.reset()
    remediation.reset_replicas()


def teardown_function():
    simulator.reset()
    remediation.reset_replicas()


def test_healthy_run_is_no_incident_and_never_enters_mutating_phases():
    result = make_controller().run_incident()
    event_types = [event["event_type"] for event in result["timeline"]]

    assert result["status"] == "no_incident"
    assert result["attempts"] == []
    assert "no_incident" in event_types
    assert "investigation_started" not in event_types
    assert "safety_check_started" not in event_types
    assert "action_started" not in event_types
    assert "verification_started" not in event_types


def test_adaptive_run_records_real_failed_verification_replan_and_recovery():
    simulator.inject_adaptive_incident()
    result = make_controller().run_incident()

    assert result["status"] == "resolved"
    assert [item["decision"]["action"] for item in result["attempts"]] == [
        "restart_service",
        "scale_service",
    ]
    assert result["attempts"][0]["verification"].status.value in {"partial", "failed"}
    assert result["attempts"][1]["verification"].status.value == "recovered"
    assert "capacity:over_utilized" in result["attempts"][1]["new_evidence"]

    events = result["timeline"]
    event_types = [event["event_type"] for event in events]
    assert "safety_approved" in event_types
    assert "verification_partial" in event_types or "verification_failed" in event_types
    assert "replanning" in event_types
    assert "verification_recovered" in event_types
    assert "incident_resolved" in event_types
    assert event_types[-1] == "run_completed"
    assert len({event["event_id"] for event in events}) == len(events)
    assert [event["timestamp"] for event in events] == sorted(
        event["timestamp"] for event in events
    )


def test_unknown_action_is_recorded_as_blocked_and_never_executed():
    simulator.inject_outage()
    controller = make_controller()
    unsafe = {
        "action": "delete_database",
        "target": None,
        "parameters": {},
        "reason": "forced unsafe proposal",
        "confidence": 1.0,
        "evidence": [],
    }

    with patch.object(controller, "decide", return_value=unsafe), patch.object(
        controller.infrastructure, "restart_service"
    ) as restart:
        result = controller.run_incident()

    assert result["status"] == "blocked"
    assert result["attempts"][0]["safety_result"]["allowed"] is False
    assert result["attempts"][0]["verification"] is None
    assert any(event["event_type"] == "safety_rejected" for event in result["timeline"])
    restart.assert_not_called()

