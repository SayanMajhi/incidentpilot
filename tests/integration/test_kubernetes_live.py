"""Live tests against a local Kubernetes cluster.

Skipped unless explicitly enabled, so plain ``pytest`` never needs a cluster:

    RUN_K8S_INTEGRATION=1 pytest -m kubernetes            # read-only checks
    RUN_K8S_INTEGRATION=1 RUN_K8S_MUTATING=1 pytest -m kubernetes

Prerequisites: the kind cluster, namespace and demo workload from
docs/kubernetes.md, and ``pip install -r requirements-kubernetes.txt``.
The mutating test only scales the demo Deployment and restores its original
replica count afterwards.
"""

import os
import time

import pytest

from backend.infrastructure.kubernetes import KubernetesInfrastructure, KubernetesSettings

pytestmark = [
    pytest.mark.kubernetes,
    pytest.mark.skipif(
        os.getenv("RUN_K8S_INTEGRATION") != "1",
        reason="Set RUN_K8S_INTEGRATION=1 to run against a local Kubernetes cluster.",
    ),
]

mutating = pytest.mark.skipif(
    os.getenv("RUN_K8S_MUTATING") != "1",
    reason="Set RUN_K8S_MUTATING=1 to allow scaling the demo Deployment.",
)


@pytest.fixture(scope="module")
def adapter():
    return KubernetesInfrastructure(settings=KubernetesSettings.from_env())


def test_connects_to_an_allow_listed_context_and_finds_the_workload(adapter):
    connection = adapter.check_connection()

    assert connection["context"] in adapter.settings.allowed_contexts
    assert connection["deployment"] == adapter.settings.deployment
    assert connection["managed"] is True


def test_observation_contract_matches_the_simulator(adapter):
    metrics = adapter.get_metrics()
    assert metrics["status"] in ("healthy", "down")
    assert 0.0 <= metrics["error_rate"] <= 1.0
    assert metrics["latency_ms"] > 0

    health = adapter.check_health()
    assert set(health) == {"status", "is_healthy"}

    assert isinstance(adapter.get_current_version(), str)

    capacity = adapter.get_capacity()
    assert capacity["replicas"] >= 1

    history = adapter.get_deployment_history()
    assert history
    assert [record["order"] for record in history] == sorted(record["order"] for record in history)

    for entry in adapter.query_logs():
        assert set(entry) == {"timestamp", "level", "message"}


@mutating
def test_scaling_round_trip_within_bounds(adapter):
    original = adapter.get_capacity()["replicas"]
    target = 2 if original != 2 else 1

    try:
        result = adapter.scale_service(target)
        assert result["success"] is True

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if adapter.get_capacity()["replicas"] == target:
                break
            time.sleep(2)
        assert adapter.get_capacity()["replicas"] == target
    finally:
        adapter.scale_service(original)
