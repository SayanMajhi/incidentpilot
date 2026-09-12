"""Integration coverage for the dashboard-facing IncidentPilot API."""

import pytest
from fastapi.testclient import TestClient

from backend.agent.controller import controller
from backend.simulator import service
from backend.tools import remediation


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
    assert service.transient_fault_active() is False
    assert service.capacity_utilization() <= 1.0


def test_duplicate_incident_runs_are_rejected():
    assert service.run_lock.acquire(blocking=False)
    try:
        response = client.post("/run-incident")
    finally:
        service.run_lock.release()

    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


def test_incident_run_failure_is_reported_and_releases_the_lock(monkeypatch):
    def fail_run(*_args, **_kwargs):
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr(controller, "run_incident", fail_run)

    response = client.post("/run-incident")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Incident run failed. Check the backend logs for details."
    }
    assert service.run_state["running"] is False
    assert service.run_state["phase"] == "failed"
    assert service.run_lock.acquire(blocking=False)
    service.run_lock.release()


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


def test_config_exposes_the_thresholds_the_backend_enforces():
    """The dashboard reads its thresholds from here, so they must match
    the values the verifier and the safety policy actually use."""
    from backend.safety.policy import policy
    from backend.verification.verifier import verifier

    config = client.get("/config").json()

    assert config["recovery"]["max_error_rate"] == verifier.MAX_ERROR_RATE
    assert config["recovery"]["max_latency_ms"] == verifier.MAX_LATENCY_MS
    assert config["replicas"]["min"] == policy.MIN_REPLICAS
    assert config["replicas"]["max"] == policy.MAX_REPLICAS
    assert config["elevated"]["error_rate"] >= config["recovery"]["max_error_rate"]
    assert config["elevated"]["latency_ms"] >= config["recovery"]["max_latency_ms"]


def test_timeline_is_render_ready_and_carries_live_agent_phase():
    client.post("/simulate/outage")
    client.post("/run-incident")

    payload = client.get("/timeline").json()

    assert payload["status"] == "resolved"
    assert payload["attempt_count"] == len(payload["timeline"]) >= 1
    assert payload["agent"]["running"] is False

    attempt = payload["timeline"][0]
    for key in (
        "attempt",
        "observations",
        "detection",
        "diagnosis",
        "decision",
        "safety_result",
        "action_result",
        "verification",
    ):
        assert key in attempt, key
    assert "metrics" in attempt["observations"]


def test_timeline_is_idle_before_any_run():
    payload = client.get("/timeline").json()

    assert payload["status"] == "idle"
    assert payload["timeline"] == []
    assert payload["attempt_count"] == 0


def test_injecting_a_scenario_clears_the_previous_runs_agent_phase():
    """A stale phase next to `incident: null` would make the dashboard
    report progress for a run whose result has already been discarded."""
    client.post("/simulate/outage")
    client.post("/run-incident")
    assert client.get("/status").json()["agent"]["phase"] == "complete"

    client.post("/simulate/bad-deployment")

    status = client.get("/status").json()
    assert status["incident"] is None
    assert status["agent"]["phase"] == "idle"
    assert status["agent"]["attempt"] == 0


def test_safety_verdict_comes_from_the_policy_gate():
    client.post("/simulate/outage")

    result = client.post("/run-incident").json()["result"]

    for attempt in result["attempts"]:
        assert attempt["safety_result"]["checked"] is True
        assert attempt["safety_result"]["allowed"] is True
        assert attempt["action_result"]["policy_allowed"] is True
