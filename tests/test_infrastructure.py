"""The infrastructure abstraction and the API's behaviour per environment."""

import ast
import inspect
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.agent import controller as controller_module
from backend.agent.controller import IncidentController
from backend.agent.decision import DecisionEngine
from backend.infrastructure import Infrastructure, get_infrastructure
from backend.infrastructure.simulator import SimulatorInfrastructure
from backend.simulator import service
from backend.tools import diagnostics, remediation
from tests.k8s_fakes import FakeCluster, make_adapter

client = TestClient(service.app)


@pytest.fixture(autouse=True)
def clean_simulator():
    service.reset_incident()
    yield
    service.reset_incident()


# ===========================================================================
# The controller is environment-agnostic
# ===========================================================================

def test_controller_imports_no_simulator_tool_or_kubernetes_code():
    tree = ast.parse(inspect.getsource(controller_module))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    forbidden = ("backend.simulator", "backend.tools", "backend.infrastructure.kubernetes",
                 "backend.infrastructure.simulator", "kubernetes")
    assert not [module for module in imported if module.startswith(forbidden)], imported

    source = inspect.getsource(controller_module).lower()
    for environment_specific in ("simulator", "kubernetes", "namespace", "replicaset"):
        assert environment_specific not in source, environment_specific


def test_default_infrastructure_is_the_simulator():
    assert isinstance(get_infrastructure(), SimulatorInfrastructure)
    assert isinstance(IncidentController(use_llm=False).infrastructure, SimulatorInfrastructure)


def test_simulator_adapter_delegates_to_the_existing_tools_at_call_time():
    infrastructure = SimulatorInfrastructure()
    service.simulate_outage()

    assert infrastructure.get_metrics() == diagnostics.get_metrics()
    assert infrastructure.query_logs() == diagnostics.query_logs()

    with patch.object(remediation, "restart_service", return_value={"patched": True}) as restart:
        assert infrastructure.restart_service() == {"patched": True}
    restart.assert_called_once_with()


class RecordingInfrastructure(Infrastructure):
    """A minimal third environment: proves the loop depends only on the interface."""

    name = "recording"

    def __init__(self):
        self.healthy = False
        self.calls = []

    def describe(self):
        return {"environment": self.name}

    def get_metrics(self):
        self.calls.append("get_metrics")
        if self.healthy:
            return {"status": "healthy", "error_rate": 0.0, "latency_ms": 20}
        return {"status": "down", "error_rate": 0.5, "latency_ms": 900}

    def check_health(self):
        status = "healthy" if self.healthy else "down"
        return {"status": status, "is_healthy": self.healthy}

    def get_current_version(self):
        return "v1"

    def get_capacity(self):
        return {"replicas": 1, "utilization": None, "telemetry": "unavailable"}

    def query_logs(self):
        self.calls.append("query_logs")
        if self.healthy:
            return []
        return [{"timestamp": "t", "level": "ERROR", "message": "upstream request timeout"}]

    def get_deployment_history(self):
        return [{"version": "v1", "order": 1, "timestamp": "t", "status": "current"}]

    def restart_service(self):
        self.calls.append("restart_service")
        self.healthy = True
        return {"action": "restart_service", "success": True, "status": "completed", "message": "ok"}

    def rollback_deployment(self, version):
        raise AssertionError("not expected")

    def scale_service(self, replicas):
        raise AssertionError("not expected")


def test_the_loop_runs_against_any_implementation_of_the_interface():
    infrastructure = RecordingInfrastructure()
    controller = IncidentController(
        use_llm=False, deterministic_engine=DecisionEngine(), infrastructure=infrastructure,
    )

    with patch.object(diagnostics, "get_metrics", side_effect=AssertionError("simulator must not be read")):
        result = controller.run_incident()

    assert result["status"] == "resolved"
    assert result["attempts"][0]["decision"]["action"] == "restart_service"
    assert "restart_service" in infrastructure.calls


def test_simulator_mode_still_resolves_every_demo_scenario_through_the_api():
    expectations = {
        "/simulate/outage": ["restart_service"],
        "/simulate/bad-deployment": ["rollback_deployment"],
        "/simulate/adaptive-incident": ["restart_service", "scale_service"],
    }

    for endpoint, expected_actions in expectations.items():
        client.post("/reset")
        assert client.post(endpoint).status_code == 200

        with patch.object(controller_module.controller, "use_llm", False):
            body = client.post("/run-incident").json()

        assert body["status"] == "resolved", endpoint
        assert [a["decision"]["action"] for a in body["result"]["attempts"]] == expected_actions

    status = client.get("/status").json()
    assert status["environment"] == "simulator"
    assert client.get("/config").json()["environment"]["environment"] == "simulator"


# ===========================================================================
# API in Kubernetes mode (fake cluster, no network)
# ===========================================================================

@pytest.fixture
def kubernetes_mode():
    adapter, cluster = make_adapter(FakeCluster(versions=("v41", "v42"), bad_versions={"v42"}))
    kubernetes_controller = IncidentController(
        use_llm=False, deterministic_engine=DecisionEngine(), infrastructure=adapter,
    )
    with patch.object(service, "_infrastructure", return_value=adapter), \
            patch.object(controller_module, "controller", kubernetes_controller):
        yield adapter, cluster


def test_status_and_config_report_the_kubernetes_workload(kubernetes_mode):
    _, cluster = kubernetes_mode

    status = client.get("/status")
    config = client.get("/config").json()

    assert status.status_code == 200
    body = status.json()
    assert body["environment"] == "kubernetes"
    assert body["scenario"] == "kubernetes"
    assert body["service"]["status"] == "down"
    assert body["service"]["current_version"] == "v42"
    assert body["replicas"] == 1
    assert [record["version"] for record in body["diagnostics"]["deployment_history"]] == ["v41", "v42"]
    assert config["environment"]["namespace"] == "incidentpilot"
    assert cluster.mutating_calls() == []


@pytest.mark.parametrize("method,endpoint", [
    ("post", "/simulate/outage"),
    ("post", "/simulate/bad-deployment"),
    ("post", "/simulate/adaptive-incident"),
    ("post", "/simulate/recover"),
    ("post", "/simulate/rollback?version=v41"),
    ("get", "/health"),
    ("get", "/metrics"),
    ("get", "/version"),
])
def test_simulator_endpoints_are_refused_in_kubernetes_mode(kubernetes_mode, method, endpoint):
    before = service.state.model_dump()

    response = getattr(client, method)(endpoint)

    assert response.status_code == 409
    assert "kubernetes" in response.json()["detail"]
    assert service.state.model_dump() == before


def test_reset_in_kubernetes_mode_clears_history_but_never_touches_the_cluster(kubernetes_mode):
    _, cluster = kubernetes_mode
    client.post("/run-incident")
    cluster.calls.clear()

    response = client.post("/reset")

    assert response.status_code == 200
    assert "was not modified" in response.json()["message"]
    assert cluster.calls == []
    assert client.get("/timeline").json()["status"] == "idle"


def test_run_incident_api_remediates_the_kubernetes_workload(kubernetes_mode):
    _, cluster = kubernetes_mode

    body = client.post("/run-incident").json()

    assert body["status"] == "resolved"
    assert [a["decision"]["action"] for a in body["result"]["attempts"]] == ["rollback_deployment"]
    assert cluster.version == "v41"
    assert client.get("/status").json()["service"]["status"] == "healthy"


def test_unreachable_cluster_returns_503_instead_of_crashing(kubernetes_mode):
    adapter, cluster = kubernetes_mode

    def unreachable(*_args, **_kwargs):
        raise ConnectionError("connection refused")

    cluster.read_namespaced_deployment = unreachable

    response = client.get("/status")

    assert response.status_code == 503
    assert "kubernetes environment is unavailable" in response.json()["detail"]
