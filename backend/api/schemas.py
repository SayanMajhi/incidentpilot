"""Validated request and response contracts for the HTTP layer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ApiHealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    environment: str
    version: str


class ServiceHealthResponse(ApiModel):
    status: str
    is_healthy: bool


class MetricsResponse(ApiModel):
    error_rate: float
    latency_ms: int
    status: str
    cpu_percent: int | None = None
    memory_percent: int | None = None


class VersionResponse(ApiModel):
    current_version: str


class EnvironmentDescriptor(ApiModel):
    mode: str
    supports_scenario_injection: bool
    target: str | None = None


class RuntimeConfigResponse(ApiModel):
    slo: dict[str, float | int]
    replicas: dict[str, int]
    agent: dict[str, int]
    verification: dict[str, float | int]
    environment: EnvironmentDescriptor


class SimulationActionResponse(ApiModel):
    message: str
    state: dict[str, Any]
    mutation: dict[str, Any] | None = None


class ResetResponse(ApiModel):
    message: str
    state: dict[str, Any] | None


class RunStartResponse(ApiModel):
    run_id: str
    status: Literal["running"]
    status_url: str
    timeline_url: str


class AgentRuntimeResponse(ApiModel):
    run_id: str | None = None
    running: bool
    status: str
    phase: str
    attempt: int
    max_attempts: int
    goal: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None


class StatusResponse(ApiModel):
    revision: int
    service: dict[str, Any]
    scenario: str
    environment: EnvironmentDescriptor
    agent: AgentRuntimeResponse
    latest_incident: dict[str, Any] | None = None
    diagnostics: dict[str, Any]


class TimelineResponse(ApiModel):
    revision: int
    run_id: str | None = None
    status: str
    goal: str | None = None
    started_at: str | None = None
    reason: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    attempts: list[dict[str, Any]] = Field(default_factory=list)


class SafetyEvaluateRequest(ApiModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    target: str | int | None = None
    namespace: str
    attempt: int = Field(default=1, ge=1)


class SafetyEvaluateResponse(ApiModel):
    assessment_id: str
    executed: Literal[False] = False
    decision: dict[str, Any]
    events: list[dict[str, Any]]

