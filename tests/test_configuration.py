"""Central settings and SLO source-of-truth tests."""

import json

import pytest
from pydantic import ValidationError

from backend.config import IncidentPilotSettings, get_settings, reset_settings_cache
from backend.shared import slo


def test_safe_demo_defaults_are_valid_and_public(monkeypatch):
    monkeypatch.delenv("VERIFICATION_INTERVAL_SECONDS", raising=False)
    settings = IncidentPilotSettings(_env_file=None)
    public = settings.public_config()

    assert public["slo"] == {
        "recovery_max_error_rate": 0.05,
        "recovery_max_latency_ms": 200,
        "incident_error_rate": 0.10,
        "incident_latency_ms": 300,
    }
    assert public["replicas"] == {"min": 1, "max": 3}
    assert public["agent"]["max_remediation_attempts"] == 3
    assert public["safety"] == {"allowed_namespace": "incidentpilot"}
    assert public["verification"] == {"samples": 3, "interval_seconds": 1.0}
    assert public["environment"]["environment"] == "simulator"


def test_environment_overrides_are_parsed_without_source_edits(monkeypatch):
    monkeypatch.setenv("RECOVERY_MAX_ERROR_RATE", "0.04")
    monkeypatch.setenv("VERIFICATION_SAMPLES", "5")
    monkeypatch.setenv("MAX_REMEDIATION_ATTEMPTS", "4")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://demo.example")

    settings = IncidentPilotSettings(_env_file=None)

    assert settings.recovery_max_error_rate == 0.04
    assert settings.verification_samples == 5
    assert settings.max_attempts == 4
    assert settings.allowed_origins == (
        "http://localhost:3000",
        "https://demo.example",
    )


def test_environment_name_is_case_and_whitespace_tolerant(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", " Kubernetes ")

    assert IncidentPilotSettings(_env_file=None).environment.value == "kubernetes"


@pytest.mark.parametrize(
    "overrides",
    [
        {"recovery_max_error_rate": 0.20, "elevated_error_rate": 0.10},
        {"recovery_max_latency_ms": 400, "elevated_latency_ms": 300},
        {"min_replicas": 4, "max_replicas": 3},
        {"simulator_adaptive_load_units": 4.0, "max_replicas": 3},
        {"latency_chart_ceiling_ms": 900, "simulator_outage_latency_ms": 1000},
        {"simulator_initial_version": "v42", "simulator_bad_deployment_version": "v42"},
        {"cors_origins": "*"},
    ],
)
def test_invalid_setting_relationships_fail_fast(overrides):
    with pytest.raises(ValidationError):
        IncidentPilotSettings(_env_file=None, **overrides)


def test_public_config_never_serializes_secret(monkeypatch):
    secret = "secret-that-must-not-leak"
    monkeypatch.setenv("HF_TOKEN", secret)
    settings = IncidentPilotSettings(_env_file=None)

    assert secret not in json.dumps(settings.public_config())
    assert "hf_token" not in settings.model_dump(mode="json")


def test_settings_are_cached_and_can_be_explicitly_reloaded(monkeypatch):
    reset_settings_cache()
    monkeypatch.setenv("VERIFICATION_SAMPLES", "4")
    first = get_settings()
    monkeypatch.setenv("VERIFICATION_SAMPLES", "5")

    assert get_settings() is first
    assert get_settings().verification_samples == 4

    reset_settings_cache()
    assert get_settings().verification_samples == 5
    reset_settings_cache()


def test_legacy_slo_accessors_resolve_through_settings():
    reset_settings_cache()
    settings = get_settings()

    assert slo.RECOVERY_MAX_ERROR_RATE == settings.recovery_max_error_rate
    assert slo.MAX_REPLICAS == settings.max_replicas
    assert slo.as_dict()["recovery"]["max_latency_ms"] == settings.recovery_max_latency_ms
