import logging
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

#In memory service state
class ServiceState(BaseModel):
    """represents the current in memory state of the smulated service"""
    status: Literal["healthy", "down"]
    error_rate: float
    latency_ms: int
    current_version: str

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
def _apply_healthy_baseline() -> None:
    """Reset status, error rate and latency to the healthy baseline.

    The deployed version is deliberately left untouched: which version is
    running is a separate fact from whether the service is healthy.
    """
    state.status = HEALTHY_STATUS
    state.error_rate = HEALTHY_ERROR_RATE
    state.latency_ms = HEALTHY_LATENCY_MS


def _apply_incident_state() -> None:
    """Put the service into the deterministic unhealthy state."""
    state.status = DOWN_STATUS
    state.error_rate = OUTAGE_ERROR_RATE
    state.latency_ms = OUTAGE_LATENCY_MS


# Module level mutable state, shared across all requests in this process.
state: ServiceState = _initial_state()

# Adaptive incident state.
adaptive_incident_active = False
adaptive_restart_attempted = False
active_scenario = "healthy"

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
    """Activate a demo scenario and discard any previous run's results."""
    global active_scenario, last_incident_result
    global adaptive_incident_active, adaptive_restart_attempted

    active_scenario = scenario
    last_incident_result = None
    adaptive_incident_active = False
    adaptive_restart_attempted = False
    _reset_run_state()

def simulate_adaptive_restart_effect() -> None:
    """
    Simulate the effect of a restart during the adaptive incident.

    The restart action itself succeeds, but the underlying incident
    remains unresolved. This creates a verification failure that
    forces IncidentPilot to reconsider its diagnosis.
    """
    global adaptive_restart_attempted

    if not adaptive_incident_active:
        return

    adaptive_restart_attempted = True

    _apply_incident_state()

def simulate_adaptive_scale_effect() -> None:
    """
    Simulate the effect of scaling during the adaptive incident.

    The second remediation addresses the underlying resource-related
    failure and restores the service to its healthy baseline.

    Once the incident is resolved, the adaptive scenario state is
    cleared so it cannot affect later incidents or tests.
    """
    global adaptive_incident_active, adaptive_restart_attempted

    if not adaptive_incident_active or not adaptive_restart_attempted:
        return

    _apply_healthy_baseline()

    # The adaptive incident has now been resolved.
    adaptive_incident_active = False
    adaptive_restart_attempted = False
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
    _apply_incident_state()
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

    Cause and effect is preserved. A restart clears transient failure, but it
    cannot fix an incident whose cause is still deployed: if the tracked bad
    deployment is the running version, the service stays down. This is what
    makes ``remediation.restart_service``'s contract ("a bad deployment would
    still be bad after a restart") true in the simulator as well as in prose.

    Returns:
        bool: True if the restart actually restored the healthy baseline,
        False if the incident cause survived the restart.
    """
    if state.current_version == BAD_DEPLOYMENT_VERSION and state.status != HEALTHY_STATUS:
        return False

    _apply_healthy_baseline()
    return True


@app.post("/simulate/recover", response_model=SimulationActionResponse)
def simulate_recover() -> SimulationActionResponse:
    """Restore the simulated service to its healthy baseline state.

    Resets status, error_rate and latency_ms to their healthy baseline
    values and clears the active scenario. The deployed version is left
    unchanged.
    """
    _begin_scenario("healthy")
    _apply_healthy_baseline()
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
    _apply_incident_state()
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
    Start a deterministic incident designed to test agent adaptation.

    The first restart attempt will appear to execute successfully,
    but the underlying incident will remain unresolved. A later
    remediation strategy can then resolve the incident.
    """
    global adaptive_incident_active

    _begin_scenario("adaptive_incident")
    adaptive_incident_active = True

    state.current_version = INITIAL_VERSION
    _apply_incident_state()

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
            state.current_version == BAD_DEPLOYMENT_VERSION and version != BAD_DEPLOYMENT_VERSION
    )

    state.current_version = version

    if incident_caused_by_current_deployment:
        _apply_healthy_baseline()
        message = (
            f"Rolled back to {version}. This removed the cause of the "
            f"bad-deployment incident ({BAD_DEPLOYMENT_VERSION}), so the "
            "service has recovered to its healthy baseline."
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

    global last_incident_result, adaptive_incident_active, adaptive_restart_attempted, active_scenario

    if run_state["running"]:
        raise HTTPException(status_code=409, detail="Cannot reset while an incident run is active.")

    _apply_healthy_baseline()
    state.current_version = INITIAL_VERSION
    remediation.reset_replicas()

    adaptive_incident_active = False
    adaptive_restart_attempted = False
    active_scenario = "healthy"
    last_incident_result = None
    _reset_run_state()

    return {
        "message": "IncidentPilot simulator reset.",
        "state": state,
    }
