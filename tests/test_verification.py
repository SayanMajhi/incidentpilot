from verification.verifier import verifier


def test_sustained_health_is_recovered():
    observations = [
        {"error_rate": 0.01, "latency_ms": 100},
        {"error_rate": 0.02, "latency_ms": 110},
        {"error_rate": 0.01, "latency_ms": 105},
    ]

    result = verifier.verify_sustained(observations)

    assert result.recovered is True


def test_recurrence_during_verification_is_not_recovered():
    observations = [
        {"error_rate": 0.01, "latency_ms": 100},
        {"error_rate": 0.02, "latency_ms": 110},
        {"error_rate": 0.70, "latency_ms": 1000},
    ]

    result = verifier.verify_sustained(observations)

    assert result.recovered is False


def test_empty_observations_are_not_recovered():
    result = verifier.verify_sustained([])

    assert result.recovered is False