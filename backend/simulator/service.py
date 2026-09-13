import logging
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, PrivateAttr
from dotenv import load_dotenv

from backend.shared import slo
from backend.agent.controller import DEFAULT_GOAL, MAX_ATTEMPTS

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="IncidentPilot Simulated Service",
    description="a deterministic,in_memory simulated production service",
    version="1.0.0",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)
HEALTHY_STATUS: Literal["healthy"] = "healthy"
DOWN_STATUS: Literal["down"] = "down"
HEALTHY_ERROR_RATE: float = slo.HEALTHY_ERROR_RATE
HEALTHY_LATENCY_MS: int = slo.HEALTHY_LATENCY_MS
OUTAGE_ERROR_RATE: float = slo.OUTAGE_ERROR_RATE
OUTAGE_LATENCY_MS: int = slo.OUTAGE_LATENCY_MS
INITIAL_VERSION: str = slo.INITIAL_VERSION
BAD_DEPLOYMENT_VERSION: str = slo.BAD_DEPLOYMENT_VERSION

# Demand on the service, in replica-equivalents: one replica serves one unit.
BASELINE_LOAD_UNITS: float = 0.6
ADAPTIVE_LOAD_UNITS: float = 2.5

class ServiceState(BaseModel):
    status: Literal["healthy", "down"]
    error_rate: float
    latency_ms: int
    current_version: str

    # Hidden fault model. These are the *causes* the simulator derives every
    # symptom from. They are private so they never appear in an API response:
    # the agent has to infer them from telemetry and logs, and remediation can
    # only change them through the effect a real action would have.
    _transient_fault: bool = PrivateAttr(default=False)
    _deployment_regression: bool = PrivateAttr(default=False)
    _load_units: float = PrivateAttr(default=BASELINE_LOAD_UNITS)
    _replicas: int = PrivateAttr(default=slo.MIN_REPLICAS)

def _initial_state() -> ServiceState:
    return ServiceState(
        status=HEALTHY_STATUS,
        error_rate=HEALTHY_ERROR_RATE,
        latency_ms=HEALTHY_LATENCY_MS,
        current_version=INITIAL_VERSION,
    )


# Module level mutable state, shared across all requests in this process.
state: ServiceState = _initial_state()

active_scenario = "healthy"


# Symptoms (status, error rate, latency, logs) are always *derived* from the
# hidden causes below; nothing sets them to a scripted value per scenario.
# That keeps cause and effect honest regardless of which remediation an agent
# tries, or in what order:
#   transient fault       hung workers; cleared by a restart
#   deployment regression the tracked bad version is running; cleared by
#                         rolling back away from it
#   capacity shortfall    demand exceeds provisioned replicas; cleared by
#                         scaling to enough replicas


def transient_fault_active() -> bool:
    """True while worker processes are hung (the kind of failure a restart clears)."""
    return state._transient_fault


def deployment_regression_active() -> bool:
    """True while the tracked bad deployment is the version actually running."""
    return state._deployment_regression and state.current_version == BAD_DEPLOYMENT_VERSION


def get_replicas() -> int:
    """Return the number of provisioned replicas."""
    return state._replicas


def capacity_utilization() -> float:
    """Demand as a fraction of provisioned capacity (above 1.0 is a shortfall)."""
    return round(state._load_units / max(state._replicas, 1), 2)


def cpu_percent() -> int:
    """Return deterministic CPU telemetry derived from active causes."""
    adaptive_load = state._load_units > BASELINE_LOAD_UNITS
    utilization = capacity_utilization()

    if transient_fault_active():
        # Hung workers mask every cause behind them. Keep the same CPU signal
        # regardless of hidden load or deployment state until restart.
        return 94
    if deployment_regression_active():
        return 62
    if utilization > 1.0:
        return 91
    if adaptive_load:
        return 48
    return 36


def memory_percent() -> int:
    """Return deterministic memory telemetry derived from active causes."""
    adaptive_load = state._load_units > BASELINE_LOAD_UNITS
    utilization = capacity_utilization()

    if transient_fault_active():
        return 82
    if deployment_regression_active():
        return 64
    if utilization > 1.0:
        return 78
    if adaptive_load:
        return 44
    return 41


def set_replicas(replicas: int) -> None:
    """Provision ``replicas`` replicas and let the symptoms follow."""
    state._replicas = replicas
    _recompute_service_health()


def _clear_faults() -> None:
    state._transient_fault = False
    state._deployment_regression = False
    state._load_units = BASELINE_LOAD_UNITS


def _recompute_service_health() -> None:
    """Derive status, error rate and latency from the active causes.

    Hung workers or a broken release take the service fully down. A capacity
    shortfall alone degrades it in proportion to how far demand exceeds
    capacity, so partial scaling produces a partial, still-unhealthy
    improvement rather than a binary switch.
    """
    utilization = capacity_utilization()

    if transient_fault_active() or deployment_regression_active():
        state.status = DOWN_STATUS
        state.error_rate = OUTAGE_ERROR_RATE
        state.latency_ms = OUTAGE_LATENCY_MS
    elif utilization > 1.0:
        state.status = DOWN_STATUS
        state.error_rate = round(1 - 1 / utilization, 2)
        state.latency_ms = min(OUTAGE_LATENCY_MS, int(HEALTHY_LATENCY_MS * utilization * 3))
    else:
        state.status = HEALTHY_STATUS
        state.error_rate = HEALTHY_ERROR_RATE
        state.latency_ms = HEALTHY_LATENCY_MS

# Latest IncidentPilot execution result and live agent-run progress. Defined
# here, before the endpoints that declare them global, so importing this
# module can never leave them unbound.
last_incident_result = None
run_lock = Lock()
run_state = {
    "run_id": None,
    "goal": DEFAULT_GOAL,
    "started_at": None,
    "running": False,
    "status": "idle",
    "phase": "idle",
    "attempt": 0,
    "max_attempts": MAX_ATTEMPTS,
    "history": [],
    "reason": None,
    "updated_at": None,
    "details": {},
}


def _reset_run_state() -> None:
    """Clear live agent progress back to idle.

    Called whenever the latest incident result is discarded, so that
    ``/status`` can never report a stale phase (for example "complete" from a
    previous run) alongside ``incident: null``.
    """
    run_state.update({
        "run_id": None,
        "goal": DEFAULT_GOAL,
        "started_at": None,
        "running": False,
        "status": "idle",
        "phase": "idle",
        "attempt": 0,
        "max_attempts": MAX_ATTEMPTS,
        "history": [],
        "reason": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "details": {},
    })


def _infrastructure():
    """The execution environment the agent operates against (see ENVIRONMENT)."""
    from backend.infrastructure import get_infrastructure

    return get_infrastructure()


def require_simulator() -> None:
    """Route dependency: simulator endpoints only exist in simulator mode.

    In Kubernetes mode these routes would read or mutate the in-memory
    simulator while the agent operates on the cluster, which would be
    actively misleading, so they are refused instead.
    """
    infrastructure = _infrastructure()
    if not infrastructure.supports_scenario_injection:
        raise HTTPException(
            status_code=409,
            detail=(
                "Simulator endpoints are unavailable while IncidentPilot is "
                f"running against the {infrastructure.name} environment."
            ),
        )


def _begin_scenario(scenario: str) -> None:
    """Activate a demo scenario and discard any previous run's results.

    Faults injected by an earlier scenario are cleared, so one scenario's
    hidden cause can never leak into the next one's evidence.
    """
    global active_scenario, last_incident_result

    active_scenario = scenario
    last_incident_result = None
    _clear_faults()
    _reset_run_state()


class HealthResponse(BaseModel):
    status: Literal["healthy", "down"]


class MetricsResponse(BaseModel):
    error_rate: float
    latency_ms: int
    status: Literal["healthy", "down"]
    cpu_percent: int
    memory_percent: int


class VersionResponse(BaseModel):
    current_version: str


class SimulationActionResponse(BaseModel):
    message: str
    state: ServiceState


@app.get("/health", response_model=HealthResponse, dependencies=[Depends(require_simulator)])
def get_health() -> HealthResponse:
    return HealthResponse(status=state.status)


@app.get("/metrics", response_model=MetricsResponse, dependencies=[Depends(require_simulator)])
def get_metrics() -> MetricsResponse:
    return MetricsResponse(
        error_rate=state.error_rate,
        latency_ms=state.latency_ms,
        status=state.status,
        cpu_percent=cpu_percent(),
        memory_percent=memory_percent(),
    )


@app.get("/version", response_model=VersionResponse, dependencies=[Depends(require_simulator)])
def get_version() -> VersionResponse:
    return VersionResponse(current_version=state.current_version)


@app.post("/simulate/outage", response_model=SimulationActionResponse, dependencies=[Depends(require_simulator)])
def simulate_outage() -> SimulationActionResponse:
    """Simulate a transient outage without changing the deployed version."""
    _begin_scenario("generic_outage")
    state._transient_fault = True
    _recompute_service_health()
    return SimulationActionResponse(
        message="Outage simulated.",
        state=state,
    )


def clear_transient_failure() -> bool:
    """Clear hung workers; other active causes remain unhealthy."""
    state._transient_fault = False
    _recompute_service_health()
    return state.status == HEALTHY_STATUS


@app.post("/simulate/recover", response_model=SimulationActionResponse, dependencies=[Depends(require_simulator)])
def simulate_recover() -> SimulationActionResponse:
    """Restore healthy simulator state without changing the version."""
    _begin_scenario("healthy")
    _recompute_service_health()
    return SimulationActionResponse(
        message="Service recovered.",
        state=state,
    )


@app.post("/simulate/bad-deployment", response_model=SimulationActionResponse, dependencies=[Depends(require_simulator)])
def simulate_bad_deployment() -> SimulationActionResponse:
    """Deploy the tracked broken version and derive its failure symptoms."""
    _begin_scenario("bad_deployment")
    state.current_version = BAD_DEPLOYMENT_VERSION
    state._deployment_regression = True
    _recompute_service_health()
    return SimulationActionResponse(
        message=(
            f"Deployment of {BAD_DEPLOYMENT_VERSION} completed, but it "
            "introduced a production incident: the service is now down "
            "with elevated error rate and latency."
        ),
        state=state,
    )


@app.post("/simulate/adaptive-incident", response_model=SimulationActionResponse, dependencies=[Depends(require_simulator)])
def simulate_adaptive_incident() -> SimulationActionResponse:
    """Start a compound incident designed to test agent adaptation.

    Hung workers initially hide the independent capacity shortfall, so a
    restart reveals new evidence without resolving the incident.
    """
    _begin_scenario("adaptive_incident")

    state.current_version = INITIAL_VERSION
    state._transient_fault = True
    state._load_units = ADAPTIVE_LOAD_UNITS
    state._replicas = slo.MIN_REPLICAS
    _recompute_service_health()

    return SimulationActionResponse(
        message=(
            "Adaptive incident simulated. The service is unhealthy "
            "and the first remediation attempt will not permanently "
            "resolve the underlying incident."
        ),
        state=state,
    )


@app.post("/simulate/rollback", response_model=SimulationActionResponse, dependencies=[Depends(require_simulator)])
def simulate_rollback(version: str) -> SimulationActionResponse:
    """Change version, healing only a regression caused by the old version."""
    fixes_regression = (
            deployment_regression_active() and version != BAD_DEPLOYMENT_VERSION
    )

    state.current_version = version

    if fixes_regression:
        state._deployment_regression = False
        _recompute_service_health()
        message = (
            f"Rolled back to {version}. This removed the "
            f"bad-deployment cause ({BAD_DEPLOYMENT_VERSION}); any other "
            "active cause still applies."
        )
    else:
        message = (
            f"Rolled back to {version}. This changed only the recorded "
            "version - the service's health was not tied to the "
            "previously deployed version, so status/metrics are unchanged."
        )

    return SimulationActionResponse(
        message=message,
        state=state,
    )

def _update_run_state(phase, details=None):
    details = details or {}
    run_state.update({
        "phase": phase,
        "attempt": details.get("attempt", run_state.get("attempt", 0)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "details": details,
    })
    for key in ("run_id", "goal", "started_at", "status", "history", "reason"):
        if key in details:
            run_state[key] = details[key]


@app.post("/run-incident")
def run_incident():
    """Run IncidentPilot against the current incident."""
    from backend.agent.controller import controller

    global last_incident_result
    if not run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An incident run is already in progress.")

    run_id = f"inc-{uuid4().hex}"
    started_at = datetime.now(timezone.utc).isoformat()
    run_state.update({
        "run_id": run_id,
        "goal": DEFAULT_GOAL,
        "started_at": started_at,
        "running": True,
        "status": "running",
        "phase": "observing",
        "attempt": 0,
        "history": [],
        "reason": None,
    })
    try:
        result = controller.run_incident(
            on_event=_update_run_state,
            run_id=run_id,
            goal=DEFAULT_GOAL,
            started_at=started_at,
        )
        if not isinstance(result, dict):
            raise RuntimeError("Incident controller returned an invalid result.")
        last_incident_result = result
        run_state.update({
            "status": result["status"],
            "phase": result["phase"],
            "attempt": result["attempt"],
            "history": result["history"],
            "reason": result["reason"],
        })
    except Exception as error:
        logger.exception("Incident controller execution failed")
        # Discard the previous run's result: reporting a stale "resolved"
        # incident under a "failed" phase would be actively misleading.
        last_incident_result = None
        _update_run_state("failed", {
            "status": "failed",
            "error": type(error).__name__,
        })
        raise HTTPException(
            status_code=500,
            detail="Incident run failed. Check the backend logs for details.",
        ) from error
    finally:
        run_state["running"] = False
        run_lock.release()

    return {
        "status": last_incident_result.get("status"),
        "result": last_incident_result,
    }


@app.get("/config")
def get_runtime_config():
    """Return the thresholds and action bounds enforced by the backend."""
    config = slo.as_dict()
    config["environment"] = _infrastructure().describe()
    return config


@app.get("/status")
def get_incident_status():
    """Read service and agent state through the configured adapter."""
    from backend.infrastructure import InfrastructureError

    infrastructure = _infrastructure()

    try:
        metrics = infrastructure.get_metrics()
        service_state = {
            "status": metrics["status"],
            "error_rate": metrics["error_rate"],
            "latency_ms": metrics["latency_ms"],
            "cpu_percent": metrics.get("cpu_percent"),
            "memory_percent": metrics.get("memory_percent"),
            "current_version": infrastructure.get_current_version(),
        }
        replicas = infrastructure.get_capacity()["replicas"]
        logs = infrastructure.query_logs()
        deployment_history = infrastructure.get_deployment_history()
    except InfrastructureError as error:
        logger.warning("Could not read %s environment: %s", infrastructure.name, error)
        raise HTTPException(
            status_code=503,
            detail=f"The {infrastructure.name} environment is unavailable: {error}",
        ) from error

    return {
        "service": service_state,
        "environment": infrastructure.name,
        "scenario": active_scenario if infrastructure.supports_scenario_injection else infrastructure.name,
        "replicas": replicas,
        "agent": dict(run_state),
        "diagnostics": {
            "logs": logs,
            "deployment_history": deployment_history,
        },
        "incident": last_incident_result,
    }


@app.get("/timeline")
def get_incident_timeline():
    """Return a render-ready view of the latest execution history."""
    attempts = []

    if last_incident_result:
        history = last_incident_result.get("attempts", []) or []

        for index, attempt in enumerate(history, start=1):
            verification = attempt.get("verification")
            if hasattr(verification, "to_dict"):
                verification = verification.to_dict()

            attempts.append({
                "attempt": attempt.get("attempt", index),
                "observations": attempt.get("observations", {}),
                "detection": attempt.get("detection", {}),
                "evidence": attempt.get("evidence", []),
                "new_evidence": attempt.get("new_evidence", []),
                "diagnosis": attempt.get("diagnosis", {}),
                "decision": attempt.get("decision", {}),
                "safety_result": attempt.get("safety_result", {}),
                "action_result": attempt.get("action_result", {}),
                "verification": verification,
                "evidence_after_action": attempt.get("evidence_after_action"),
                "new_evidence_after_action": attempt.get("new_evidence_after_action"),
            })

    return {
        "status": (
            last_incident_result.get("status")
            if last_incident_result
            else "idle"
        ),
        "run_id": last_incident_result.get("run_id") if last_incident_result else None,
        "goal": last_incident_result.get("goal", DEFAULT_GOAL) if last_incident_result else DEFAULT_GOAL,
        "started_at": last_incident_result.get("started_at") if last_incident_result else None,
        "reason": last_incident_result.get("reason") if last_incident_result else None,
        "trace_events": last_incident_result.get("trace_events", []) if last_incident_result else [],
        "agent": dict(run_state),
        "attempt_count": len(attempts),
        "timeline": attempts,
    }


@app.post("/reset")
def reset_incident():
    """
    Reset the simulated service to its initial healthy state.

    Outside simulator mode only the agent's run history is cleared: the API
    never deletes or re-creates cluster resources. Reset a Kubernetes
    workload by re-applying its manifest (see docs/kubernetes.md).
    """
    from backend.tools import remediation

    global last_incident_result, active_scenario

    if run_state["running"]:
        raise HTTPException(status_code=409, detail="Cannot reset while an incident run is active.")

    infrastructure = _infrastructure()

    last_incident_result = None
    _reset_run_state()

    if not infrastructure.supports_scenario_injection:
        return {
            "message": (
                "IncidentPilot run history cleared. The "
                f"{infrastructure.name} environment was not modified."
            ),
            "state": None,
        }

    _clear_faults()
    state.current_version = INITIAL_VERSION
    remediation.reset_replicas()

    active_scenario = "healthy"

    return {
        "message": "IncidentPilot simulator reset.",
        "state": state,
    }
