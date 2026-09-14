"""Thin FastAPI routes over runtime, policy, and infrastructure services."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from backend.agent.controller import DEFAULT_GOAL
from backend.api.runtime import RuntimeBusyError, runtime
from backend.api.schemas import (
    ApiHealthResponse,
    MetricsResponse,
    ResetResponse,
    RunStartResponse,
    RuntimeConfigResponse,
    SafetyEvaluateRequest,
    SafetyEvaluateResponse,
    ServiceHealthResponse,
    SimulationActionResponse,
    StatusResponse,
    TimelineResponse,
    VersionResponse,
)
from backend.config import get_settings
from backend.infrastructure import InfrastructureError, get_infrastructure
from backend.safety.policy import policy
from backend.simulator.environment import simulator


logger = logging.getLogger(__name__)
router = APIRouter()
API_VERSION = "1.1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _environment_descriptor(infrastructure: Any) -> dict[str, Any]:
    raw = dict(infrastructure.describe())
    raw["mode"] = raw.pop("environment", infrastructure.name)
    raw["supports_scenario_injection"] = bool(
        infrastructure.supports_scenario_injection
    )
    return raw


def _simulator_only() -> Any:
    infrastructure = get_infrastructure()
    if not infrastructure.supports_scenario_injection:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Simulator endpoints are unavailable while IncidentPilot is "
                f"running against the {infrastructure.name} environment."
            ),
        )
    return infrastructure


def _mutate_scenario(
    scenario: str,
    mutation: Callable[[], dict[str, Any]],
    message: str,
) -> SimulationActionResponse:
    _simulator_only()
    try:
        result = runtime.mutate_scenario(scenario, mutation)
    except RuntimeBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return SimulationActionResponse(
        message=message,
        state=simulator.public_state(),
        mutation=result,
    )


@router.get("/health", response_model=ApiHealthResponse)
def api_health() -> ApiHealthResponse:
    """API liveness; this deliberately does not require a reachable target."""
    infrastructure = get_infrastructure()
    return ApiHealthResponse(
        status="ok",
        environment=infrastructure.name,
        version=API_VERSION,
    )


@router.get("/service/health", response_model=ServiceHealthResponse)
def service_health() -> ServiceHealthResponse:
    try:
        value = get_infrastructure().check_health()
    except InfrastructureError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return ServiceHealthResponse(**value)


@router.get("/metrics", response_model=MetricsResponse)
def metrics() -> MetricsResponse:
    try:
        return MetricsResponse(**get_infrastructure().get_metrics())
    except InfrastructureError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    try:
        return VersionResponse(current_version=get_infrastructure().get_current_version())
    except InfrastructureError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/simulate/outage", response_model=SimulationActionResponse)
def simulate_outage() -> SimulationActionResponse:
    return _mutate_scenario(
        "generic_outage",
        simulator.inject_outage,
        "Transient outage injected.",
    )


@router.post("/simulate/recover", response_model=SimulationActionResponse)
def simulate_recover() -> SimulationActionResponse:
    return _mutate_scenario(
        "healthy",
        simulator.reset,
        "Simulator restored to its healthy baseline.",
    )


@router.post("/simulate/bad-deployment", response_model=SimulationActionResponse)
def simulate_bad_deployment() -> SimulationActionResponse:
    return _mutate_scenario(
        "bad_deployment",
        simulator.inject_bad_deployment,
        "Bad deployment injected; the service is unhealthy.",
    )


@router.post("/simulate/adaptive-incident", response_model=SimulationActionResponse)
def simulate_adaptive_incident() -> SimulationActionResponse:
    return _mutate_scenario(
        "adaptive_incident",
        simulator.inject_adaptive_incident,
        (
            "Compound incident injected. Restart will clear the visible "
            "transient fault; fresh telemetry will then reveal pressure."
        ),
    )


@router.post("/simulate/capacity-incident", response_model=SimulationActionResponse)
def simulate_capacity_incident() -> SimulationActionResponse:
    return _mutate_scenario(
        "capacity_incident",
        simulator.inject_capacity_incident,
        "Capacity pressure injected.",
    )


@router.post("/simulate/rollback", response_model=SimulationActionResponse)
def simulate_rollback(version: str) -> SimulationActionResponse:
    _simulator_only()
    known = {entry["version"] for entry in get_infrastructure().get_deployment_history()}
    if version not in known:
        raise HTTPException(status_code=422, detail="Rollback target is not in deployment history.")
    try:
        mutation = runtime.mutate_scenario(simulator.scenario, lambda: simulator.rollback(version))
    except RuntimeBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return SimulationActionResponse(
        message=f"Simulator version changed to {version}; health follows active causes.",
        state=simulator.public_state(),
        mutation=mutation,
    )


@router.post(
    "/run-incident",
    response_model=RunStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_incident() -> RunStartResponse:
    from backend.agent.controller import controller as active_controller

    try:
        payload = runtime.start(
            controller=active_controller,
            goal=DEFAULT_GOAL,
            max_attempts=active_controller.MAX_ATTEMPTS,
        )
    except RuntimeBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RunStartResponse(**payload)


@router.get("/config", response_model=RuntimeConfigResponse)
def config() -> RuntimeConfigResponse:
    from backend.agent.controller import controller as active_controller

    infrastructure = get_infrastructure()
    descriptor = _environment_descriptor(infrastructure)
    payload = get_settings().public_config(environment_description=descriptor)
    payload["agent"]["max_remediation_attempts"] = active_controller.MAX_ATTEMPTS
    payload["verification"] = {
        "samples": active_controller.VERIFICATION_SAMPLES,
        "interval_seconds": active_controller.verification_interval_seconds,
    }
    return RuntimeConfigResponse(**payload)


@router.get("/status", response_model=StatusResponse)
def incident_status() -> StatusResponse:
    infrastructure = get_infrastructure()
    snapshot = runtime.snapshot()
    try:
        metrics_value = infrastructure.get_metrics()
        capacity = infrastructure.get_capacity()
        current_version = infrastructure.get_current_version()
        # Diagnostics are useful during incidents but unnecessarily expensive
        # for idle Kubernetes polling.
        needs_diagnostics = (
            metrics_value.get("status") != "healthy"
            or snapshot["agent"]["running"]
            or snapshot["latest_incident"] is not None
        )
        logs = infrastructure.query_logs() if needs_diagnostics else []
        deployment_history = (
            infrastructure.get_deployment_history() if needs_diagnostics else []
        )
    except InfrastructureError as error:
        logger.warning("Could not read %s environment: %s", infrastructure.name, error)
        raise HTTPException(
            status_code=503,
            detail=f"The {infrastructure.name} environment is unavailable: {error}",
        ) from error

    service = {
        "status": metrics_value.get("status"),
        "error_rate": metrics_value.get("error_rate"),
        "latency_ms": metrics_value.get("latency_ms"),
        "cpu_percent": metrics_value.get("cpu_percent"),
        "memory_percent": metrics_value.get("memory_percent"),
        "current_version": current_version,
        "replicas": capacity.get("replicas"),
        "ready_replicas": capacity.get("ready_replicas"),
        "utilization": capacity.get("utilization"),
    }
    return StatusResponse(
        revision=snapshot["revision"],
        service=service,
        scenario=(
            snapshot["scenario"]
            if infrastructure.supports_scenario_injection
            else infrastructure.name
        ),
        environment=_environment_descriptor(infrastructure),
        agent=snapshot["agent"],
        latest_incident=snapshot["latest_incident"],
        diagnostics={"logs": logs, "deployment_history": deployment_history},
    )


@router.get("/timeline", response_model=TimelineResponse)
def incident_timeline() -> TimelineResponse:
    return TimelineResponse(**runtime.timeline())


@router.post("/safety/evaluate", response_model=SafetyEvaluateResponse)
def evaluate_safety(request: SafetyEvaluateRequest) -> SafetyEvaluateResponse:
    infrastructure = get_infrastructure()
    history: list[dict[str, Any]] = []
    current_version: str | None = None
    if request.action == "rollback_deployment":
        try:
            history = infrastructure.get_deployment_history()
            current_version = infrastructure.get_current_version()
        except InfrastructureError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    decision = policy.evaluate(
        request.action,
        target=request.target,
        namespace=request.namespace,
        replicas=request.target if request.action == "scale_service" else None,
        version=request.target if request.action == "rollback_deployment" else None,
        attempt=request.attempt,
        deployment_history=history,
        current_version=current_version,
    )
    value = decision.to_dict()

    assessment_id = f"safe-{uuid4().hex}"
    event = {
        "event_id": f"evt-{uuid4().hex}",
        "timestamp": _now(),
        "incident_id": assessment_id,
        "attempt": request.attempt,
        "phase": "safety_check",
        "event_type": "safety_approved" if value.get("allowed") else "safety_rejected",
        "message": value.get("reason", "Safety policy evaluated."),
        "data": {"decision": value, "executed": False},
    }
    runtime.record_events([event])
    return SafetyEvaluateResponse(
        assessment_id=assessment_id,
        executed=False,
        decision=value,
        events=[event],
    )


@router.post("/reset", response_model=ResetResponse)
def reset() -> ResetResponse:
    infrastructure = get_infrastructure()
    try:
        if infrastructure.supports_scenario_injection:
            runtime.mutate_scenario("healthy", simulator.reset)
            return ResetResponse(
                message="IncidentPilot simulator reset.",
                state=simulator.public_state(),
            )
        runtime.reset(scenario=infrastructure.name)
    except RuntimeBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ResetResponse(
        message=(
            "IncidentPilot run history cleared. The "
            f"{infrastructure.name} environment was not modified."
        ),
        state=None,
    )
