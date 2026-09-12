import logging
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, PrivateAttr
from dotenv import load_dotenv

from backend.shared import slo

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
# Status keywords. Every numeric threshold and version below is shared with
# the agent, the safety policy and the dashboard via backend.shared.slo.
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

#In memory service state
class ServiceState(BaseModel):
    """represents the current in memory state of the smulated service"""
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
    """build the initial health state of the simulated service,
    returns:
        ServiceState:a freshly constructed healthy state.
    """
    return ServiceState(
        status=HEALTHY_STATUS,
        error_rate=HEALTHY_ERROR_RATE,
        latency_ms=HEALTHY_LATENCY_MS,
        current_version=INITIAL_VERSION,
    )


# Module level mutable state, shared across all requests in this process.
state: ServiceState = _initial_state()

active_scenario = "healthy"


# ============================================================
# Causal fault model
# ============================================================
#
# Symptoms (status, error rate, latency, logs) are always *derived* from the
# hidden causes below; nothing sets them to a scripted value per scenario.
# That keeps cause and effect honest regardless of which remediation an agent
# tries, or in what order:
#
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
    "running": False,
    "phase": "idle",
    "attempt": 0,
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
        "running": False,
        "phase": "idle",
        "attempt": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "details": {},
    })


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

# Response models
class HealthResponse(BaseModel):
    """response model for the /health endpoint"""
    status: Literal["healthy", "down"]

class MetricsResponse(BaseModel):
    """response model for the /metrics endpoint"""
    error_rate: float
    latency_ms: int
    status: Literal["healthy", "down"]
class VersionResponse(BaseModel):
    """response model for the/version endpoint"""
    current_version: str
class SimulationActionResponse(BaseModel):
    """response model returned after a simulation action is applied"""
    message: str
    state: ServiceState
#endpoint
@app.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """returns the current health status of the simulated service

    returns:
        HealthResponse:the current status "healthy" / "down"
    """
    return HealthResponse(status=state.status)
@app.get("/metrics", response_model=MetricsResponse)
def get_metrics() -> MetricsResponse:
    """return the current operational metrics of the simulated service

    returns:
        MetricsResponse:error_rate,latency_ms,and status.
    """
    return MetricsResponse(
        error_rate=state.error_rate,
        latency_ms=state.latency_ms,
        status=state.status,
    )

@app.get("/version", response_model=VersionResponse)
def get_version() -> VersionResponse:
    """return the current deployment version of the simulated service
    returns:
        VersionResponse:the current deployed version string
    """
    return VersionResponse(current_version=state.current_version)
@app.post("/simulate/outage", response_model=SimulationActionResponse)
def simulate_outage() -> SimulationActionResponse:
    """simulate a production outage.

    sets the service into a "down" state with
    abnormal error rate and latency values the deployed version is
    left unchanged,since an outage is not assumed to be caused by a
    deployment in this simulation.

    returns:
        SimulationActionResponse:a confirmation message and the
        resulting service state.
    """
    _begin_scenario("generic_outage")
    state._transient_fault = True
    _recompute_service_health()
    return SimulationActionResponse(
        message="Outage simulated.",
        state=state,
    )


def clear_transient_failure() -> bool:
    """Clear transient unhealthy state, the way a process restart would.

    This is the simulator-internal effect of a restart, called by
    ``backend.tools.remediation.restart_service``. It is deliberately NOT an
    HTTP endpoint: nothing outside the remediation layer should be able to
    declare the service healthy.

    Cause and effect is preserved. A restart clears hung workers, but it
    cannot fix an incident with a different cause: a bad deployment that is
    still running, or demand that exceeds provisioned capacity, survives the
    restart and the service stays unhealthy.

    Returns:
        bool: True if the restart actually restored the healthy baseline,
        False if an incident cause survived the restart.
    """
    state._transient_fault = False
    _recompute_service_health()
    return state.status == HEALTHY_STATUS


@app.post("/simulate/recover", response_model=SimulationActionResponse)
def simulate_recover() -> SimulationActionResponse:
    """Restore the simulated service to its healthy baseline state.

    Resets status, error_rate and latency_ms to their healthy baseline
    values and clears the active scenario. The deployed version is left
    unchanged.
    """
    _begin_scenario("healthy")
    _recompute_service_health()
    return SimulationActionResponse(
        message="Service recovered.",
        state=state,
    )


@app.post("/simulate/bad-deployment", response_model=SimulationActionResponse)
def simulate_bad_deployment() -> SimulationActionResponse:
    """simulate a bad deployment that ships a new, broken version.

    deploys BAD_DEPLOYMENT_VERSION ("v42") as the current_version and,
    as a direct consequence of that deployment, puts the service into
    a "down" state with abnormal error rate and latency values. Unlike
    simulate_outage(), this scenario ties the incident to a specific
    version change, so a future agent can correlate the bad metrics
    with the deployment that caused them (e.g. via
    tools.diagnostics.get_deployment_history()).

    returns:
        SimulationActionResponse:a confirmation message describing
        both the deployment and the resulting incident, and the
        resulting service state.
    """
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

@app.post("/simulate/adaptive-incident", response_model=SimulationActionResponse)
def simulate_adaptive_incident() -> SimulationActionResponse:
    """
    Start a compound incident designed to test agent adaptation.

    Two independent causes are active at once:

    * hung worker processes, which a restart clears, and
    * a traffic surge that needs more capacity than the single provisioned
      replica, which only scaling clears.

    While the workers are hung, requests time out before they ever reach the
    connection pool, so the capacity shortfall produces no evidence of its
    own. A restart therefore succeeds as an action but the service stays
    unhealthy, and only then does resource-pressure evidence appear. Nothing
    here prescribes an order: scaling first and restarting second resolves
    it just as well, because each action removes exactly its own cause.
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

@app.post("/simulate/rollback", response_model=SimulationActionResponse)
def simulate_rollback(version: str) -> SimulationActionResponse:
    """Simulate rolling back the deployed version.

    This changes current_version unconditionally. Whether that change
    also heals the service depends on why the service was unhealthy in
    the first place, kept deterministic and tied to cause-and-effect
    rather than "every rollback fixes everything":

        - If the service is currently down BECAUSE of the tracked bad
          deployment (current_version == BAD_DEPLOYMENT_VERSION) and
          this call moves away from that version, the cause of the
          incident is removed, so the service deterministically
          recovers to its healthy baseline - mirroring how
          simulate_bad_deployment() tied the incident to the version
          in the first place.
        - Otherwise (e.g. the service is unhealthy for a reason never
          tied to the deployed version, such as simulate_outage(), or
          this call rolls back to the same bad version), only the
          recorded version changes. Status/error_rate/latency are left
          untouched, so a rollback cannot be assumed to fix an
          incident it didn't cause.

    Args:
        version: The version string to roll back to.

    Returns:
        SimulationActionResponse: a confirmation message and the
        resulting service state.
    """
    incident_caused_by_current_deployment = (
            deployment_regression_active() and version != BAD_DEPLOYMENT_VERSION
    )

    state.current_version = version

    if incident_caused_by_current_deployment:
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

# ============================================================
# IncidentPilot API
# ============================================================


def _update_run_state(phase, details=None):
    run_state.update({
        "phase": phase,
        "attempt": (details or {}).get("attempt", run_state.get("attempt", 0)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    })


@app.post("/run-incident")
def run_incident():
    """
    Run IncidentPilot against the current simulated incident.

    The controller investigates the service, chooses a remediation,
    passes it through the safety policy, executes it, verifies recovery,
    and adapts if necessary.
    """
    from backend.agent.controller import controller

    global last_incident_result
    if not run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An incident run is already in progress.")

    run_state.update({"running": True, "attempt": 0})
    _update_run_state("observing")
    try:
        result = controller.run_incident(on_event=_update_run_state)
        if not isinstance(result, dict):
            raise RuntimeError("Incident controller returned an invalid result.")
        last_incident_result = result
    except Exception as error:
        logger.exception("Incident controller execution failed")
        # Discard the previous run's result: reporting a stale "resolved"
        # incident under a "failed" phase would be actively misleading.
        last_incident_result = None
        _update_run_state("failed", {"error": type(error).__name__})
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
    """
    Return the SLO thresholds and action bounds the backend enforces.

    The dashboard reads this instead of hardcoding thresholds, so the numbers
    it displays are always the ones the agent and the safety policy actually
    use.
    """
    return slo.as_dict()


@app.get("/status")
def get_incident_status():
    """
    Return the current simulated service state and latest agent result.
    """
    from backend.tools import diagnostics
    from backend.tools.remediation import get_current_replicas

    return {
        "service": {
            "status": state.status,
            "error_rate": state.error_rate,
            "latency_ms": state.latency_ms,
            "current_version": state.current_version,
        },
        "scenario": active_scenario,
        "replicas": get_current_replicas(),
        "agent": dict(run_state),
        "diagnostics": {
            "logs": diagnostics.query_logs(),
            "deployment_history": diagnostics.get_deployment_history(),
        },
        "incident": last_incident_result,
    }


@app.get("/timeline")
def get_incident_timeline():
    """
    Return the agent's execution history in dashboard-friendly form.

    This is the endpoint the dashboard's Agent Execution Timeline reads. It
    projects the latest run into one flat, render-ready shape per attempt -
    the observations, detection signals, diagnosis, decision, safety verdict,
    action outcome and verification - alongside the live agent phase, so the
    timeline stays correct across a page reload in the middle of a run and
    when a run was started by another client.
    """
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
                "diagnosis": attempt.get("diagnosis", {}),
                "decision": attempt.get("decision", {}),
                "safety_result": attempt.get("safety_result", {}),
                "action_result": attempt.get("action_result", {}),
                "verification": verification,
            })

    return {
        "status": (
            last_incident_result.get("status")
            if last_incident_result
            else "idle"
        ),
        "agent": dict(run_state),
        "attempt_count": len(attempts),
        "timeline": attempts,
    }


@app.post("/reset")
def reset_incident():
    """
    Reset the simulated service to its initial healthy state.
    """
    from backend.tools import remediation

    global last_incident_result, active_scenario

    if run_state["running"]:
        raise HTTPException(status_code=409, detail="Cannot reset while an incident run is active.")

    _clear_faults()
    state.current_version = INITIAL_VERSION
    remediation.reset_replicas()

    active_scenario = "healthy"
    last_incident_result = None
    _reset_run_state()

    return {
        "message": "IncidentPilot simulator reset.",
        "state": state,
    }
