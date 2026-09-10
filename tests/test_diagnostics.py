"""
Tests for the IncidentPilot diagnostic tools in tools/diagnostics.py.

These tests exercise each diagnostic function directly (no HTTP layer
involved) against the simulator's in-memory state, in both the healthy
and outage states where applicable. Assertions check actual returned
data/values, not just that the functions run without raising.
"""

import sys
from pathlib import Path

import pytest

# Ensure the project root is importable regardless of the working
# directory pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator import service  # noqa: E402
from tools import diagnostics  # noqa: E402


@pytest.fixture(autouse=True)
def reset_state():
    """Reset the simulator to its initial healthy state before/after each test."""
    service.state = service._initial_state()
    yield
    service.state = service._initial_state()


# ---------------------------------------------------------------------------
# get_metrics
# ---------------------------------------------------------------------------

def test_get_metrics_healthy():
    """get_metrics() should reflect the healthy baseline metrics."""
    metrics = diagnostics.get_metrics()
    assert metrics == {
        "status": "healthy",
        "error_rate": 0.01,
        "latency_ms": 100,
    }


def test_get_metrics_outage():
    """get_metrics() should reflect abnormal metrics during an outage."""
    service.simulate_outage()

    metrics = diagnostics.get_metrics()
    assert metrics["status"] == "down"
    assert metrics["error_rate"] == 0.70
    assert metrics["latency_ms"] == 1000


# ---------------------------------------------------------------------------
# check_health
# ---------------------------------------------------------------------------

def test_check_health_healthy():
    """check_health() should report the service as healthy initially."""
    health = diagnostics.check_health()
    assert health["status"] == "healthy"
    assert health["is_healthy"] is True


def test_check_health_outage():
    """check_health() should report the service as unhealthy during an outage."""
    service.simulate_outage()

    health = diagnostics.check_health()
    assert health["status"] == "down"
    assert health["is_healthy"] is False


def test_check_health_after_recovery():
    """check_health() should report healthy again after recovery."""
    service.simulate_outage()
    service.simulate_recover()

    health = diagnostics.check_health()
    assert health["status"] == "healthy"
    assert health["is_healthy"] is True


# ---------------------------------------------------------------------------
# get_current_version
# ---------------------------------------------------------------------------

def test_get_current_version_initial():
    """get_current_version() should return the initial version, v41."""
    assert diagnostics.get_current_version() == "v41"


def test_get_current_version_unchanged_during_outage():
    """An outage should not change the reported deployment version."""
    service.simulate_outage()
    assert diagnostics.get_current_version() == "v41"


# ---------------------------------------------------------------------------
# query_logs
# ---------------------------------------------------------------------------

def test_query_logs_healthy_returns_normal_logs():
    """query_logs() should return normal INFO-level logs when healthy."""
    logs = diagnostics.query_logs()

    assert len(logs) > 0
    assert all("timestamp" in entry and "level" in entry and "message" in entry for entry in logs)
    # Healthy logs should contain no ERROR entries.
    assert all(entry["level"] != "ERROR" for entry in logs)
    assert any(entry["level"] == "INFO" for entry in logs)


def test_query_logs_outage_returns_error_logs():
    """query_logs() should return realistic error logs during an outage."""
    service.simulate_outage()

    logs = diagnostics.query_logs()

    assert len(logs) > 0
    assert all("timestamp" in entry and "level" in entry and "message" in entry for entry in logs)
    # Outage logs must contain at least one ERROR entry with diagnostic detail.
    error_logs = [entry for entry in logs if entry["level"] == "ERROR"]
    assert len(error_logs) > 0
    assert any("timeout" in entry["message"].lower() or "error" in entry["message"].lower() for entry in error_logs)


def test_query_logs_is_deterministic():
    """query_logs() should return identical output across repeated calls."""
    first_call = diagnostics.query_logs()
    second_call = diagnostics.query_logs()
    assert first_call == second_call

    service.simulate_outage()
    third_call = diagnostics.query_logs()
    fourth_call = diagnostics.query_logs()
    assert third_call == fourth_call


def test_query_logs_returns_independent_copies():
    """Mutating a returned log list should not affect subsequent calls."""
    logs = diagnostics.query_logs()
    logs.append({"timestamp": "x", "level": "DEBUG", "message": "injected"})

    fresh_logs = diagnostics.query_logs()
    assert {"timestamp": "x", "level": "DEBUG", "message": "injected"} not in fresh_logs


def test_query_logs_healthy_state_returns_healthy_logs():
    """query_logs() should return only healthy/INFO evidence while the
    service is healthy, even though a bad deployment scenario exists
    elsewhere in the simulator."""
    logs = diagnostics.query_logs()

    assert len(logs) > 0
    assert all(entry["level"] != "ERROR" for entry in logs)
    messages = " ".join(entry["message"] for entry in logs).lower()
    assert "v42" not in messages


def test_query_logs_bad_deployment_returns_deployment_evidence():
    """query_logs() should return deployment-specific evidence once the
    bad-deployment scenario is active."""
    service.simulate_bad_deployment()

    logs = diagnostics.query_logs()

    assert len(logs) > 0
    assert all("timestamp" in entry and "level" in entry and "message" in entry for entry in logs)
    messages = " ".join(entry["message"] for entry in logs).lower()
    assert "v42" in messages
    assert "503" in messages
    assert "error rate" in messages or "latency" in messages


def test_query_logs_bad_deployment_contains_v42():
    """Bad-deployment logs must explicitly reference the deployed
    version, v42, so an agent can tie the incident to that deployment."""
    service.simulate_bad_deployment()

    logs = diagnostics.query_logs()
    assert any("v42" in entry["message"] for entry in logs)


def test_query_logs_bad_deployment_contains_failure_evidence():
    """Bad-deployment logs must contain ERROR-level entries describing
    application failures and HTTP 503s caused by the deployment."""
    service.simulate_bad_deployment()

    logs = diagnostics.query_logs()
    error_logs = [entry for entry in logs if entry["level"] == "ERROR"]

    assert len(error_logs) > 0
    assert any("application failures" in entry["message"].lower() for entry in error_logs)
    assert any("503" in entry["message"] for entry in error_logs)


def test_query_logs_generic_outage_is_unaffected_by_bad_deployment_logs():
    """A generic outage (not the bad-deployment scenario) must not be
    mistaken for the bad deployment: it should not mention v42."""
    service.simulate_outage()

    logs = diagnostics.query_logs()
    messages = " ".join(entry["message"] for entry in logs).lower()
    assert "v42" not in messages


# ---------------------------------------------------------------------------
# get_deployment_history
# ---------------------------------------------------------------------------

def test_get_deployment_history_structure():
    """get_deployment_history() should return well-formed deployment records."""
    history = diagnostics.get_deployment_history()

    assert len(history) >= 1
    for record in history:
        assert "version" in record
        assert "order" in record
        assert "timestamp" in record
        assert "status" in record


def test_get_deployment_history_most_recent_is_current_version():
    """The most recent deployment (highest 'order') should match the current version."""
    history = diagnostics.get_deployment_history()

    most_recent = max(history, key=lambda record: record["order"])
    assert most_recent["version"] == diagnostics.get_current_version()


def test_get_deployment_history_order_is_unique_and_increasing():
    """Deployment 'order' values should be unique, enabling clear recency ranking."""
    history = diagnostics.get_deployment_history()

    orders = [record["order"] for record in history]
    assert len(orders) == len(set(orders))
    assert orders == sorted(orders)