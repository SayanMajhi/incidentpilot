class VerificationResult:
    def __init__(self, recovered, reason):
        self.recovered = recovered
        self.reason = reason


class Verifier:
    def verify(self, metrics):
        error_rate = metrics.get("error_rate")
        latency_ms = metrics.get("latency_ms")

        if error_rate is None or latency_ms is None:
            return VerificationResult(
                False,
                "Missing required metrics"
            )

        if error_rate <= 0.05 and latency_ms <= 200:
            return VerificationResult(
                True,
                "Service metrics are healthy"
            )

        return VerificationResult(
            False,
            "Service metrics are still unhealthy"
        )

    def verify_sustained(self, observations):
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


verifier = Verifier()