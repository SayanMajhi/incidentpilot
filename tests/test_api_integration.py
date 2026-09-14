"""Integration coverage for the dashboard-facing IncidentPilot API."""

import pytest
from fastapi.testclient import TestClient

from backend.agent.controller import controller
from backend.api.app import app
from backend.api.runtime import runtime
from backend.simulator.environment import simulator
from backend.tools import remediation
from tests.helpers import run_incident, wait_for_idle


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_runtime_state():
    original_llm_setting = controller.use_llm
    controller.use_llm = False
    client.post("/reset")
    yield
    wait_for_idle()
    client.post("/reset")
    controller.use_llm = original_llm_setting


def test_status_is_a_complete_live_dashboard_snapshot():
    client.post("/simulate/bad-deployment")

    response = client.get("/status")

    assert response.status_code == 200
    body = response.json()
    assert body["service"]["current_version"] == "v42"
    assert body["service"]["replicas"] == 1
    assert body["scenario"] == "bad_deployment"
    assert body["environment"]["mode"] == "simulator"
    assert body["environment"]["supports_scenario_injection"] is True
    assert body["agent"]["running"] is False
    assert body["agent"]["phase"] == "idle"
    assert body["diagnostics"]["logs"]
    assert body["latest_incident"] is None


def test_adaptive_api_run_rejects_false_success_then_recovers():
    client.post("/simulate/adaptive-incident")

    result = run_incident(client)

    assert result["run_id"].startswith("inc-")
    assert result["goal"]
    assert result["started_at"]
    assert result["status"] == "resolved"
    assert [item["decision"]["action"] for item in result["attempts"]] == [
        "restart_service",
        "scale_service",
    ]
    first, second = result["attempts"]
    assert first["verification"]["recovered"] is False
    assert second["verification"]["recovered"] is True
    assert first["detection"]["incident_detected"] is True
    assert second["diagnosis"]["probable_cause"] == "resource_exhaustion"
    assert first["verification"]["metrics_before"]["cpu_percent"] == 94
    assert first["verification"]["metrics_after"]["cpu_percent"] == 91
    assert second["verification"]["metrics_after"]["cpu_percent"] == 48
    assert second["verification"]["metrics_after"]["replicas"] == 3


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
        "cpu_percent": 36,
        "memory_percent": 41,
        "current_version": "v41",
        "replicas": 1,
        "ready_replicas": None,
        "utilization": 0.6,
    }
    assert status["scenario"] == "healthy"
    assert status["latest_incident"] is None
    assert simulator.transient_fault_active() is False
    assert simulator.capacity_utilization() <= 1.0


def test_duplicate_incident_runs_are_rejected(monkeypatch):
    release = []

    def slow_run(*_args, **_kwargs):
        while not release:
            pass
        return {"run_id": "inc-test", "status": "resolved", "attempts": [], "timeline": []}

    monkeypatch.setattr(controller, "run_incident", slow_run)
    assert client.post("/run-incident").status_code == 202
    try:
        response = client.post("/run-incident")
    finally:
        release.append(True)
        wait_for_idle()

    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


def test_incident_run_failure_becomes_visible_state_and_frees_the_runtime(monkeypatch):
    def fail_run(*_args, **_kwargs):
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr(controller, "run_incident", fail_run)

    assert client.post("/run-incident").status_code == 202
    wait_for_idle()

    agent = client.get("/status").json()["agent"]
    assert agent["running"] is False
    assert agent["status"] == "failed"
    assert agent["phase"] == "complete"
    # The failure is reported without leaking the internal exception message.
    assert "private implementation detail" not in str(client.get("/timeline").json())
    assert runtime.running is False


def test_mutating_the_simulator_during_a_run_is_rejected(monkeypatch):
    release = []

    def slow_run(*_args, **_kwargs):
        while not release:
            pass
        return {"run_id": "inc-test", "status": "resolved", "attempts": [], "timeline": []}

    monkeypatch.setattr(controller, "run_incident", slow_run)
    assert client.post("/run-incident").status_code == 202
    try:
        blocked = client.post("/simulate/outage")
        reset = client.post("/reset")
    finally:
        release.append(True)
        wait_for_idle()

    assert blocked.status_code == 409
    assert reset.status_code == 409


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
    assert config["agent"]["max_remediation_attempts"] == controller.MAX_ATTEMPTS
    assert config["environment"]["mode"] == "simulator"


def test_config_never_exposes_credentials():
    body = client.get("/config").text.lower()

    assert "hf_token" not in body
    assert "token" not in body
    assert "secret" not in body


def test_timeline_is_render_ready_and_carries_the_finished_run():
    client.post("/simulate/outage")
    run_incident(client)

    payload = client.get("/timeline").json()

    assert payload["status"] == "resolved"
    assert payload["run_id"].startswith("inc-")
    assert payload["goal"]
    assert payload["events"]
    assert payload["attempts"]

    timestamps = [event["timestamp"] for event in payload["events"]]
    assert timestamps == sorted(timestamps)
    for event in payload["events"]:
        for key in ("event_id", "timestamp", "incident_id", "phase", "event_type", "message"):
            assert key in event, key

    attempt = payload["attempts"][0]
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
    assert payload["events"] == []
    assert payload["attempts"] == []
    assert payload["run_id"] is None


def test_injecting_a_scenario_clears_the_previous_runs_agent_phase():
    """A stale phase next to a discarded result would make the dashboard
    report progress for a run that no longer exists."""
    client.post("/simulate/outage")
    run_incident(client)
    assert client.get("/status").json()["agent"]["phase"] == "complete"

    client.post("/simulate/bad-deployment")

    status = client.get("/status").json()
    assert status["latest_incident"] is None
    assert status["agent"]["phase"] == "idle"
    assert status["agent"]["attempt"] == 0


def test_safety_verdict_comes_from_the_policy_gate():
    client.post("/simulate/outage")

    result = run_incident(client)

    for attempt in result["attempts"]:
        assert attempt["safety_result"]["checked"] is True
        assert attempt["safety_result"]["allowed"] is True
        assert attempt["action_result"]["policy_allowed"] is True


def test_safety_evaluate_rejects_an_out_of_bounds_scale_without_executing_it():
    before = client.get("/status").json()["service"]["replicas"]

    response = client.post(
        "/safety/evaluate",
        json={"action": "scale_service", "target": 20, "namespace": "incidentpilot"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["executed"] is False
    assert body["decision"]["allowed"] is False
    assert body["decision"]["rule_id"]
    assert body["events"]
    assert client.get("/status").json()["service"]["replicas"] == before


def test_revision_increases_on_every_observable_state_change():
    first = client.get("/status").json()["revision"]

    client.post("/simulate/outage")
    second = client.get("/status").json()["revision"]
    run_incident(client)
    third = client.get("/status").json()["revision"]

    assert first < second < third
