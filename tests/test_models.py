"""Validation tests for the runtime-aligned incident domain contract."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.models import (
    ActionProposal,
    ActionType,
    AgentPhase,
    EvidenceItem,
    EvidenceSeverity,
    IncidentRun,
    IncidentStatus,
    TimelineEvent,
    VerificationResult,
    VerificationStatus,
)


def test_required_phase_status_and_action_values_match_runtime():
    assert {phase.value for phase in AgentPhase} == {
        "idle",
        "observing",
        "incident_detected",
        "investigating",
        "diagnosing",
        "planning",
        "safety_check",
        "executing",
        "verifying",
        "replanning",
        "resolved",
        "blocked",
        "escalated",
        "failed",
        "complete",
    }
    assert {status.value for status in IncidentStatus} == {
        "idle",
        "running",
        "no_incident",
        "resolved",
        "blocked",
        "escalated",
        "failed",
    }
    assert {action.value for action in ActionType} == {
        "restart_service",
        "rollback_deployment",
        "scale_service",
        "escalate",
    }


def test_evidence_item_uses_actual_decision_engine_fields():
    timestamp = datetime(2026, 9, 13, 8, 30, tzinfo=timezone.utc)
    item = EvidenceItem(
        id="logs:resource_pressure",
        source="logs",
        signal="resource_pressure",
        detail="Connection pool exhausted.",
        value={"replicas": 1},
        severity=EvidenceSeverity.ERROR,
        timestamp=timestamp,
    )

    assert item.to_dict() == {
        "id": "logs:resource_pressure",
        "source": "logs",
        "signal": "resource_pressure",
        "detail": "Connection pool exhausted.",
        "value": {"replicas": 1},
        "count": None,
        "severity": "error",
        "timestamp": "2026-09-13T08:30:00Z",
    }


def test_evidence_accepts_transitional_input_but_serializes_canonical_shape():
    item = EvidenceItem(
        source="metrics",
        key="error_rate_breach",
        description="Error rate exceeded its SLO.",
    )

    assert item.id == "metrics:error_rate_breach"
    assert item.signal == "error_rate_breach"
    assert "key" not in item.to_dict()


@pytest.mark.parametrize(
    "action",
    ["restart_service", "rollback_deployment", "scale_service", "escalate"],
)
def test_action_proposal_serializes_runtime_action_names(action):
    proposal = ActionProposal(
        action=action,
        reason="Evidence supports this decision.",
        confidence=0.9,
    )

    assert proposal.to_dict()["action"] == action


def test_action_proposal_accepts_old_field_during_migration():
    proposal = ActionProposal(
        action_type="restart",
        reason="Transient-failure evidence supports a restart.",
        confidence=0.7,
    )

    assert proposal.action is ActionType.RESTART_SERVICE
    assert proposal.action_type is ActionType.RESTART_SERVICE


def test_action_proposal_rejects_unknown_or_invalid_confidence():
    with pytest.raises(ValidationError):
        ActionProposal(action="delete_database", reason="unsafe", confidence=1.0)
    with pytest.raises(ValidationError):
        ActionProposal(action="restart_service", reason="invalid", confidence=1.1)


def test_verification_supports_partial_and_legacy_constructor():
    result = VerificationResult(
        status="partial",
        reason="Latency improved but remains above its SLO.",
        metrics_before={"latency_ms": 1000},
        metrics_after={"latency_ms": 750},
        deltas={"latency_ms": -250},
    )
    legacy = VerificationResult(True, "Recovered", {"samples": 3})

    assert result.status is VerificationStatus.PARTIAL
    assert result.recovered is False
    assert legacy.status is VerificationStatus.RECOVERED
    assert legacy.recovered is True


def test_verification_rejects_inconsistent_verdict_fields():
    with pytest.raises(ValidationError):
        VerificationResult(status="recovered", recovered=False, reason="Contradiction")


def test_timeline_event_is_json_ready_and_immutable():
    event = TimelineEvent(
        event_id="evt-1",
        timestamp="2026-09-13T08:30:00Z",
        incident_id="inc-a82f",
        attempt=1,
        phase="safety_check",
        event_type="safety_rejected",
        message="Scale target exceeds the configured upper bound.",
        data={"rule_id": "replica_upper_bound"},
    )

    assert event.to_dict() == {
        "event_id": "evt-1",
        "timestamp": "2026-09-13T08:30:00Z",
        "incident_id": "inc-a82f",
        "attempt": 1,
        "phase": "safety_check",
        "event_type": "safety_rejected",
        "message": "Scale target exceeds the configured upper bound.",
        "data": {"rule_id": "replica_upper_bound"},
    }
    with pytest.raises(ValidationError):
        event.message = "mutated"


def test_incident_run_exposes_compatibility_history_and_trace_events():
    event = TimelineEvent(
        incident_id="inc-a82f",
        phase="observing",
        event_type="observation_started",
        message="Reading fresh telemetry.",
    )
    run = IncidentRun(
        incident_id="inc-a82f",
        goal="Restore SLOs safely.",
        status="no_incident",
        phase="complete",
        timeline=[event],
    )

    payload = run.to_dict()
    assert payload["run_id"] == "inc-a82f"
    assert payload["history"] == payload["attempts"] == []
    assert payload["trace_events"] == payload["timeline"]
    assert payload["status"] == "no_incident"
