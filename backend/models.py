"""Validated domain contracts for IncidentPilot's controller and API.

The names in this module intentionally match the running incident workflow.
They can therefore be used at controller, runtime, and HTTP boundaries without
renaming actions or translating evidence into a second, synthetic schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    computed_field,
    field_validator,
    model_validator,
)


def utc_now() -> datetime:
    """Return an aware UTC timestamp suitable for persisted API state."""
    return datetime.now(timezone.utc)


class SerializableModel(BaseModel):
    """Pydantic base with a consistent JSON-compatible conversion helper."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AgentPhase(str, Enum):
    IDLE = "idle"
    OBSERVING = "observing"
    INCIDENT_DETECTED = "incident_detected"
    INVESTIGATING = "investigating"
    DIAGNOSING = "diagnosing"
    PLANNING = "planning"
    SAFETY_CHECK = "safety_check"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REPLANNING = "replanning"
    RESOLVED = "resolved"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    FAILED = "failed"
    COMPLETE = "complete"


class IncidentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    NO_INCIDENT = "no_incident"
    RESOLVED = "resolved"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    FAILED = "failed"


class ActionType(str, Enum):
    """Every controller outcome; only the first three mutate infrastructure."""

    RESTART_SERVICE = "restart_service"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    SCALE_SERVICE = "scale_service"
    ESCALATE = "escalate"

    # Source-compatible enum member names from the transitional contract.
    RESTART = "restart_service"
    ROLLBACK = "rollback_deployment"
    SCALE = "scale_service"


class EvidenceSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class VerificationStatus(str, Enum):
    RECOVERED = "recovered"
    PARTIAL = "partial"
    FAILED = "failed"


class EvidenceItem(SerializableModel):
    """One attributable fact collected from the environment."""

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    signal: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    value: JsonValue = None
    count: int | None = Field(default=None, ge=1)
    severity: EvidenceSeverity = EvidenceSeverity.INFO
    timestamp: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def accept_transitional_names(cls, data: Any) -> Any:
        """Accept old ``key``/``description`` input while serializing one shape."""
        if not isinstance(data, Mapping):
            return data
        values = dict(data)
        signal = values.pop("key", None)
        detail = values.pop("description", None)
        values.setdefault("signal", signal)
        values.setdefault("detail", detail)
        if not values.get("id") and values.get("source") and values.get("signal"):
            values["id"] = f"{values['source']}:{values['signal']}"
        return values


class Observation(SerializableModel):
    """A fresh environment snapshot plus optional investigation evidence."""

    observation_id: int = Field(ge=1)
    observed_at: datetime = Field(default_factory=utc_now)
    metrics: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)
    current_version: str | None = None
    capacity: dict[str, Any] = Field(default_factory=dict)
    logs: list[Any] = Field(default_factory=list)
    deployment_history: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    attempt_history: list[dict[str, Any]] = Field(default_factory=list)
    previous_attempt: dict[str, Any] | None = None


class InvestigationResult(SerializableModel):
    evidence: list[EvidenceItem] = Field(default_factory=list)
    summary: str = ""


class Diagnosis(SerializableModel):
    probable_cause: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ActionProposal(SerializableModel):
    """An evidence-backed proposal which still requires policy approval."""

    action: ActionType = Field(validation_alias=AliasChoices("action", "action_type"))
    target: JsonValue = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    diagnosis: str | None = None
    evidence: list[str] = Field(default_factory=list)
    source: str | None = None
    fallback_reason: str | None = None
    arbitration_reason: str | None = None
    llm_proposal: dict[str, Any] | None = None
    deterministic_validation: dict[str, Any] | None = None

    @field_validator("action", mode="before")
    @classmethod
    def normalize_transitional_action(cls, value: Any) -> Any:
        return {
            "restart": ActionType.RESTART_SERVICE,
            "rollback": ActionType.ROLLBACK_DEPLOYMENT,
            "scale": ActionType.SCALE_SERVICE,
        }.get(value, value)

    @property
    def action_type(self) -> ActionType:
        """Compatibility accessor for the former field name."""
        return self.action


class AttemptBudget(SerializableModel):
    attempt: int = Field(ge=0)
    maximum: int = Field(ge=1)
    remaining_after_this_attempt: int = Field(ge=0)


class SafetyDecision(SerializableModel):
    """Inspectable result from the deterministic remediation policy."""

    assessment_id: str = Field(default_factory=lambda: f"safe-{uuid4().hex}")
    action: str
    target: JsonValue = None
    namespace: str
    checked: bool = True
    allowed: bool | None
    rule_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    bounds: dict[str, JsonValue] = Field(default_factory=dict)
    budget: AttemptBudget
    context: dict[str, JsonValue] = Field(default_factory=dict)


class ActionResult(SerializableModel):
    """Infrastructure command outcome, deliberately separate from recovery."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=True,
    )

    action: str = Field(min_length=1)
    success: bool
    status: str = Field(min_length=1)
    message: str = Field(min_length=1)
    target: JsonValue = None
    policy_allowed: bool | None = None
    executed_at: datetime = Field(default_factory=utc_now)


class VerificationCheck(SerializableModel):
    name: str = Field(min_length=1)
    passed: bool
    required: bool = True
    observed: JsonValue = None
    expected: JsonValue = None
    message: str = Field(min_length=1)


class VerificationResult(SerializableModel):
    """Fresh recovery evidence with legacy verdict fields kept in sync."""

    status: VerificationStatus
    reason: str = Field(min_length=1)
    recovered: bool
    checks: list[VerificationCheck] = Field(default_factory=list)
    samples: list[dict[str, JsonValue]] = Field(default_factory=list)
    sample_count: int = Field(default=0, ge=0)
    metrics_before: dict[str, JsonValue] | None = None
    metrics_after: dict[str, JsonValue] | None = None
    deltas: dict[str, JsonValue] = Field(default_factory=dict)
    readiness: dict[str, JsonValue] | None = None
    telemetry: dict[str, Any] | None = None
    verified_at: datetime = Field(default_factory=utc_now)

    def __init__(
        self,
        recovered: bool | None = None,
        reason: str | None = None,
        telemetry: dict[str, Any] | None = None,
        **data: Any,
    ) -> None:
        """Accept the verifier's historical three-position constructor."""
        if recovered is not None:
            data.setdefault("recovered", recovered)
        if reason is not None:
            data.setdefault("reason", reason)
        if telemetry is not None:
            data.setdefault("telemetry", telemetry)
        super().__init__(**data)

    @model_validator(mode="before")
    @classmethod
    def fill_verdict_fields(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        values = dict(data)
        status = values.get("status")
        recovered = values.get("recovered")
        if status is None and recovered is not None:
            values["status"] = (
                VerificationStatus.RECOVERED if recovered else VerificationStatus.FAILED
            )
        elif recovered is None and status is not None:
            values["recovered"] = status in (
                VerificationStatus.RECOVERED,
                VerificationStatus.RECOVERED.value,
            )
        if not values.get("sample_count") and values.get("samples"):
            values["sample_count"] = len(values["samples"])
        return values

    @model_validator(mode="after")
    def check_verdict(self) -> "VerificationResult":
        if self.recovered != (self.status is VerificationStatus.RECOVERED):
            raise ValueError("status and recovered describe different verdicts")
        return self

    def with_failed_status(self, reason: str) -> "VerificationResult":
        """Return a validated failed copy for compatibility callers."""
        payload = self.model_dump()
        payload.update(
            status=VerificationStatus.FAILED,
            recovered=False,
            reason=reason,
        )
        return type(self).model_validate(payload)


class AttemptRecord(SerializableModel):
    attempt: int = Field(ge=1)
    observations: Observation | dict[str, Any]
    detection: dict[str, Any]
    evidence: list[EvidenceItem] = Field(default_factory=list)
    new_evidence: list[str] = Field(default_factory=list)
    diagnosis: Diagnosis | dict[str, Any]
    decision: ActionProposal | dict[str, Any]
    safety_result: SafetyDecision | dict[str, Any]
    action_result: ActionResult | dict[str, Any] | None = None
    verification: VerificationResult | None = None
    evidence_after_action: list[EvidenceItem] | None = None
    new_evidence_after_action: list[str] | None = None


class TimelineEvent(SerializableModel):
    """One immutable, ordered fact in an incident's backend-owned timeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: f"evt-{uuid4().hex}")
    timestamp: datetime = Field(default_factory=utc_now)
    incident_id: str = Field(min_length=1)
    attempt: int | None = Field(default=None, ge=0)
    phase: AgentPhase
    event_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)


class IncidentRun(SerializableModel):
    """Mutable, validated state for one bounded autonomous response run."""

    incident_id: str = Field(pattern=r"^inc-[A-Za-z0-9-]+$")
    goal: str = Field(min_length=1)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    status: IncidentStatus = IncidentStatus.RUNNING
    phase: AgentPhase = AgentPhase.IDLE
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    symptoms: list[str] = Field(default_factory=list)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    diagnosis: Diagnosis | dict[str, Any] | None = None
    selected_action: ActionProposal | dict[str, Any] | None = None
    attempted_actions: list[dict[str, Any]] = Field(default_factory=list)
    failed_actions: list[dict[str, Any]] = Field(default_factory=list)
    attempts: list[AttemptRecord | dict[str, Any]] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    outcome: str | None = None
    reason: str | None = None
    revision: int = Field(default=0, ge=0)

    @computed_field
    @property
    def run_id(self) -> str:
        return self.incident_id

    @computed_field
    @property
    def trace_events(self) -> list[TimelineEvent]:
        """Compatibility name used by the first dashboard implementation."""
        return self.timeline

    @computed_field
    @property
    def history(self) -> list[AttemptRecord | dict[str, Any]]:
        return self.attempts


# Compatibility names for callers migrating to the runtime-aligned models.
RemediationActionType = ActionType
ProposedAction = ActionProposal
IncidentRunStatus = IncidentStatus


class TracePhase(str, Enum):
    """Deprecated phase vocabulary retained only for old stored traces."""

    OBSERVING = "observing"
    INVESTIGATING = "investigating"
    DIAGNOSING = "diagnosing"
    DECIDING = "deciding"
    CHECKING_SAFETY = "checking_safety"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    ADAPTING = "adapting"
    ESCALATED = "escalated"
    COMPLETE = "complete"
    FAILED = "failed"


class TraceEvent(SerializableModel):
    """Deprecated trace shape; new code should emit :class:`TimelineEvent`."""

    attempt: int = Field(ge=1)
    phase: TracePhase
    timestamp: datetime = Field(default_factory=utc_now)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    diagnosis: str | dict[str, JsonValue] | None = None
    decision: ActionProposal | None = None
    safety: dict[str, JsonValue] | None = None
    execution: dict[str, JsonValue] | None = None
    verification: VerificationResult | None = None


class IncidentRunState(SerializableModel):
    """Deprecated status-only view kept for integrations using the old name."""

    run_id: str = Field(pattern=r"^inc-[A-Za-z0-9-]+$")
    goal: str = Field(min_length=1)
    started_at: datetime
    status: IncidentStatus
    phase: AgentPhase | TracePhase
    attempt: int = Field(ge=0)
    history: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
