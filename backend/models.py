"""Typed domain contracts shared by IncidentPilot's agent and API layers.

These models deliberately do not prescribe agent behavior.  They provide
validated, JSON-serializable shapes that the existing dictionary-oriented
pipeline can adopt incrementally without changing remediation decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class SerializableModel(BaseModel):
    """Strict Pydantic base with a small API-friendly conversion helper."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation, including enum values."""
        return self.model_dump(mode="json")


class EvidenceSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RemediationActionType(str, Enum):
    """The only mutation categories a proposed remediation may contain."""

    RESTART = "restart"
    ROLLBACK = "rollback"
    SCALE = "scale"


class VerificationStatus(str, Enum):
    RECOVERED = "recovered"
    FAILED = "failed"


class TracePhase(str, Enum):
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


class EvidenceItem(SerializableModel):
    """One independently attributable fact discovered during investigation."""

    source: str = Field(min_length=1)
    key: str = Field(min_length=1)
    value: JsonValue = None
    severity: EvidenceSeverity = EvidenceSeverity.INFO
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    description: str = Field(min_length=1)


class InvestigationResult(SerializableModel):
    """Typed evidence plus the investigator's concise factual summary."""

    evidence: list[EvidenceItem] = Field(default_factory=list)
    summary: str


class ProposedAction(SerializableModel):
    """A proposal only; execution still requires the existing safety gate."""

    action_type: RemediationActionType
    target: str | int | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class VerificationResult(SerializableModel):
    """Recovery verdict with old and new fields during model migration.

    ``recovered`` and ``telemetry`` are retained because the current
    controller, tests, and frontend consume them. ``status``,
    ``metrics_before``, and ``metrics_after`` establish the structured shape
    for later features.  The two verdict fields are validated as equivalent.
    """

    status: VerificationStatus
    reason: str
    metrics_before: dict[str, JsonValue] | None = None
    metrics_after: dict[str, JsonValue] | None = None
    recovered: bool
    telemetry: dict[str, JsonValue] | None = None

    def __init__(
        self,
        recovered: bool | None = None,
        reason: str | None = None,
        telemetry: dict[str, JsonValue] | None = None,
        **data: Any,
    ) -> None:
        """Accept the verifier's historical positional constructor."""
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
        if not isinstance(data, dict):
            return data

        values = dict(data)
        status = values.get("status")
        recovered = values.get("recovered")

        if status is None and recovered is not None:
            values["status"] = (
                VerificationStatus.RECOVERED
                if recovered
                else VerificationStatus.FAILED
            )
        elif recovered is None and status is not None:
            values["recovered"] = status in (
                VerificationStatus.RECOVERED,
                VerificationStatus.RECOVERED.value,
            )

        return values

    @model_validator(mode="after")
    def check_verdict(self) -> "VerificationResult":
        expected = self.status == VerificationStatus.RECOVERED
        if self.recovered != expected:
            raise ValueError("status and recovered describe different verdicts")
        return self

    def with_failed_status(self, reason: str) -> "VerificationResult":
        """Return a failed copy while keeping compatibility fields aligned."""
        return self.model_copy(
            update={
                "status": VerificationStatus.FAILED,
                "recovered": False,
                "reason": reason,
            },
        )


class TraceEvent(SerializableModel):
    """One timestamped event in an agent attempt's observable trace."""

    attempt: int = Field(ge=1)
    phase: TracePhase
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    evidence: list[EvidenceItem] = Field(default_factory=list)
    diagnosis: str | dict[str, JsonValue] | None = None
    decision: ProposedAction | None = None
    safety: dict[str, JsonValue] | None = None
    execution: dict[str, JsonValue] | None = None
    verification: VerificationResult | None = None


class IncidentRunStatus(str, Enum):
    RUNNING = "running"
    RESOLVED = "resolved"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    FAILED = "failed"


class IncidentRunState(SerializableModel):
    """Goal and progress for one bounded incident-response run."""

    run_id: str = Field(pattern=r"^inc-[a-f0-9]+$")
    goal: str = Field(min_length=1)
    started_at: datetime
    status: IncidentRunStatus
    phase: TracePhase
    attempt: int = Field(ge=0)
    history: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
