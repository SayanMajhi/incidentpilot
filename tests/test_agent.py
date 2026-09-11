import pytest

from agent.decision import decision_engine
from simulator import service
from tools import diagnostics


# ---------------------------------------------------------------------------
# A. Bad deployment -> rollback_deployment, target = previous stable version
# ---------------------------------------------------------------------------

def test_bad_deployment_causes_rollback_to_previous_version():
    """Deployment evidence in the logs + deployment history should produce
    a rollback to the version immediately before the current one - never a
    hardcoded 'v41'."""

    observations = {
        "logs": [
            "Application error after deployment"
        ],
        "deployment_history": [
            {"version": "v41"},
            {"version": "v42"},
        ],
        "current_version": "v42",
        "metrics": {
            "error_rate": 0.70,
            "latency_ms": 1000,
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] == "rollback_deployment"
    assert decision["target"] == "v41"
    assert decision["confidence"] >= 0.8


def test_bad_deployment_with_structured_dict_logs():
    """Structured (dict) log entries, as returned by
    tools.diagnostics.query_logs(), must not crash the engine and should
    still be recognized as deployment evidence."""

    observations = {
        "logs": [
            {"timestamp": "t1", "level": "ERROR", "message": "Deployment v42 introduced application failures."},
            {"timestamp": "t2", "level": "ERROR", "message": "HTTP 503 responses increased after deployment v42."},
        ],
        "deployment_history": [
            {"version": "v41"},
            {"version": "v42"},
        ],
        "current_version": "v42",
        "metrics": {
            "error_rate": 0.70,
            "latency_ms": 1000,
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] == "rollback_deployment"
    assert decision["target"] == "v41"
    assert decision["confidence"] >= 0.8


def test_bad_deployment_full_integration_with_diagnostics_and_simulator():
    """End-to-end sanity check: drive the real simulator + diagnostics
    layer through the bad-deployment scenario and confirm the decision
    engine correctly picks the last known-good version from
    diagnostics.get_deployment_history(), even though the current
    (bad) version never appears in that history."""
    try:
        service.simulate_bad_deployment()

        observations = {
            "logs": diagnostics.query_logs(),
            "deployment_history": diagnostics.get_deployment_history(),
            "current_version": diagnostics.get_current_version(),
            "metrics": diagnostics.get_metrics(),
        }

        assert observations["current_version"] == "v42"
        # v42 is intentionally NOT in the recorded deployment history yet.
        assert "v42" not in [d["version"] for d in observations["deployment_history"]]

        decision = decision_engine.decide(observations)

        assert decision["action"] == "rollback_deployment"
        assert decision["target"] == "v41"
        assert decision["confidence"] >= 0.8
    finally:
        # Reset shared simulator state so other tests aren't affected.
        service.simulate_recover()
        service.state.current_version = service.INITIAL_VERSION


# ---------------------------------------------------------------------------
# B. Resource exhaustion -> scale_service
# ---------------------------------------------------------------------------

def test_resource_exhaustion_causes_scaling():

    observations = {
        "logs": [
            "Connection pool exhausted"
        ],
        "deployment_history": [
            {"version": "v41"}
        ],
        "current_version": "v41",
        "metrics": {
            "error_rate": 0.70,
            "latency_ms": 1000,
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] == "scale_service"
    assert decision["target"] == 3
    assert decision["confidence"] >= 0.8


def test_resource_exhaustion_memory_keyword_causes_scaling():

    observations = {
        "logs": [
            {"timestamp": "t1", "level": "ERROR", "message": "Out of memory: service killed."},
        ],
        "deployment_history": [
            {"version": "v41"}
        ],
        "current_version": "v41",
        "metrics": {
            "error_rate": 0.50,
            "latency_ms": 800,
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] == "scale_service"
    assert decision["target"] == 3
    assert decision["confidence"] >= 0.8


# ---------------------------------------------------------------------------
# C. Unknown incident -> escalate
# ---------------------------------------------------------------------------

def test_unknown_incident_causes_escalation():

    observations = {
        "logs": [
            "Unknown internal failure"
        ],
        "deployment_history": [
            {"version": "v41"}
        ],
        "current_version": "v41",
        "metrics": {
            "error_rate": 0.70,
            "latency_ms": 1000,
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] == "escalate"
    assert decision["target"] is None


# ---------------------------------------------------------------------------
# D. Current version with no previous version -> escalate, never invent a
#    rollback target
# ---------------------------------------------------------------------------

def test_no_previous_version_does_not_invent_rollback_target():
    """Deployment evidence is present, but the current version is the only
    (or oldest) entry in history, so there's nothing safe to roll back to.
    The engine must escalate instead of guessing a target."""

    observations = {
        "logs": [
            "Application error after deployment of v41"
        ],
        "deployment_history": [
            {"version": "v41"}
        ],
        "current_version": "v41",
        "metrics": {
            "error_rate": 0.70,
            "latency_ms": 1000,
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] == "escalate"
    assert decision["target"] is None


def test_no_previous_version_with_empty_deployment_history():
    """Deployment evidence with a completely empty history should also
    escalate rather than fabricate a target."""

    observations = {
        "logs": [
            "Deployment error: HTTP 503 responses increased."
        ],
        "deployment_history": [],
        "current_version": "v1",
        "metrics": {
            "error_rate": 0.70,
            "latency_ms": 1000,
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] == "escalate"
    assert decision["target"] is None


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------

def test_multiple_deployments_without_evidence_does_not_trigger_rollback():
    """A longer deployment history alone is not evidence of a bad
    deployment - there must be actual deployment-related evidence in the
    logs/metrics, per requirement 9."""

    observations = {
        "logs": [
            "Unrelated informational log entry"
        ],
        "deployment_history": [
            {"version": "v39"},
            {"version": "v40"},
            {"version": "v41"},
            {"version": "v42"},
        ],
        "current_version": "v42",
        "metrics": {
            "error_rate": 0.01,
            "latency_ms": 100,
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] == "escalate"
    assert decision["target"] is None

    # ---------------------------------------------------------------------------
# E. Adaptation after failed remediation
# ---------------------------------------------------------------------------

def test_failed_rollback_does_not_repeat_rollback():
    """If rollback completed but verification failed, the engine must
    adapt instead of blindly repeating the same rollback."""

    observations = {
        "logs": [
            "Deployment v42 introduced application failures.",
            "HTTP 503 responses increased after deployment v42.",
        ],
        "deployment_history": [
            {"version": "v41"},
            {"version": "v42"},
        ],
        "current_version": "v42",
        "metrics": {
            "error_rate": 0.70,
            "latency_ms": 1000,
        },
        "previous_attempt": {
            "action": "rollback_deployment",
            "target": "v41",
            "action_status": "completed",
            "verification_recovered": False,
            "verification_reason": "Service metrics are still unhealthy",
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] != "rollback_deployment"
    assert decision["action"] == "escalate"
    assert decision["target"] is None


def test_failed_scaling_does_not_repeat_scaling():
    """If scaling completed but verification failed, the engine must
    not blindly repeat the same scaling action."""

    observations = {
        "logs": [
            "Connection pool exhausted",
            "Service is still returning errors",
        ],
        "deployment_history": [
            {"version": "v41"},
        ],
        "current_version": "v41",
        "metrics": {
            "error_rate": 0.70,
            "latency_ms": 1000,
        },
        "previous_attempt": {
            "action": "scale_service",
            "target": 3,
            "action_status": "completed",
            "verification_recovered": False,
            "verification_reason": "Service metrics are still unhealthy",
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] != "scale_service"
    assert decision["action"] == "escalate"
    assert decision["target"] is None


def test_successful_previous_attempt_does_not_trigger_adaptation():
    """Adaptation should only occur when the previous attempt actually
    failed verification."""

    observations = {
        "logs": [
            "Application error after deployment",
        ],
        "deployment_history": [
            {"version": "v41"},
            {"version": "v42"},
        ],
        "current_version": "v42",
        "metrics": {
            "error_rate": 0.70,
            "latency_ms": 1000,
        },
        "previous_attempt": {
            "action": "rollback_deployment",
            "target": "v41",
            "action_status": "completed",
            "verification_recovered": True,
            "verification_reason": "Service metrics are healthy",
        },
    }

    decision = decision_engine.decide(observations)

    assert decision["action"] == "rollback_deployment"
    assert decision["target"] == "v41"