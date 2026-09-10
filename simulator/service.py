from typing import Literal
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI(
    title="IncidentPilot Simulated Service",
    description="a deterministic,in_memory simulated production service",
    version="1.0.0",
)
#Constants,Keywords
HEALTHY_STATUS: Literal["healthy"] = "healthy"
DOWN_STATUS: Literal["down"] = "down"
HEALTHY_ERROR_RATE: float = 0.01
HEALTHY_LATENCY_MS: int = 100
OUTAGE_ERROR_RATE: float = 0.70
OUTAGE_LATENCY_MS: int = 1000
INITIAL_VERSION: str = "v41"

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
#module level mutable state,shared across all requests in this process
state:ServiceState = _initial_state()
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
    state.status = DOWN_STATUS
    state.error_rate = OUTAGE_ERROR_RATE
    state.latency_ms = OUTAGE_LATENCY_MS
    return SimulationActionResponse(
        message="Outage simulated.",
        state=state,
    )


@app.post("/simulate/recover", response_model=SimulationActionResponse)
def simulate_recover() -> SimulationActionResponse:
    """Restore the simulated service to its healthy baseline state

    resets status,error_rate,and latency_ms back
    to their healthy baseline values the deployed version is left
    unchanged.

    returns:
        simulationActionResponse:a confirmation message and the
        resulting service state
    """
    state.status = HEALTHY_STATUS
    state.error_rate = HEALTHY_ERROR_RATE
    state.latency_ms = HEALTHY_LATENCY_MS
    return SimulationActionResponse(
        message="Service recovered.",
        state=state,
    )
