"""Deterministic in-memory service used by the IncidentPilot demo.

The simulator owns causes, not scripted action sequences. Public symptoms are
derived from those hidden causes after every mutation, so the controller must
observe and reason about the state left by its previous action.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any, Literal

from pydantic import BaseModel, PrivateAttr

from backend.config import get_settings
from backend.shared import slo


HEALTHY_STATUS: Literal["healthy"] = "healthy"
DOWN_STATUS: Literal["down"] = "down"
HEALTHY_ERROR_RATE = slo.HEALTHY_ERROR_RATE
HEALTHY_LATENCY_MS = slo.HEALTHY_LATENCY_MS
OUTAGE_ERROR_RATE = slo.OUTAGE_ERROR_RATE
OUTAGE_LATENCY_MS = slo.OUTAGE_LATENCY_MS
INITIAL_VERSION = slo.INITIAL_VERSION
BAD_DEPLOYMENT_VERSION = slo.BAD_DEPLOYMENT_VERSION

# Demand is expressed in replica-equivalents: one replica serves one unit.
_SETTINGS = get_settings()
BASELINE_LOAD_UNITS = _SETTINGS.simulator_baseline_load_units
ADAPTIVE_LOAD_UNITS = _SETTINGS.simulator_adaptive_load_units


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ServiceState(BaseModel):
    status: Literal["healthy", "down"]
    error_rate: float
    latency_ms: int
    current_version: str

    # Hidden causes are private so neither telemetry nor API serialization can
    # reveal them to the controller.
    _transient_fault: bool = PrivateAttr(default=False)
    _deployment_regression: bool = PrivateAttr(default=False)
    _load_units: float = PrivateAttr(default=BASELINE_LOAD_UNITS)
    _replicas: int = PrivateAttr(default=slo.MIN_REPLICAS)


class SimulatorEnvironment:
    """Causal, thread-safe state machine behind simulator infrastructure."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.state = self.initial_state()
        self.scenario = "healthy"

    @staticmethod
    def initial_state() -> ServiceState:
        return ServiceState(
            status=HEALTHY_STATUS,
            error_rate=HEALTHY_ERROR_RATE,
            latency_ms=HEALTHY_LATENCY_MS,
            current_version=INITIAL_VERSION,
        )

    def public_state(self) -> dict[str, Any]:
        with self._lock:
            return self.state.model_dump()

    def _before(self) -> dict[str, Any]:
        return {
            **self.state.model_dump(),
            "replicas": self.state._replicas,
            "utilization": self.capacity_utilization(),
        }

    def _mutation(self, action: str, before: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": action,
            "observed_at": _now(),
            "before": before,
            "after": self._before(),
        }

    def transient_fault_active(self) -> bool:
        return self.state._transient_fault

    def deployment_regression_active(self) -> bool:
        return (
            self.state._deployment_regression
            and self.state.current_version == BAD_DEPLOYMENT_VERSION
        )

    def get_replicas(self) -> int:
        return self.state._replicas

    def capacity_utilization(self) -> float:
        return round(self.state._load_units / max(self.state._replicas, 1), 2)

    def cpu_percent(self) -> int:
        adaptive_load = self.state._load_units > BASELINE_LOAD_UNITS
        utilization = self.capacity_utilization()
        if self.transient_fault_active():
            return 94
        if self.deployment_regression_active():
            return 62
        if utilization > 1.0:
            return 91
        if adaptive_load:
            return 48
        return 36

    def memory_percent(self) -> int:
        adaptive_load = self.state._load_units > BASELINE_LOAD_UNITS
        utilization = self.capacity_utilization()
        if self.transient_fault_active():
            return 82
        if self.deployment_regression_active():
            return 64
        if utilization > 1.0:
            return 78
        if adaptive_load:
            return 44
        return 41

    def recompute(self) -> None:
        """Derive symptoms from the currently active causes."""
        utilization = self.capacity_utilization()
        if self.transient_fault_active() or self.deployment_regression_active():
            self.state.status = DOWN_STATUS
            self.state.error_rate = OUTAGE_ERROR_RATE
            self.state.latency_ms = OUTAGE_LATENCY_MS
        elif utilization > 1.0:
            self.state.status = DOWN_STATUS
            self.state.error_rate = round(1 - 1 / utilization, 2)
            self.state.latency_ms = min(
                OUTAGE_LATENCY_MS,
                int(HEALTHY_LATENCY_MS * utilization * 3),
            )
        else:
            self.state.status = HEALTHY_STATUS
            self.state.error_rate = HEALTHY_ERROR_RATE
            self.state.latency_ms = HEALTHY_LATENCY_MS

    def clear_causes(self) -> None:
        self.state._transient_fault = False
        self.state._deployment_regression = False
        self.state._load_units = BASELINE_LOAD_UNITS

    def reset(self) -> dict[str, Any]:
        with self._lock:
            before = self._before()
            self.state.status = HEALTHY_STATUS
            self.state.error_rate = HEALTHY_ERROR_RATE
            self.state.latency_ms = HEALTHY_LATENCY_MS
            self.state.current_version = INITIAL_VERSION
            self.state._replicas = slo.MIN_REPLICAS
            self.clear_causes()
            self.scenario = "healthy"
            self.recompute()
            return self._mutation("reset", before)

    def inject_outage(self) -> dict[str, Any]:
        with self._lock:
            before = self._before()
            self.reset()
            self.scenario = "generic_outage"
            self.state._transient_fault = True
            self.recompute()
            return self._mutation("inject_outage", before)

    def inject_bad_deployment(self) -> dict[str, Any]:
        with self._lock:
            before = self._before()
            self.reset()
            self.scenario = "bad_deployment"
            self.state.current_version = BAD_DEPLOYMENT_VERSION
            self.state._deployment_regression = True
            self.recompute()
            return self._mutation("inject_bad_deployment", before)

    def inject_adaptive_incident(self) -> dict[str, Any]:
        with self._lock:
            before = self._before()
            self.reset()
            self.scenario = "adaptive_incident"
            self.state.current_version = INITIAL_VERSION
            self.state._transient_fault = True
            self.state._load_units = ADAPTIVE_LOAD_UNITS
            self.state._replicas = slo.MIN_REPLICAS
            self.recompute()
            return self._mutation("inject_adaptive_incident", before)

    def inject_capacity_incident(self, load_units: float = 2.5) -> dict[str, Any]:
        """Create visible pressure, useful for partial-recovery verification."""
        with self._lock:
            before = self._before()
            self.reset()
            self.scenario = "capacity_incident"
            self.state._load_units = max(float(load_units), BASELINE_LOAD_UNITS)
            self.recompute()
            return self._mutation("inject_capacity_incident", before)

    def clear_transient_failure(self) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            before = self._before()
            self.state._transient_fault = False
            self.recompute()
            return self.state.status == HEALTHY_STATUS, self._mutation("restart_service", before)

    def rollback(self, version: str) -> dict[str, Any]:
        with self._lock:
            before = self._before()
            fixes_regression = self.deployment_regression_active() and version != BAD_DEPLOYMENT_VERSION
            self.state.current_version = version
            if fixes_regression:
                self.state._deployment_regression = False
            self.recompute()
            mutation = self._mutation("rollback_deployment", before)
            mutation["fixed_regression"] = fixes_regression
            return mutation

    def scale(self, replicas: int) -> dict[str, Any]:
        with self._lock:
            before = self._before()
            self.state._replicas = replicas
            self.recompute()
            return self._mutation("scale_service", before)


simulator = SimulatorEnvironment()
