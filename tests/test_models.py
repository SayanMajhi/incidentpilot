"""Validation and serialization tests for shared agent domain models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.models import (
    EvidenceItem,
    EvidenceSeverity,
    InvestigationResult,
    ProposedAction,
    RemediationActionType,
    TraceEvent,
    TracePhase,
    VerificationResult,
    VerificationStatus,
)


def test_evidence_item_serializes_as_json_values():
    timestamp = datetime(2026, 9, 13, 8, 30, tzinfo=timezone.utc)
    item = EvidenceItem(
        source="logs",
        key="resource_pressure",
        value={"replicas": 1},
        severity=EvidenceSeverity.ERROR,
        timestamp=timestamp,
        description="Connection pool exhausted.",
    )

    assert item.model_dump(mode="json") == {
        "source": "logs",
        "key": "resource_pressure",
        "value": {"replicas": 1},
        "severity": "error",
        "timestamp": "2026-09-13T08:30:00Z",
        "description": "Connection pool exhausted.",
    }


def test_investigation_coerces_nested_evidence_to_typed_models():
    result = InvestigationResult(
        evidence=[{
            "source": "metrics",
            "key": "error_rate",
            "value": 0.7,
            "severity": "critical",
            "description": "Error-rate SLO breached.",
        }],
        summary="The service is unhealthy.",
    )

    assert isinstance(result.evidence[0], EvidenceItem)
    assert result.evidence[0].severity is EvidenceSeverity.CRITICAL


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("restart", RemediationActionType.RESTART),
        ("rollback", RemediationActionType.ROLLBACK),
        ("scale", RemediationActionType.SCALE),
    ],
)
def test_proposed_action_handles_each_enum_value(raw, expected):
    action = ProposedAction(
        action_type=raw,
        reason="Evidence supports this bounded remediation.",
        confidence=0.9,
    )

    assert action.action_type is expected
    assert action.model_dump(mode="json")["action_type"] == raw


def test_proposed_action_rejects_invalid_remediation_type():
    with pytest.raises(ValidationError):
        ProposedAction(
            action_type="delete_database",
            reason="Unsafe and unsupported.",
            confidence=1.0,
        )


def test_proposed_action_validates_confidence_range():
    with pytest.raises(ValidationError):
        ProposedAction(
            action_type="restart",
            reason="Confidence cannot exceed one.",
            confidence=1.1,
        )


def test_verification_supports_legacy_constructor_and_structured_fields():
    result = VerificationResult(
        True,
        "Service remained healthy during verification",
        {"samples": 3},
        metrics_before={"error_rate": 0.7},
        metrics_after={"error_rate": 0.01},
    )

    payload = result.to_dict()
    assert result.status is VerificationStatus.RECOVERED
    assert payload["status"] == "recovered"
    assert payload["recovered"] is True
    assert payload["metrics_before"]["error_rate"] == 0.7
    assert payload["metrics_after"]["error_rate"] == 0.01


def test_verification_rejects_inconsistent_status_and_boolean():
    with pytest.raises(ValidationError):
        VerificationResult(
            status="recovered",
            recovered=False,
            reason="Contradictory verdict.",
        )


def test_trace_event_serializes_nested_models_for_api_consumers():
    event = TraceEvent(
        attempt=1,
        phase=TracePhase.DECIDING,
        evidence=[{
            "source": "logs",
            "key": "transient_failure",
            "value": "HTTP 503",
            "severity": "warning",
            "description": "A transient request failure was observed.",
        }],
        diagnosis="transient_service_failure",
        decision={
            "action_type": "restart",
            "reason": "Restart evidence is present.",
            "confidence": 0.7,
        },
    )

    payload = event.model_dump(mode="json")
    assert payload["phase"] == "deciding"
    assert payload["decision"]["action_type"] == "restart"
    assert payload["evidence"][0]["severity"] == "warning"
