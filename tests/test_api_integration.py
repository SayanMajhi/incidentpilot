"""Integration coverage for the dashboard-facing IncidentPilot API."""

import pytest
from fastapi.testclient import TestClient

from agent.controller import controller
from simulator import service
from tools import remediation


client = TestClient(service.app)


@pytest.fixture(autouse=True)
def clean_runtime_state():
    original_llm_setting = controller.use_llm
    controller.use_llm = False
    client.post("/reset")
    yield
    client.post("/reset")
    controller.use_llm = original_llm_setting


def test_status_is_a_complete_live_dashboard_snapshot():
    client.post("/simulate/bad-deployment")

    response = client.get("/status")

    assert response.status_code == 200
    body = response.json()
    assert body["service"]["current_version"] == "v42"
    assert body["scenario"] == "bad_deployment"
    assert body["replicas"] == 1
    assert body["agent"]["running"] is False
    assert body["diagnostics"]["logs"]
    assert body["incident"] is None


def test_adaptive_api_run_rejects_false_success_then_recovers():
    client.post("/simulate/adaptive-incident")

    response = client.post("/run-incident")

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"] == "resolved"
    assert [item["decision"]["action"] for item in result["attempts"]] == [
        "restart_service",
        "scale_service",
    ]
    assert result["attempts"][0]["verification"]["recovered"] is False
    assert result["attempts"][1]["verification"]["recovered"] is True
    assert result["attempts"][0]["detection"]["incident_detected"] is True
    assert result["attempts"][1]["diagnosis"]["probable_cause"] == "resource_exhaustion"


def test_reset_clears_all_cross_scenario_state():
    client.post("/simulate/adaptive-incident")
    remediation.scale_service(3)

    response = client.post("/reset")

    assert response.status_code == 200
    status = client.get("/status").json()
    assert status["service"] == {
        "status": "healthy",
        "error_rate": 0.01,
        "latency_ms": 100,
        "current_version": "v41",
    }
    assert status["scenario"] == "healthy"
    assert status["replicas"] == 1
    assert status["incident"] is None
    assert service.adaptive_incident_active is False


def test_duplicate_incident_runs_are_rejected():
    assert service.run_lock.acquire(blocking=False)
    try:
        response = client.post("/run-incident")
    finally:
        service.run_lock.release()

    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


def test_local_frontend_origin_is_allowed_by_cors():
    response = client.options(
        "/status",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
