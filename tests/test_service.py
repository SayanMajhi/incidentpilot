"""
Tests for the IncidentPilot simulated production service.

These tests use FastAPI's TestClient (backed by httpx) to exercise the
HTTP endpoints defined in simulator/service.py. Each test resets the
module-level state before running, so tests are independent of
execution order.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure the project root is importable regardless of the working
# directory pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator import service  # noqa: E402
from simulator.service import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset the simulated service to its initial healthy state.

    This fixture runs automatically before every test to guarantee
    each test starts from a known, deterministic baseline regardless
    of what previous tests did.
    """
    service.state = service._initial_state()
    yield
    service.state = service._initial_state()


def test_initial_service_is_healthy():
    """The service's in-memory state should start out healthy."""
    assert service.state.status == "healthy"
    assert service.state.error_rate == 0.01
    assert service.state.latency_ms == 100
    assert service.state.current_version == "v41"


def test_health_endpoint_returns_healthy():
    """GET /health should report 'healthy' before any simulation."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_metrics_endpoint_returns_normal_metrics():
    """GET /metrics should report normal baseline metrics."""
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["error_rate"] == 0.01
    assert body["latency_ms"] == 100


def test_version_endpoint_returns_v41():
    """GET /version should report the initial deployed version, v41."""
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"current_version": "v41"}


def test_simulate_outage_sets_status_down():
    """POST /simulate/outage should change the service status to down."""
    response = client.post("/simulate/outage")
    assert response.status_code == 200
    assert response.json()["state"]["status"] == "down"

    # Confirm it is reflected in /health too.
    health_response = client.get("/health")
    assert health_response.json() == {"status": "down"}


def test_simulate_outage_produces_abnormal_metrics():
    """POST /simulate/outage should produce clearly abnormal metrics."""
    client.post("/simulate/outage")

    response = client.get("/metrics")
    body = response.json()
    assert body["status"] == "down"
    assert body["error_rate"] == 0.70
    assert body["latency_ms"] == 1000

    # Version should remain unchanged by an outage.
    version_response = client.get("/version")
    assert version_response.json() == {"current_version": "v41"}


def test_simulate_recover_restores_healthy_state():
    """POST /simulate/recover should restore the service to healthy."""
    # First push the service into an outage.
    client.post("/simulate/outage")
    assert client.get("/health").json()["status"] == "down"

    # Then recover it.
    response = client.post("/simulate/recover")
    assert response.status_code == 200
    assert response.json()["state"]["status"] == "healthy"

    metrics_response = client.get("/metrics")
    body = metrics_response.json()
    assert body["status"] == "healthy"
    assert body["error_rate"] == 0.01
    assert body["latency_ms"] == 100


def test_simulate_bad_deployment_changes_version_to_v42():
    """POST /simulate/bad-deployment should deploy version v42."""
    response = client.post("/simulate/bad-deployment")
    assert response.status_code == 200
    assert response.json()["state"]["current_version"] == "v42"

    # Confirm it is reflected in /version too.
    version_response = client.get("/version")
    assert version_response.json() == {"current_version": "v42"}


def test_simulate_bad_deployment_makes_service_unhealthy():
    """POST /simulate/bad-deployment should change the service status to down."""
    response = client.post("/simulate/bad-deployment")
    assert response.status_code == 200
    assert response.json()["state"]["status"] == "down"

    # Confirm it is reflected in /health too.
    health_response = client.get("/health")
    assert health_response.json() == {"status": "down"}


def test_simulate_bad_deployment_produces_abnormal_error_rate():
    """POST /simulate/bad-deployment should push error_rate to 0.70."""
    client.post("/simulate/bad-deployment")

    response = client.get("/metrics")
    body = response.json()
    assert body["error_rate"] == 0.70


def test_simulate_bad_deployment_produces_abnormal_latency():
    """POST /simulate/bad-deployment should push latency_ms to 1000."""
    client.post("/simulate/bad-deployment")

    response = client.get("/metrics")
    body = response.json()
    assert body["latency_ms"] == 1000


def test_existing_recovery_still_works_after_bad_deployment():
    """POST /simulate/recover should still restore status/metrics to
    healthy after a bad deployment, without silently reverting the
    deployed version (recovery is not the same as a rollback)."""
    client.post("/simulate/bad-deployment")
    assert client.get("/health").json()["status"] == "down"

    response = client.post("/simulate/recover")
    assert response.status_code == 200
    assert response.json()["state"]["status"] == "healthy"

    metrics_response = client.get("/metrics")
    body = metrics_response.json()
    assert body["status"] == "healthy"
    assert body["error_rate"] == 0.01
    assert body["latency_ms"] == 100

    # The bad version stays deployed; recovery clears the incident
    # symptoms but does not roll back the code.
    version_response = client.get("/version")
    assert version_response.json() == {"current_version": "v42"}