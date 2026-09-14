"""Compatibility facade for the extracted simulator and API.

New code should import :mod:`backend.simulator.environment` for simulator
state and :mod:`backend.api.app` for the HTTP application. This module keeps
the original public helpers available for scripts and older integrations.
"""

from __future__ import annotations

from threading import Lock

from backend.api.runtime import runtime
from backend.api.schemas import MetricsResponse, ServiceHealthResponse, SimulationActionResponse, VersionResponse
from backend.infrastructure import get_infrastructure
from backend.simulator.environment import (
    ADAPTIVE_LOAD_UNITS,
    BAD_DEPLOYMENT_VERSION,
    BASELINE_LOAD_UNITS,
    DOWN_STATUS,
    HEALTHY_ERROR_RATE,
    HEALTHY_LATENCY_MS,
    HEALTHY_STATUS,
    INITIAL_VERSION,
    OUTAGE_ERROR_RATE,
    OUTAGE_LATENCY_MS,
    ServiceState,
    simulator,
)


def _refresh_aliases() -> None:
    global state, active_scenario
    state = simulator.state
    active_scenario = simulator.scenario


def _initial_state() -> ServiceState:
    """Create and install a clean state (retained for test/script compatibility)."""
    simulator.state = simulator.initial_state()
    simulator.scenario = "healthy"
    _refresh_aliases()
    return simulator.state


state: ServiceState = simulator.state
active_scenario = simulator.scenario


def transient_fault_active() -> bool:
    return simulator.transient_fault_active()


def deployment_regression_active() -> bool:
    return simulator.deployment_regression_active()


def get_replicas() -> int:
    return simulator.get_replicas()


def capacity_utilization() -> float:
    return simulator.capacity_utilization()


def cpu_percent() -> int:
    return simulator.cpu_percent()


def memory_percent() -> int:
    return simulator.memory_percent()


def set_replicas(replicas: int) -> None:
    simulator.scale(replicas)
    _refresh_aliases()


def _clear_faults() -> None:
    simulator.clear_causes()
    _refresh_aliases()


def _recompute_service_health() -> None:
    # Fixtures occasionally replace ``service.state`` with ``_initial_state``;
    # keep the facade and extracted environment pointed at the same object.
    if simulator.state is not state:
        simulator.state = state
    simulator.recompute()
    _refresh_aliases()


def get_health() -> ServiceHealthResponse:
    _recompute_service_health()
    return ServiceHealthResponse(
        status=simulator.state.status,
        is_healthy=simulator.state.status == HEALTHY_STATUS,
    )


def get_metrics() -> MetricsResponse:
    _recompute_service_health()
    return MetricsResponse(
        error_rate=simulator.state.error_rate,
        latency_ms=simulator.state.latency_ms,
        status=simulator.state.status,
        cpu_percent=simulator.cpu_percent(),
        memory_percent=simulator.memory_percent(),
    )


def get_version() -> VersionResponse:
    _recompute_service_health()
    return VersionResponse(current_version=simulator.state.current_version)


def simulate_outage() -> SimulationActionResponse:
    mutation = simulator.inject_outage()
    _refresh_aliases()
    return SimulationActionResponse(
        message="Outage simulated.",
        state=simulator.public_state(),
        mutation=mutation,
    )


def clear_transient_failure() -> bool:
    recovered, _ = simulator.clear_transient_failure()
    _refresh_aliases()
    return recovered


def simulate_recover() -> SimulationActionResponse:
    mutation = simulator.reset()
    _refresh_aliases()
    return SimulationActionResponse(
        message="Service recovered.",
        state=simulator.public_state(),
        mutation=mutation,
    )


def simulate_bad_deployment() -> SimulationActionResponse:
    mutation = simulator.inject_bad_deployment()
    _refresh_aliases()
    return SimulationActionResponse(
        message=(
            f"Deployment of {BAD_DEPLOYMENT_VERSION} completed, but it "
            "introduced a production incident."
        ),
        state=simulator.public_state(),
        mutation=mutation,
    )


def simulate_adaptive_incident() -> SimulationActionResponse:
    mutation = simulator.inject_adaptive_incident()
    _refresh_aliases()
    return SimulationActionResponse(
        message="Adaptive compound incident simulated.",
        state=simulator.public_state(),
        mutation=mutation,
    )


def simulate_rollback(version: str) -> SimulationActionResponse:
    mutation = simulator.rollback(version)
    _refresh_aliases()
    return SimulationActionResponse(
        message=f"Rolled back to {version}; health follows remaining causes.",
        state=simulator.public_state(),
        mutation=mutation,
    )


def reset_incident():
    """Reset simulator state and latest runtime history."""
    if runtime.running:
        raise RuntimeError("Cannot reset while an incident run is active.")
    mutation = simulator.reset()
    runtime.reset()
    _refresh_aliases()
    return SimulationActionResponse(
        message="IncidentPilot simulator reset.",
        state=simulator.public_state(),
        mutation=mutation,
    )


def _infrastructure():
    return get_infrastructure()


# Deprecated process-global names remain readable for one release. Runtime
# ownership now lives in IncidentRuntime, so application code never mutates
# these objects.
run_lock = Lock()
run_state = runtime.snapshot()["agent"]
last_incident_result = None


from backend.api.app import app  # noqa: E402  (facade import after helpers)


__all__ = [
    "app",
    "state",
    "ServiceState",
    "simulate_outage",
    "simulate_recover",
    "simulate_bad_deployment",
    "simulate_adaptive_incident",
    "simulate_rollback",
    "reset_incident",
]

