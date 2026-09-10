"""
Tests for the IncidentPilot remediation tools in tools/remediation.py.

These tests verify:
    - restart_service() executes and produces a verifiable effect.
    - rollback_deployment() accepts known versions and rejects unknown ones.
    - scale_service() accepts safe replica counts and rejects unsafe ones.
    - None of the remediation functions ever claim the overall incident
      is "resolved" or "fixed" in their returned messages/status.
"""

import sys
from pathlib import Path

import pytest

# Ensure the project root is importable regardless of the working
# directory pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator import service  # noqa: E402
from tools import diagnostics, remediation  # noqa: E402

# Words that would imply the overall incident has been declared fixed.
# Remediation actions must never use language like this - they may only
# describe whether the action itself succeeded.
_RESOLUTION_CLAIM_WORDS = ["resolved", "fixed", "incident is over", "all clear"]


def _assert_no_resolution_claim(result: dict) -> None:
    """Assert that a remediation result never claims the incident is resolved."""
    text = f"{result.get('status', '')} {result.get('message', '')}".lower()
    for banned_word in _RESOLUTION_CLAIM_WORDS:
        assert banned_word not in text, f"Unexpected resolution claim: {banned_word!r} in {text!r}"


@pytest.fixture(autouse=True)
def reset_state():
    """Reset the simulator and remediation module state before/after each test."""
    service.state = service._initial_state()
    remediation._current_replicas = 1
    yield
    service.state = service._initial_state()
    remediation._current_replicas = 1


# ---------------------------------------------------------------------------
# restart_service
# ---------------------------------------------------------------------------

def test_restart_service_reports_success():
    """restart_service() should report that the restart action succeeded."""
    result = remediation.restart_service()

    assert result["action"] == "restart_service"
    assert result["success"] is True
    assert result["status"] == "completed"


def test_restart_service_has_verifiable_effect_during_outage():
    """restart_service() should have a concrete, verifiable effect on metrics."""
    service.simulate_outage()
    assert diagnostics.check_health()["is_healthy"] is False

    remediation.restart_service()

    # The restart's simulated effect should be reflected in the metrics -
    # verified independently through the diagnostic tools, as intended.
    metrics = diagnostics.get_metrics()
    assert metrics["status"] == "healthy"
    assert metrics["error_rate"] == 0.01
    assert metrics["latency_ms"] == 100


def test_restart_service_does_not_claim_incident_resolved():
    """restart_service()'s result must not claim the incident is resolved."""
    result = remediation.restart_service()
    _assert_no_resolution_claim(result)


# ---------------------------------------------------------------------------
# rollback_deployment
# ---------------------------------------------------------------------------

def test_rollback_to_known_version_succeeds():
    """rollback_deployment() should succeed for a version in deployment history."""
    result = remediation.rollback_deployment("v40")

    assert result["action"] == "rollback_deployment"
    assert result["success"] is True
    assert result["status"] == "success"
    assert result["requested_version"] == "v40"
    assert result["previous_version"] == "v41"
    assert result["current_version"] == "v40"

    # The simulator's version should actually be updated.
    assert diagnostics.get_current_version() == "v40"


def test_rollback_to_unknown_version_is_rejected():
    """rollback_deployment() should reject a version not in deployment history."""
    result = remediation.rollback_deployment("v999")

    assert result["success"] is False
    assert result["status"] == "rejected"
    assert result["requested_version"] == "v999"
    assert result["current_version"] == "v41"

    # The simulator's version should remain unchanged.
    assert diagnostics.get_current_version() == "v41"


def test_rollback_deployment_does_not_claim_incident_resolved():
    """rollback_deployment()'s result must not claim the incident is resolved,
    whether it succeeds or is rejected."""
    success_result = remediation.rollback_deployment("v39")
    _assert_no_resolution_claim(success_result)

    rejected_result = remediation.rollback_deployment("not-a-real-version")
    _assert_no_resolution_claim(rejected_result)


# ---------------------------------------------------------------------------
# scale_service
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("replicas", [1, 3, 5])
def test_scale_service_accepts_safe_values(replicas):
    """scale_service() should accept replica counts within the safe range."""
    result = remediation.scale_service(replicas)

    assert result["action"] == "scale_service"
    assert result["success"] is True
    assert result["status"] == "success"
    assert result["requested_replicas"] == replicas
    assert result["current_replicas"] == replicas
    assert remediation.get_current_replicas() == replicas


@pytest.mark.parametrize("replicas", [0, -1, 6, 100])
def test_scale_service_rejects_unsafe_values(replicas):
    """scale_service() should reject replica counts outside the safe range."""
    result = remediation.scale_service(replicas)

    assert result["success"] is False
    assert result["status"] == "rejected"
    assert result["requested_replicas"] == replicas
    # Replica count should remain at its previous (default) value.
    assert result["current_replicas"] == 1
    assert remediation.get_current_replicas() == 1


def test_scale_service_does_not_claim_incident_resolved():
    """scale_service()'s result must not claim the incident is resolved,
    whether it succeeds or is rejected."""
    success_result = remediation.scale_service(3)
    _assert_no_resolution_claim(success_result)

    rejected_result = remediation.scale_service(10)
    _assert_no_resolution_claim(rejected_result)
