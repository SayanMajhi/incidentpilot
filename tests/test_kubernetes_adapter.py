"""Kubernetes adapter tests. No cluster and no `kubernetes` package required.

The real KubernetesGateway and KubernetesInfrastructure run against
tests/k8s_fakes.FakeCluster, which stands in for CoreV1Api / AppsV1Api and
records every call made.
"""

import sys
import types

import pytest

from backend.agent.controller import IncidentController
from backend.agent.decision import DecisionEngine, collect_evidence
from backend.infrastructure import (
    InfrastructureError,
    InfrastructureSafetyError,
    create_infrastructure,
    reset_infrastructure_cache,
    selected_environment,
)
from backend.infrastructure.kubernetes.adapter import (
    POD_TEMPLATE_HASH_LABEL,
    RESTARTED_AT_ANNOTATION,
    KubernetesInfrastructure,
)
from backend.infrastructure.kubernetes.config import (
    ALLOWED_NAMESPACE,
    VERSION_LABEL,
    KubernetesSettings,
)
from backend.infrastructure.kubernetes.gateway import KubernetesGateway
from backend.infrastructure.simulator import SimulatorInfrastructure
from backend.safety.policy import policy
from backend.shared import slo
from tests.k8s_fakes import NAME, FakeApiException, FakeCluster, make_adapter


# ===========================================================================
# Adapter initialization
# ===========================================================================

def test_default_settings_target_the_demo_workload_in_the_incidentpilot_namespace():
    settings = KubernetesSettings()

    assert settings.namespace == ALLOWED_NAMESPACE == "incidentpilot"
    assert settings.deployment == NAME
    assert settings.service == NAME
    assert (settings.min_replicas, settings.max_replicas) == (slo.MIN_REPLICAS, slo.MAX_REPLICAS)
    assert "kind-incidentpilot" in settings.allowed_contexts


def test_settings_are_read_from_environment_variables():
    settings = KubernetesSettings.from_env({
        "K8S_DEPLOYMENT": "checkout",
        "K8S_ALLOWED_DEPLOYMENTS": "checkout, payments",
        "K8S_SERVICE": "checkout",
        "K8S_ALLOWED_SERVICES": "checkout",
        "K8S_CONTEXT": "minikube",
        "K8S_MAX_REPLICAS": "3",
        "K8S_PROBE_SAMPLES": "2",
    })

    assert settings.deployment == "checkout"
    assert settings.allowed_deployments == ("checkout", "payments")
    assert settings.context == "minikube"
    assert settings.max_replicas == 3
    assert settings.probe_samples == 2


def test_creating_the_adapter_does_not_contact_the_cluster(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("connect() must not be called at construction")

    monkeypatch.setattr(KubernetesGateway, "connect", classmethod(refuse))

    adapter = KubernetesInfrastructure(settings=KubernetesSettings())

    assert adapter.name == "kubernetes"
    assert adapter.supports_scenario_injection is False
    assert adapter.describe() == {
        "environment": "kubernetes",
        "namespace": "incidentpilot",
        "deployment": NAME,
        "service": NAME,
        "context": None,
        "connected": False,
        "replicas": {"min": slo.MIN_REPLICAS, "max": slo.MAX_REPLICAS},
    }


def test_environment_selection_defaults_to_simulator(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert selected_environment() == "simulator"
    assert isinstance(create_infrastructure(), SimulatorInfrastructure)


def test_environment_selection_builds_the_kubernetes_adapter_lazily(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "Kubernetes")
    monkeypatch.setattr(
        KubernetesGateway, "connect",
        classmethod(lambda *_: (_ for _ in ()).throw(AssertionError("no connection expected"))),
    )

    infrastructure = create_infrastructure()

    assert isinstance(infrastructure, KubernetesInfrastructure)
    reset_infrastructure_cache()


def test_unknown_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(InfrastructureError, match="Unsupported ENVIRONMENT"):
        selected_environment()


def test_missing_kubernetes_package_gives_an_actionable_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "kubernetes", None)

    with pytest.raises(InfrastructureError, match="requirements-kubernetes.txt"):
        KubernetesGateway.connect(KubernetesSettings())


def _fake_kubernetes_package(monkeypatch, active_context):
    created = {"clients": 0}

    config = types.SimpleNamespace(
        list_kube_config_contexts=lambda: ([{"name": active_context}], {"name": active_context}),
        new_client_from_config=lambda context=None: created.__setitem__("clients", created["clients"] + 1) or object(),
    )
    client = types.SimpleNamespace(CoreV1Api=lambda api_client: object(), AppsV1Api=lambda api_client: object())
    exceptions = types.SimpleNamespace(ApiException=FakeApiException)

    package = types.ModuleType("kubernetes")
    package.client, package.config = client, config
    client_module = types.ModuleType("kubernetes.client")
    client_module.exceptions = exceptions
    exceptions_module = types.ModuleType("kubernetes.client.exceptions")
    exceptions_module.ApiException = FakeApiException

    monkeypatch.setitem(sys.modules, "kubernetes", package)
    monkeypatch.setitem(sys.modules, "kubernetes.client", client_module)
    monkeypatch.setitem(sys.modules, "kubernetes.client.exceptions", exceptions_module)
    return created


def test_connect_refuses_a_kubeconfig_context_that_is_not_allow_listed(monkeypatch):
    created = _fake_kubernetes_package(monkeypatch, active_context="arn:aws:eks:us-east-1:1234:cluster/prod")

    with pytest.raises(InfrastructureSafetyError, match="not in the allow-list"):
        KubernetesGateway.connect(KubernetesSettings())

    assert created["clients"] == 0, "no API client may be built for a refused context"


def test_connect_accepts_a_local_development_context(monkeypatch):
    created = _fake_kubernetes_package(monkeypatch, active_context="kind-incidentpilot")

    gateway = KubernetesGateway.connect(KubernetesSettings())

    assert gateway.context == "kind-incidentpilot"
    assert created["clients"] == 1


def test_an_explicit_context_must_also_be_allow_listed():
    with pytest.raises(InfrastructureSafetyError):
        KubernetesSettings(context="gke_company_prod")


# ===========================================================================
# Resource targeting
# ===========================================================================

def test_every_api_call_targets_only_the_configured_namespace_and_workload():
    adapter, cluster = make_adapter(FakeCluster(versions=("v40", "v41")))

    adapter.get_metrics()
    adapter.get_capacity()
    adapter.get_current_version()
    adapter.query_logs()
    adapter.get_deployment_history()
    adapter.restart_service()
    adapter.scale_service(2)
    adapter.rollback_deployment("v40")

    assert cluster.calls
    for call in cluster.calls:
        method, namespace, target = call[0], call[1], call[2]
        assert namespace == "incidentpilot", call
        if method in ("read_namespaced_deployment", "patch_namespaced_deployment",
                      "patch_namespaced_deployment_scale"):
            assert target == NAME, call
        if method == "connect_get_namespaced_service_proxy":
            assert target == f"{NAME}:http", call
        if method in ("list_namespaced_pod", "list_namespaced_replica_set"):
            assert target == f"app.kubernetes.io/name={NAME}", call


def test_deployment_outside_the_allow_list_is_rejected():
    with pytest.raises(InfrastructureSafetyError, match="allow-list"):
        KubernetesSettings(deployment="payments")

    with pytest.raises(InfrastructureSafetyError, match="allow-list"):
        KubernetesSettings(service="payments")


def test_gateway_refuses_non_allow_listed_resources_even_if_asked_directly():
    adapter, cluster = make_adapter()
    gateway = adapter.gateway

    with pytest.raises(InfrastructureSafetyError):
        gateway.read_deployment("incidentpilot", "payments")
    with pytest.raises(InfrastructureSafetyError):
        gateway.scale_deployment("incidentpilot", "coredns", 2)
    with pytest.raises(InfrastructureSafetyError):
        gateway.probe_service("incidentpilot", "kubernetes")

    assert cluster.calls == []


def test_replica_sets_owned_by_other_deployments_are_ignored():
    adapter, _ = make_adapter(FakeCluster(versions=("v40", "v41")))

    versions = [record["version"] for record in adapter.get_deployment_history()]

    assert versions == ["v40", "v41"]  # "unrelated-rs" (v1) is excluded


def test_unmanaged_deployment_can_be_observed_but_never_modified():
    adapter, cluster = make_adapter(FakeCluster(versions=("v40", "v41"), managed=False))

    assert adapter.get_current_version() == "v41"

    for action in (
            adapter.restart_service,
            lambda: adapter.scale_service(2),
            lambda: adapter.rollback_deployment("v40"),
    ):
        with pytest.raises(InfrastructureSafetyError, match="incidentpilot.io/managed"):
            action()

    assert cluster.mutating_calls() == []


def test_api_returning_a_different_deployment_is_refused():
    cluster = FakeCluster()
    cluster.returned_namespace = "default"
    adapter, _ = make_adapter(cluster)

    with pytest.raises(InfrastructureSafetyError, match="other than the configured target"):
        adapter.get_current_version()


# ===========================================================================
# Allowed actions
# ===========================================================================

def test_gateway_exposes_no_generic_execution_capability():
    public = {name for name in dir(KubernetesGateway) if not name.startswith("_")}

    assert public == {
        "connect",
        "read_namespace",
        "read_deployment",
        "list_pods",
        "list_replica_sets",
        "list_events",
        "read_pod_log",
        "probe_service",
        "replace_pod_template",
        "scale_deployment",
    }


def test_restart_only_stamps_the_restarted_at_annotation():
    adapter, cluster = make_adapter()

    result = adapter.restart_service()

    assert result["success"] is True and result["status"] == "completed"
    [(method, namespace, name, body)] = cluster.mutating_calls()
    assert (method, namespace, name) == ("patch_namespaced_deployment", "incidentpilot", NAME)
    assert body == {"spec": {"template": {"metadata": {"annotations": {
        RESTARTED_AT_ANNOTATION: result["restarted_at"],
    }}}}}


def test_scale_uses_the_scale_subresource():
    adapter, cluster = make_adapter()

    result = adapter.scale_service(3)

    assert result["success"] is True
    assert result["previous_replicas"] == 1 and result["current_replicas"] == 3
    assert cluster.mutating_calls() == [
        ("patch_namespaced_deployment_scale", "incidentpilot", NAME, {"spec": {"replicas": 3}}),
    ]
    assert adapter.get_capacity()["replicas"] == 3


def test_rollback_restores_the_pod_template_of_the_requested_version():
    adapter, cluster = make_adapter(FakeCluster(versions=("v40", "v41")))

    result = adapter.rollback_deployment("v40")

    assert result["success"] is True
    assert (result["previous_version"], result["current_version"]) == ("v41", "v40")
    [(_, _, _, body)] = cluster.mutating_calls()
    template = body["spec"]["template"]
    assert template["metadata"]["labels"][VERSION_LABEL] == "v40"
    assert POD_TEMPLATE_HASH_LABEL not in template["metadata"]["labels"]
    assert adapter.get_current_version() == "v40"


def test_pod_template_patch_cannot_carry_other_fields():
    adapter, cluster = make_adapter()

    with pytest.raises(InfrastructureSafetyError):
        adapter.gateway.replace_pod_template("incidentpilot", NAME, {"spec": {}, "status": {}})

    assert cluster.calls == []


def test_restarts_of_the_same_version_do_not_duplicate_history():
    adapter, _ = make_adapter(FakeCluster(versions=("v40", "v41")))

    adapter.restart_service()
    adapter.restart_service()

    history = adapter.get_deployment_history()
    assert [record["version"] for record in history] == ["v40", "v41"]
    assert history[-1]["status"] == "current"
    assert history[-1]["order"] > history[0]["order"]


# ===========================================================================
# Invalid target rejection
# ===========================================================================

def test_rollback_to_an_unknown_version_is_rejected_without_modification():
    adapter, cluster = make_adapter(FakeCluster(versions=("v40", "v41")))

    result = adapter.rollback_deployment("v99")

    assert result["success"] is False and result["status"] == "rejected"
    assert "v99" in result["message"]
    assert cluster.mutating_calls() == []


@pytest.mark.parametrize("version", ["v41; kubectl delete ns incidentpilot", "../v40", "", " v40", None, 40])
def test_malformed_rollback_targets_are_rejected(version):
    adapter, cluster = make_adapter(FakeCluster(versions=("v40", "v41")))

    result = adapter.rollback_deployment(version)

    assert result["status"] == "rejected"
    assert cluster.mutating_calls() == []


def test_rollback_to_the_running_version_is_rejected():
    adapter, cluster = make_adapter(FakeCluster(versions=("v40", "v41")))

    result = adapter.rollback_deployment("v41")

    assert result["status"] == "rejected"
    assert "already the running version" in result["message"]
    assert cluster.mutating_calls() == []


@pytest.mark.parametrize("selector", ["", "app", "app in (a,b)", "app!=x", "a=b;c"])
def test_gateway_rejects_non_equality_or_empty_label_selectors(selector):
    adapter, cluster = make_adapter()

    with pytest.raises(InfrastructureSafetyError):
        adapter.gateway.list_pods("incidentpilot", selector)

    assert cluster.calls == []


@pytest.mark.parametrize("pod", ["", "../etc", "Pod_Name", "a" * 64])
def test_gateway_rejects_invalid_pod_names_for_logs(pod):
    adapter, cluster = make_adapter()

    with pytest.raises(InfrastructureSafetyError):
        adapter.gateway.read_pod_log("incidentpilot", pod, "app", 10)

    assert cluster.calls == []


def test_probe_path_cannot_escape_the_service():
    with pytest.raises(InfrastructureSafetyError):
        KubernetesSettings(probe_path="/../../api/v1/secrets")
    with pytest.raises(InfrastructureSafetyError):
        KubernetesSettings(probe_path="http://example.com")


# ===========================================================================
# Namespace restriction
# ===========================================================================

@pytest.mark.parametrize("namespace", ["default", "kube-system", "production", "incidentpilot-prod", ""])
def test_settings_refuse_any_namespace_other_than_incidentpilot(namespace):
    with pytest.raises(InfrastructureSafetyError, match="incidentpilot"):
        KubernetesSettings(namespace=namespace)

    with pytest.raises(InfrastructureSafetyError):
        KubernetesSettings.from_env({"K8S_NAMESPACE": namespace or "x"})


@pytest.mark.parametrize("namespace", ["default", "kube-system", "production"])
def test_every_gateway_operation_refuses_other_namespaces_before_calling_the_api(namespace):
    adapter, cluster = make_adapter()
    gateway = adapter.gateway
    selector = f"app.kubernetes.io/name={NAME}"

    operations = [
        lambda: gateway.read_namespace(namespace),
        lambda: gateway.read_deployment(namespace, NAME),
        lambda: gateway.list_pods(namespace, selector),
        lambda: gateway.list_replica_sets(namespace, selector),
        lambda: gateway.list_events(namespace),
        lambda: gateway.read_pod_log(namespace, "pod-a", "app", 10),
        lambda: gateway.probe_service(namespace, NAME),
        lambda: gateway.replace_pod_template(namespace, NAME, {"metadata": {}}),
        lambda: gateway.scale_deployment(namespace, NAME, 2),
    ]
    for operation in operations:
        with pytest.raises(InfrastructureSafetyError, match="only 'incidentpilot' is permitted"):
            operation()

    assert cluster.calls == []


# ===========================================================================
# Replica bounds
# ===========================================================================

@pytest.mark.parametrize("replicas", [0, -1, 6, 100, True, 3.0, "3", None])
def test_out_of_bounds_or_non_integer_replicas_are_rejected_without_api_calls(replicas):
    adapter, cluster = make_adapter()

    result = adapter.scale_service(replicas)

    assert result["success"] is False and result["status"] == "rejected"
    assert cluster.calls == []


def test_gateway_enforces_replica_bounds_independently_of_the_adapter():
    adapter, cluster = make_adapter()

    for replicas in (0, 6, True):
        with pytest.raises(InfrastructureSafetyError, match="outside the permitted range"):
            adapter.gateway.scale_deployment("incidentpilot", NAME, replicas)

    assert cluster.calls == []


def test_replica_bounds_can_be_narrowed_but_never_widened():
    with pytest.raises(InfrastructureSafetyError):
        KubernetesSettings(max_replicas=slo.MAX_REPLICAS + 1)
    with pytest.raises(InfrastructureSafetyError):
        KubernetesSettings(min_replicas=0)
    with pytest.raises(InfrastructureSafetyError):
        KubernetesSettings.from_env({"K8S_MAX_REPLICAS": "10"})

    adapter, _ = make_adapter(settings=KubernetesSettings(max_replicas=3, probe_samples=1))
    assert adapter.scale_service(3)["success"] is True
    assert adapter.scale_service(4)["status"] == "rejected"


def test_safety_policy_never_approves_a_replica_count_the_adapter_rejects():
    adapter, _ = make_adapter()

    for replicas in range(-1, slo.MAX_REPLICAS + 4):
        if policy.allows("scale_service", replicas=replicas):
            assert adapter.scale_service(replicas)["success"] is True, replicas


# ===========================================================================
# Observation derived from the real cluster state
# ===========================================================================

def test_metrics_come_from_service_probes_and_pod_readiness():
    adapter, _ = make_adapter()

    metrics = adapter.get_metrics()

    assert metrics["status"] == "healthy"
    assert metrics["error_rate"] == 0.0
    assert 0 < metrics["latency_ms"] <= slo.RECOVERY_MAX_LATENCY_MS
    assert metrics["probe_samples"] == 3
    assert metrics["source"] == "kubernetes_service_probe"
    assert adapter.check_health() == {"status": "healthy", "is_healthy": True}


def test_failed_probes_and_unready_pods_are_reported_not_hidden():
    adapter, _ = make_adapter(FakeCluster(versions=("v41", "v42"), bad_versions={"v42"}))

    metrics = adapter.get_metrics()

    assert metrics["status"] == "down"
    assert metrics["error_rate"] == 1.0
    assert metrics["ready_replicas"] == 0
    assert adapter.get_capacity()["utilization"] is None  # not measured, not invented


def test_stalled_rollout_is_rendered_as_deployment_evidence():
    adapter, _ = make_adapter(FakeCluster(versions=("v41", "v42"), bad_versions={"v42"}))

    logs = adapter.query_logs()
    evidence = collect_evidence({
        "logs": logs,
        "current_version": adapter.get_current_version(),
        "metrics": adapter.get_metrics(),
    })

    messages = " | ".join(entry["message"] for entry in logs)
    assert "rollout of v42 failed to progress: ProgressDeadlineExceeded" in messages
    assert "ImagePullBackOff" in messages
    assert "logs:deployment_failure" in {item["id"] for item in evidence}


def test_healthy_workload_logs_carry_no_incident_evidence():
    adapter, _ = make_adapter()

    evidence = collect_evidence({"logs": adapter.query_logs(), "metrics": adapter.get_metrics()})

    assert [item for item in evidence if item["source"] == "logs"] == []


def test_connection_check_is_read_only_and_reports_the_target():
    adapter, cluster = make_adapter(FakeCluster(versions=("v40", "v41")))

    info = adapter.check_connection()

    assert info == {
        "context": "kind-incidentpilot",
        "namespace": "incidentpilot",
        "deployment": NAME,
        "managed": True,
        "version": "v41",
        "replicas": 1,
        "ready_replicas": 1,
    }
    assert cluster.mutating_calls() == []


def test_connection_check_tolerates_a_namespace_scoped_identity():
    cluster = FakeCluster()

    def forbidden(_name):
        raise FakeApiException(403, "Forbidden")

    cluster.read_namespace = forbidden
    adapter, _ = make_adapter(cluster)

    assert "not readable with this identity" in adapter.check_connection()["namespace"]

    def missing(_name):
        raise FakeApiException(404, "Not Found")

    cluster.read_namespace = missing
    with pytest.raises(InfrastructureError, match="HTTP 404"):
        adapter.check_connection()


def test_api_errors_surface_as_infrastructure_errors():
    cluster = FakeCluster()

    def unreachable(*_args, **_kwargs):
        raise ConnectionError("connection refused")

    cluster.read_namespaced_deployment = unreachable
    adapter, _ = make_adapter(cluster)

    with pytest.raises(InfrastructureError, match="Could not reach the Kubernetes API"):
        adapter.get_current_version()


# ===========================================================================
# The same controller, a different environment
# ===========================================================================

def test_the_same_incident_controller_remediates_a_kubernetes_workload():
    adapter, cluster = make_adapter(FakeCluster(versions=("v41", "v42"), bad_versions={"v42"}))
    controller = IncidentController(
        use_llm=False,
        deterministic_engine=DecisionEngine(),
        infrastructure=adapter,
    )

    result = controller.run_incident()

    assert result["status"] == "resolved"
    [attempt] = result["attempts"]
    assert attempt["detection"]["incident_detected"] is True
    assert attempt["diagnosis"]["probable_cause"] == "deployment_regression"
    assert (attempt["decision"]["action"], attempt["decision"]["target"]) == ("rollback_deployment", "v41")
    assert attempt["safety_result"] == {"action": "rollback_deployment", "checked": True, "allowed": True}
    assert attempt["verification"].recovered is True
    assert cluster.version == "v41"
    assert [call[0] for call in cluster.mutating_calls()] == ["patch_namespaced_deployment"]
