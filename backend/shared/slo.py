"""SLO value contract and compatibility accessors.

Default values live only in :mod:`backend.config`.  The module attributes at
the bottom preserve existing callers while resolving through the validated,
cached settings object rather than maintaining a second set of constants.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SLOThresholds(BaseModel):
    """Immutable, validated thresholds used by diagnosis and verification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    recovery_max_error_rate: float = Field(ge=0.0, le=1.0)
    recovery_max_latency_ms: int = Field(gt=0)
    elevated_error_rate: float = Field(ge=0.0, le=1.0)
    elevated_latency_ms: int = Field(gt=0)
    min_replicas: int = Field(ge=1)
    max_replicas: int = Field(ge=1)
    baseline_error_rate: float = Field(ge=0.0, le=1.0)
    baseline_latency_ms: int = Field(gt=0)
    outage_error_rate: float = Field(ge=0.0, le=1.0)
    outage_latency_ms: int = Field(gt=0)
    latency_chart_ceiling_ms: int = Field(gt=0)
    initial_version: str = Field(min_length=1)
    bad_deployment_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relationships(self) -> "SLOThresholds":
        if not (
            self.baseline_error_rate
            <= self.recovery_max_error_rate
            < self.elevated_error_rate
            <= self.outage_error_rate
        ):
            raise ValueError(
                "Error-rate thresholds must satisfy baseline <= recovery "
                "< elevated <= outage."
            )
        if not (
            self.baseline_latency_ms
            <= self.recovery_max_latency_ms
            < self.elevated_latency_ms
            <= self.outage_latency_ms
        ):
            raise ValueError(
                "Latency thresholds must satisfy baseline <= recovery "
                "< elevated <= outage."
            )
        if self.min_replicas > self.max_replicas:
            raise ValueError("Minimum replicas cannot exceed maximum replicas.")
        if self.latency_chart_ceiling_ms < self.outage_latency_ms:
            raise ValueError("Chart ceiling must include the configured outage latency.")
        if self.initial_version == self.bad_deployment_version:
            raise ValueError("Initial and bad-deployment versions must differ.")
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "recovery": {
                "max_error_rate": self.recovery_max_error_rate,
                "max_latency_ms": self.recovery_max_latency_ms,
            },
            "elevated": {
                "error_rate": self.elevated_error_rate,
                "latency_ms": self.elevated_latency_ms,
            },
            "replicas": {"min": self.min_replicas, "max": self.max_replicas},
            "baseline": {
                "error_rate": self.baseline_error_rate,
                "latency_ms": self.baseline_latency_ms,
                "version": self.initial_version,
            },
            "outage": {
                "error_rate": self.outage_error_rate,
                "latency_ms": self.outage_latency_ms,
            },
            "chart": {"latency_ceiling_ms": self.latency_chart_ceiling_ms},
            "bad_deployment_version": self.bad_deployment_version,
        }


_SETTING_ATTRIBUTES = {
    "HEALTHY_ERROR_RATE": "simulator_healthy_error_rate",
    "HEALTHY_LATENCY_MS": "simulator_healthy_latency_ms",
    "OUTAGE_ERROR_RATE": "simulator_outage_error_rate",
    "OUTAGE_LATENCY_MS": "simulator_outage_latency_ms",
    "RECOVERY_MAX_ERROR_RATE": "recovery_max_error_rate",
    "RECOVERY_MAX_LATENCY_MS": "recovery_max_latency_ms",
    "ELEVATED_ERROR_RATE": "elevated_error_rate",
    "ELEVATED_LATENCY_MS": "elevated_latency_ms",
    "MIN_REPLICAS": "min_replicas",
    "MAX_REPLICAS": "max_replicas",
    "LATENCY_CHART_CEILING_MS": "latency_chart_ceiling_ms",
    "INITIAL_VERSION": "simulator_initial_version",
    "BAD_DEPLOYMENT_VERSION": "simulator_bad_deployment_version",
}


def __getattr__(name: str) -> Any:
    setting_name = _SETTING_ATTRIBUTES.get(name)
    if setting_name is None:
        raise AttributeError(name)
    from backend.config import get_settings

    return getattr(get_settings(), setting_name)


def as_dict() -> dict[str, Any]:
    """Return the public SLO shape used by legacy ``GET /config`` callers."""
    from backend.config import get_settings

    return get_settings().slo.as_dict()
