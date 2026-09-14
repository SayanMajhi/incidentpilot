"""Single validated configuration source for IncidentPilot.

Environment variables use the upper-case form of each field name.  The
cached object is immutable, which prevents thresholds changing halfway
through an incident.  ``public_config`` deliberately omits credentials.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.shared.slo import SLOThresholds


class InfrastructureMode(str, Enum):
    SIMULATOR = "simulator"
    KUBERNETES = "kubernetes"


class IncidentPilotSettings(BaseSettings):
    """Process-wide settings with safe demo defaults and bounded values."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
        frozen=True,
    )

    environment: InfrastructureMode = InfrastructureMode.SIMULATOR
    allowed_namespace: str = Field(default="incidentpilot", min_length=1)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        validation_alias=AliasChoices("MAX_REMEDIATION_ATTEMPTS", "MAX_ATTEMPTS"),
    )
    verification_samples: int = Field(default=3, ge=1, le=20)
    verification_interval_seconds: float = Field(default=1.0, ge=0.0, le=60.0)

    recovery_max_error_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    recovery_max_latency_ms: int = Field(default=200, gt=0)
    elevated_error_rate: float = Field(default=0.10, ge=0.0, le=1.0)
    elevated_latency_ms: int = Field(default=300, gt=0)
    min_replicas: int = Field(default=1, ge=1, le=20)
    max_replicas: int = Field(default=3, ge=1, le=20)

    simulator_healthy_error_rate: float = Field(default=0.01, ge=0.0, le=1.0)
    simulator_healthy_latency_ms: int = Field(default=100, gt=0)
    simulator_outage_error_rate: float = Field(default=0.70, ge=0.0, le=1.0)
    simulator_outage_latency_ms: int = Field(default=1000, gt=0)
    simulator_initial_version: str = Field(default="v41", min_length=1)
    simulator_bad_deployment_version: str = Field(default="v42", min_length=1)
    simulator_baseline_load_units: float = Field(default=0.6, gt=0.0)
    simulator_adaptive_load_units: float = Field(default=2.5, gt=0.0)
    latency_chart_ceiling_ms: int = Field(default=1200, gt=0)

    llm_enabled: bool = False
    hf_token: SecretStr | None = Field(default=None, exclude=True)
    hf_model: str = Field(default="Qwen/Qwen2.5-7B-Instruct", min_length=1)
    hf_timeout_seconds: float = Field(default=20.0, gt=0.0, le=120.0)

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        if not origins:
            raise ValueError("CORS_ORIGINS must contain at least one origin.")
        if "*" in origins or any(
            not origin.startswith(("http://", "https://")) for origin in origins
        ):
            raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins.")
        return ",".join(dict.fromkeys(origins))

    @model_validator(mode="after")
    def validate_related_settings(self) -> "IncidentPilotSettings":
        # Constructing the value object applies all cross-threshold checks.
        self.slo
        if self.simulator_baseline_load_units > self.min_replicas:
            raise ValueError("Simulator baseline load must fit the minimum replica count.")
        if not (
            self.min_replicas
            < self.simulator_adaptive_load_units
            <= self.max_replicas
        ):
            raise ValueError(
                "Adaptive simulator load must exceed minimum capacity and be "
                "recoverable within the configured maximum replicas."
            )
        return self

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        return tuple(self.cors_origins.split(","))

    @property
    def slo(self) -> SLOThresholds:
        return SLOThresholds(
            recovery_max_error_rate=self.recovery_max_error_rate,
            recovery_max_latency_ms=self.recovery_max_latency_ms,
            elevated_error_rate=self.elevated_error_rate,
            elevated_latency_ms=self.elevated_latency_ms,
            min_replicas=self.min_replicas,
            max_replicas=self.max_replicas,
            baseline_error_rate=self.simulator_healthy_error_rate,
            baseline_latency_ms=self.simulator_healthy_latency_ms,
            outage_error_rate=self.simulator_outage_error_rate,
            outage_latency_ms=self.simulator_outage_latency_ms,
            latency_chart_ceiling_ms=self.latency_chart_ceiling_ms,
            initial_version=self.simulator_initial_version,
            bad_deployment_version=self.simulator_bad_deployment_version,
        )

    def public_config(
        self,
        environment_description: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return settings safe to expose through the unauthenticated API."""
        config = self.slo.as_dict()
        config.update(
            {
                "slo": {
                    "recovery_max_error_rate": self.recovery_max_error_rate,
                    "recovery_max_latency_ms": self.recovery_max_latency_ms,
                    "incident_error_rate": self.elevated_error_rate,
                    "incident_latency_ms": self.elevated_latency_ms,
                },
                "agent": {
                    "max_remediation_attempts": self.max_attempts,
                    "max_attempts": self.max_attempts,
                },
                "safety": {"allowed_namespace": self.allowed_namespace},
                "verification": {
                    "samples": self.verification_samples,
                    "interval_seconds": self.verification_interval_seconds,
                },
                "simulator": {
                    "baseline_load_units": self.simulator_baseline_load_units,
                    "adaptive_load_units": self.simulator_adaptive_load_units,
                },
                "environment": environment_description
                or {
                    "environment": self.environment.value,
                    "simulator_controls": self.environment is InfrastructureMode.SIMULATOR,
                },
                "llm": {"enabled": self.llm_enabled, "model": self.hf_model},
            }
        )
        return config


@lru_cache(maxsize=1)
def get_settings() -> IncidentPilotSettings:
    """Read and validate the environment exactly once per process."""
    return IncidentPilotSettings()


def reset_settings_cache() -> None:
    """Testing hook: force the next access to re-read environment variables."""
    get_settings.cache_clear()
