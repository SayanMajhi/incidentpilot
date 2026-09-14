"""Endpoint behaviour of the simulator environment behind the HTTP API.

``/health`` is API liveness. The observed service is read through the
infrastructure adapter at ``/service/health``, ``/metrics`` and ``/version``,
so these tests assert on the adapter-backed endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.shared import slo
from backend.simulator.environment import simulator
from tests.helpers import reset_simulator


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    reset_simulator()
    yield
    reset_simulator()


def test_initial_service_is_healthy():
    assert simulator.state.status == "healthy"
    assert simulator.state.error_rate == slo.HEALTHY_ERROR_RATE
    assert simulator.state.latency_ms == slo.HEALTHY_LATENCY_MS
    assert simulator.state.current_version == slo.INITIAL_VERSION


def test_api_health_reports_liveness_and_the_selected_environment():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "simulator",
        "version": client.app.version,
    }


def test_service_health_reports_the_observed_service():
    response = client.get("/service/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "is_healthy": True}


def test_metrics_endpoint_returns_normal_metrics():
    body = client.get("/metrics").json()

    assert body["status"] == "healthy"
    assert body["error_rate"] == slo.HEALTHY_ERROR_RATE
    assert body["latency_ms"] == slo.HEALTHY_LATENCY_MS


def test_version_endpoint_returns_the_initial_version():
    response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {"current_version": slo.INITIAL_VERSION}


def test_simulate_outage_sets_status_down():
    response = client.post("/simulate/outage")

    assert response.status_code == 200
    assert response.json()["state"]["status"] == "down"
    assert client.get("/service/health").json() == {"status": "down", "is_healthy": False}


def test_simulate_outage_produces_abnormal_metrics():
    client.post("/simulate/outage")

    body = client.get("/metrics").json()

    assert body["status"] == "down"
    assert body["error_rate"] == slo.OUTAGE_ERROR_RATE
    assert body["latency_ms"] == slo.OUTAGE_LATENCY_MS
    # An outage does not change what is deployed.
    assert client.get("/version").json() == {"current_version": slo.INITIAL_VERSION}


def test_simulate_recover_restores_healthy_state():
    client.post("/simulate/outage")
    assert client.get("/service/health").json()["status"] == "down"

    response = client.post("/simulate/recover")

    assert response.status_code == 200
    assert response.json()["state"]["status"] == "healthy"
    body = client.get("/metrics").json()
    assert body["status"] == "healthy"
    assert body["error_rate"] == slo.HEALTHY_ERROR_RATE
    assert body["latency_ms"] == slo.HEALTHY_LATENCY_MS


def test_simulate_bad_deployment_changes_the_deployed_version():
    response = client.post("/simulate/bad-deployment")

    assert response.status_code == 200
    assert response.json()["state"]["current_version"] == slo.BAD_DEPLOYMENT_VERSION
    assert client.get("/version").json() == {
        "current_version": slo.BAD_DEPLOYMENT_VERSION
    }


def test_simulate_bad_deployment_makes_the_service_unhealthy():
    response = client.post("/simulate/bad-deployment")

    assert response.status_code == 200
    assert response.json()["state"]["status"] == "down"
    assert client.get("/service/health").json()["status"] == "down"

    body = client.get("/metrics").json()
    assert body["error_rate"] == slo.OUTAGE_ERROR_RATE
    assert body["latency_ms"] == slo.OUTAGE_LATENCY_MS


def test_recover_restores_the_full_healthy_baseline():
    """`/simulate/recover` is a demo reset, so it also restores the version."""
    client.post("/simulate/bad-deployment")
    assert client.get("/service/health").json()["status"] == "down"

    response = client.post("/simulate/recover")

    assert response.status_code == 200
    assert response.json()["state"]["status"] == "healthy"
    assert client.get("/metrics").json()["status"] == "healthy"
    assert client.get("/version").json() == {"current_version": slo.INITIAL_VERSION}


def test_rollback_to_an_unknown_version_is_rejected():
    client.post("/simulate/bad-deployment")

    response = client.post("/simulate/rollback", params={"version": "v99"})

    assert response.status_code == 422
    assert client.get("/version").json() == {
        "current_version": slo.BAD_DEPLOYMENT_VERSION
    }
