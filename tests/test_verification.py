from backend.models import VerificationStatus
from backend.verification.verifier import verifier


def test_sustained_health_records_named_checks_and_all_samples():
    observations = [
        {"error_rate": 0.01, "latency_ms": 100, "status": "healthy"},
        {"error_rate": 0.02, "latency_ms": 110, "status": "healthy"},
        {"error_rate": 0.01, "latency_ms": 105, "status": "healthy"},
    ]

    result = verifier.verify_sustained(
        observations,
        health={"status": "healthy", "is_healthy": True},
        capacity={"replicas": 3, "ready_replicas": 3},
        metrics_before={"error_rate": 0.70, "latency_ms": 1000, "replicas": 1},
    )

    assert result.status is VerificationStatus.RECOVERED
    assert result.recovered is True
    assert result.sample_count == 3
    assert [sample["sample"] for sample in result.samples] == [1, 2, 3]
    assert {check.name for check in result.checks} == {
        "telemetry_available",
        "error_rate_slo",
        "latency_slo",
        "service_status",
        "sustained_samples",
        "health_endpoint",
        "readiness",
    }
    assert all(check.passed for check in result.checks)
    assert result.deltas == {
        "error_rate": -0.69,
        "latency_ms": -895.0,
        "replicas": 2.0,
    }
    assert result.readiness == {"replicas": 3, "ready_replicas": 3}


def test_recurrence_during_verification_is_partial_not_recovered():
    observations = [
        {"error_rate": 0.01, "latency_ms": 100},
        {"error_rate": 0.02, "latency_ms": 110},
        {"error_rate": 0.70, "latency_ms": 1000},
    ]

    result = verifier.verify_sustained(observations)

    assert result.status is VerificationStatus.PARTIAL
    assert result.recovered is False
    sustained = next(check for check in result.checks if check.name == "sustained_samples")
    assert sustained.passed is False
    assert [sample["passed"] for sample in result.samples] == [True, True, False]


def test_improvement_that_still_misses_slos_is_partial():
    result = verifier.verify_sustained(
        [
            {"error_rate": 0.60, "latency_ms": 750, "status": "down"},
            {"error_rate": 0.55, "latency_ms": 700, "status": "down"},
        ],
        metrics_before={"error_rate": 0.70, "latency_ms": 1000},
    )

    assert result.status is VerificationStatus.PARTIAL
    assert result.recovered is False
    assert result.deltas["error_rate"] == -0.15
    assert result.deltas["latency_ms"] == -300.0


def test_unhealthy_without_improvement_is_failed():
    result = verifier.verify(
        {"error_rate": 0.70, "latency_ms": 1000, "status": "down"},
    )

    assert result.status is VerificationStatus.FAILED
    assert result.recovered is False


def test_health_and_readiness_override_passing_numbers():
    result = verifier.verify_sustained(
        [{"error_rate": 0.01, "latency_ms": 100, "status": "healthy"}],
        health={"status": "down", "is_healthy": False},
        capacity={"replicas": 3, "ready_replicas": 2},
    )

    assert result.status is VerificationStatus.PARTIAL
    assert result.recovered is False
    assert next(c for c in result.checks if c.name == "health_endpoint").passed is False
    assert next(c for c in result.checks if c.name == "readiness").passed is False


def test_missing_or_invalid_telemetry_is_failed_with_evidence():
    missing = verifier.verify_sustained([])
    invalid = verifier.verify({"error_rate": "not-a-number", "latency_ms": None})

    assert missing.status is VerificationStatus.FAILED
    assert missing.sample_count == 0
    assert missing.checks[0].name == "telemetry_available"
    assert missing.checks[0].passed is False
    assert invalid.status is VerificationStatus.FAILED
    assert invalid.checks[0].passed is False


def test_readiness_is_non_required_when_adapter_does_not_report_it():
    result = verifier.verify(
        {"error_rate": 0.01, "latency_ms": 100, "status": "healthy"},
        health={"is_healthy": True},
        capacity={"replicas": 1, "utilization": 0.6},
    )

    readiness = next(check for check in result.checks if check.name == "readiness")
    assert readiness.required is False
    assert readiness.passed is True
    assert result.recovered is True
