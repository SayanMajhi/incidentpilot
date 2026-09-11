class VerificationResult:
    """
    Represents the result of an incident recovery verification.

    The result is kept as a small object internally, but provides
    dictionary conversion and a readable representation so it can
    safely be returned by APIs, printed in the terminal, or stored
    in execution history.
    """

    def __init__(self, recovered, reason):
        self.recovered = bool(recovered)
        self.reason = str(reason)

    def to_dict(self):
        """
        Convert the verification result into a JSON-friendly dictionary.
        """
        return {
            "recovered": self.recovered,
            "reason": self.reason,
        }

    def __repr__(self):
        """
        Make pprint()/debug output readable.
        """
        return repr(self.to_dict())


class Verifier:
    """
    Determines whether the service has actually recovered.

    Important distinction:

        remediation success != incident recovery

    A remediation action can execute successfully while the service
    remains unhealthy. Recovery is determined only from fresh metrics.
    """

    # Healthy-service thresholds
    MAX_ERROR_RATE = 0.05
    MAX_LATENCY_MS = 200

    def verify(self, metrics):
        """
        Verify the current service health using fresh metrics.

        Args:
            metrics: Dictionary containing error_rate and latency_ms.

        Returns:
            VerificationResult
        """

        if not isinstance(metrics, dict):
            return VerificationResult(
                False,
                "Invalid metrics data"
            )

        error_rate = metrics.get("error_rate")
        latency_ms = metrics.get("latency_ms")

        # Required metrics are missing.
        if error_rate is None or latency_ms is None:
            return VerificationResult(
                False,
                "Missing required metrics"
            )

        # Make sure metrics are numeric.
        try:
            error_rate = float(error_rate)
            latency_ms = float(latency_ms)
        except (TypeError, ValueError):
            return VerificationResult(
                False,
                "Metrics contain invalid numeric values"
            )

        # Healthy.
        if (
                error_rate <= self.MAX_ERROR_RATE
                and latency_ms <= self.MAX_LATENCY_MS
        ):
            return VerificationResult(
                True,
                "Service metrics are healthy"
            )

        # Still unhealthy.
        return VerificationResult(
            False,
            "Service metrics are still unhealthy"
        )

    def verify_sustained(self, observations):
        """
        Verify that the service remains healthy across multiple
        observations.

        This prevents a temporary recovery from being incorrectly
        classified as a successful incident resolution.

        Args:
            observations: List of metric dictionaries.

        Returns:
            VerificationResult
        """

        if not observations:
            return VerificationResult(
                False,
                "No observations available"
            )

        for metrics in observations:

            result = self.verify(metrics)

            if not result.recovered:
                return VerificationResult(
                    False,
                    "Service became unhealthy during verification"
                )

        return VerificationResult(
            True,
            "Service remained healthy during verification"
        )


# Default verifier instance
verifier = Verifier()