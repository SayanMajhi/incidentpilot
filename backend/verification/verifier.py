"""Independent, evidence-rich recovery verification."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from backend.config import IncidentPilotSettings, get_settings
from backend.models import VerificationCheck, VerificationResult, VerificationStatus


class Verifier:
    """Determine recovery from fresh telemetry, health, and readiness evidence."""

    # Class-level defaults so callers can read the thresholds without an
    # instance; ``__init__`` overrides them from the supplied settings.
    MAX_ERROR_RATE = get_settings().recovery_max_error_rate
    MAX_LATENCY_MS = get_settings().recovery_max_latency_ms

    def __init__(self, settings: IncidentPilotSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.MAX_ERROR_RATE = self.settings.recovery_max_error_rate
        self.MAX_LATENCY_MS = self.settings.recovery_max_latency_ms

    def verify(
        self,
        metrics: Mapping[str, Any] | None,
        health: Mapping[str, Any] | None = None,
        capacity: Mapping[str, Any] | None = None,
        metrics_before: Mapping[str, Any] | None = None,
        *,
        before: Mapping[str, Any] | None = None,
    ) -> VerificationResult:
        """Verify one fresh telemetry sample with optional infrastructure checks."""
        metrics_before = metrics_before if metrics_before is not None else before
        checks = self._sample_checks(metrics)
        checks.extend(self._environment_checks(health, capacity))
        after = dict(metrics) if isinstance(metrics, Mapping) else None
        deltas = self._deltas(metrics_before, after, capacity)
        status = self._classify(checks, deltas=deltas)
        samples = [self._sample_summary(1, metrics, checks)]

        return self._result(
            status=status,
            checks=checks,
            samples=samples,
            metrics_before=metrics_before,
            metrics_after=after,
            deltas=deltas,
            health=health,
            capacity=capacity,
        )

    def verify_sustained(
        self,
        observations: Sequence[Mapping[str, Any]] | None,
        health: Mapping[str, Any] | None = None,
        capacity: Mapping[str, Any] | None = None,
        metrics_before: Mapping[str, Any] | None = None,
        *,
        before: Mapping[str, Any] | None = None,
    ) -> VerificationResult:
        """Require every independent telemetry sample to satisfy both SLOs."""
        metrics_before = metrics_before if metrics_before is not None else before
        if not observations:
            check = VerificationCheck(
                name="telemetry_available",
                passed=False,
                observed=0,
                expected="one or more fresh samples",
                message="No verification samples were available.",
            )
            return self._result(
                status=VerificationStatus.FAILED,
                checks=[check],
                samples=[],
                metrics_before=metrics_before,
                metrics_after=None,
                deltas={},
                health=health,
                capacity=capacity,
            )

        per_sample = [self._sample_checks(metrics) for metrics in observations]
        samples = [
            self._sample_summary(index, metrics, checks)
            for index, (metrics, checks) in enumerate(
                zip(observations, per_sample, strict=True),
                start=1,
            )
        ]

        checks = [
            self._aggregate_check(
                "telemetry_available",
                per_sample,
                expected=f"{len(observations)} valid samples",
            ),
            self._aggregate_check(
                "error_rate_slo",
                per_sample,
                expected=f"all samples <= {self.MAX_ERROR_RATE}",
            ),
            self._aggregate_check(
                "latency_slo",
                per_sample,
                expected=f"all samples <= {self.MAX_LATENCY_MS}ms",
            ),
            self._aggregate_check(
                "service_status",
                per_sample,
                expected="all reported statuses healthy",
                required=any(
                    self._find_check(sample_checks, "service_status").required
                    for sample_checks in per_sample
                ),
            ),
        ]
        all_samples_healthy = all(
            all(check.passed for check in sample_checks if check.required)
            for sample_checks in per_sample
        )
        checks.append(
            VerificationCheck(
                name="sustained_samples",
                passed=all_samples_healthy,
                observed=sum(
                    all(check.passed for check in sample_checks if check.required)
                    for sample_checks in per_sample
                ),
                expected=len(observations),
                message=(
                    "Every fresh telemetry sample satisfied the recovery checks."
                    if all_samples_healthy
                    else "Recovery was not sustained across every fresh telemetry sample."
                ),
            )
        )
        checks.extend(self._environment_checks(health, capacity))

        after = dict(observations[-1])
        deltas = self._deltas(metrics_before, after, capacity)
        status = self._classify(
            checks,
            deltas=deltas,
            sample_passes=[summary["passed"] for summary in samples],
        )
        return self._result(
            status=status,
            checks=checks,
            samples=samples,
            metrics_before=metrics_before,
            metrics_after=after,
            deltas=deltas,
            health=health,
            capacity=capacity,
        )

    def _sample_checks(
        self,
        metrics: Mapping[str, Any] | None,
    ) -> list[VerificationCheck]:
        available = isinstance(metrics, Mapping)
        error_rate = self._number(metrics.get("error_rate")) if available else None
        latency_ms = self._number(metrics.get("latency_ms")) if available else None
        valid = available and error_rate is not None and latency_ms is not None
        checks = [
            VerificationCheck(
                name="telemetry_available",
                passed=valid,
                observed=(
                    {
                        "error_rate": metrics.get("error_rate"),
                        "latency_ms": metrics.get("latency_ms"),
                    }
                    if available
                    else None
                ),
                expected="numeric error_rate and latency_ms",
                message=(
                    "Required telemetry is available."
                    if valid
                    else "Required numeric telemetry is missing or invalid."
                ),
            ),
            VerificationCheck(
                name="error_rate_slo",
                passed=error_rate is not None and error_rate <= self.MAX_ERROR_RATE,
                observed=error_rate,
                expected={"maximum": self.MAX_ERROR_RATE},
                message=(
                    f"Error rate is within the {self.MAX_ERROR_RATE:.0%} recovery SLO."
                    if error_rate is not None and error_rate <= self.MAX_ERROR_RATE
                    else f"Error rate exceeds the {self.MAX_ERROR_RATE:.0%} recovery SLO."
                ),
            ),
            VerificationCheck(
                name="latency_slo",
                passed=latency_ms is not None and latency_ms <= self.MAX_LATENCY_MS,
                observed=latency_ms,
                expected={"maximum_ms": self.MAX_LATENCY_MS},
                message=(
                    f"Latency is within the {self.MAX_LATENCY_MS}ms recovery SLO."
                    if latency_ms is not None and latency_ms <= self.MAX_LATENCY_MS
                    else f"Latency exceeds the {self.MAX_LATENCY_MS}ms recovery SLO."
                ),
            ),
        ]

        reported_status = metrics.get("status") if available else None
        status_supplied = reported_status is not None
        checks.append(
            VerificationCheck(
                name="service_status",
                passed=not status_supplied or reported_status == "healthy",
                required=status_supplied,
                observed=reported_status,
                expected="healthy",
                message=(
                    "Reported service status is healthy."
                    if reported_status == "healthy"
                    else "Service status was not reported; numeric SLO checks remain authoritative."
                    if not status_supplied
                    else f"Reported service status is {reported_status!r}."
                ),
            )
        )
        return checks

    def _environment_checks(
        self,
        health: Mapping[str, Any] | None,
        capacity: Mapping[str, Any] | None,
    ) -> list[VerificationCheck]:
        if health is None:
            health_check = VerificationCheck(
                name="health_endpoint",
                passed=True,
                required=False,
                observed=None,
                expected="healthy when supplied",
                message="Health endpoint evidence was not supplied to this verification.",
            )
        else:
            health_passed = health.get("is_healthy") is True or (
                health.get("is_healthy") is None and health.get("status") == "healthy"
            )
            health_check = VerificationCheck(
                name="health_endpoint",
                passed=health_passed,
                observed=dict(health),
                expected={"is_healthy": True},
                message=(
                    "The independent health endpoint reports healthy."
                    if health_passed
                    else "The independent health endpoint still reports unhealthy."
                ),
            )

        if capacity is None:
            readiness_check = VerificationCheck(
                name="readiness",
                passed=True,
                required=False,
                observed=None,
                expected="all desired replicas ready when supplied",
                message="Replica readiness evidence was not supplied to this verification.",
            )
        else:
            replicas = self._integer(capacity.get("replicas"))
            ready = self._integer(capacity.get("ready_replicas"))
            readiness_supplied = replicas is not None and ready is not None
            readiness_passed = readiness_supplied and ready >= replicas and replicas >= 1
            readiness_check = VerificationCheck(
                name="readiness",
                passed=readiness_passed if readiness_supplied else True,
                required=readiness_supplied,
                observed={"replicas": replicas, "ready_replicas": ready},
                expected="ready_replicas >= replicas >= 1",
                message=(
                    "All desired replicas are ready."
                    if readiness_passed
                    else "Replica counts were supplied without readiness data."
                    if not readiness_supplied
                    else "Not all desired replicas are ready."
                ),
            )
        return [health_check, readiness_check]

    def _aggregate_check(
        self,
        name: str,
        samples: Sequence[list[VerificationCheck]],
        *,
        expected: Any,
        required: bool = True,
    ) -> VerificationCheck:
        values = [self._find_check(checks, name) for checks in samples]
        passed_count = sum(check.passed for check in values)
        return VerificationCheck(
            name=name,
            passed=passed_count == len(values),
            required=required,
            observed={"passed_samples": passed_count, "total_samples": len(values)},
            expected=expected,
            message=(
                f"All {len(values)} samples passed {name}."
                if passed_count == len(values)
                else f"{passed_count} of {len(values)} samples passed {name}."
            ),
        )

    @staticmethod
    def _find_check(checks: Sequence[VerificationCheck], name: str) -> VerificationCheck:
        return next(check for check in checks if check.name == name)

    @staticmethod
    def _sample_summary(
        index: int,
        metrics: Mapping[str, Any] | None,
        checks: Sequence[VerificationCheck],
    ) -> dict[str, Any]:
        required = [check for check in checks if check.required]
        return {
            "sample": index,
            "error_rate": metrics.get("error_rate") if isinstance(metrics, Mapping) else None,
            "latency_ms": metrics.get("latency_ms") if isinstance(metrics, Mapping) else None,
            "status": metrics.get("status") if isinstance(metrics, Mapping) else None,
            "passed": bool(required) and all(check.passed for check in required),
        }

    def _classify(
        self,
        checks: Sequence[VerificationCheck],
        *,
        deltas: Mapping[str, Any],
        sample_passes: Sequence[bool] | None = None,
    ) -> VerificationStatus:
        required = [check for check in checks if check.required]
        if required and all(check.passed for check in required):
            return VerificationStatus.RECOVERED

        improvement = any(
            isinstance(value, (int, float)) and value < 0
            for key, value in deltas.items()
            if key in {"error_rate", "latency_ms"}
        )
        mixed_samples = bool(sample_passes) and any(sample_passes) and not all(sample_passes)
        # Readiness is deliberately excluded: a workload can run every desired
        # replica and still serve a total outage, so replica readiness alone is
        # not evidence that anything recovered.
        meaningful_pass = any(
            check.passed and check.name in {"error_rate_slo", "latency_slo", "health_endpoint"}
            for check in required
        )
        if improvement or mixed_samples or meaningful_pass:
            return VerificationStatus.PARTIAL
        return VerificationStatus.FAILED

    def _result(
        self,
        *,
        status: VerificationStatus,
        checks: list[VerificationCheck],
        samples: list[dict[str, Any]],
        metrics_before: Mapping[str, Any] | None,
        metrics_after: Mapping[str, Any] | None,
        deltas: dict[str, Any],
        health: Mapping[str, Any] | None,
        capacity: Mapping[str, Any] | None,
    ) -> VerificationResult:
        failed_names = [
            check.name for check in checks if check.required and not check.passed
        ]
        if status is VerificationStatus.RECOVERED:
            reason = "All required recovery checks passed across fresh telemetry."
        elif status is VerificationStatus.PARTIAL:
            reason = "Recovery is partial; checks still failing: " + ", ".join(failed_names)
        else:
            reason = "Recovery checks failed: " + ", ".join(failed_names)

        readiness = None
        if capacity is not None:
            readiness = {
                "replicas": capacity.get("replicas"),
                "ready_replicas": capacity.get("ready_replicas"),
            }
        return VerificationResult(
            status=status,
            recovered=status is VerificationStatus.RECOVERED,
            reason=reason,
            checks=checks,
            samples=samples,
            sample_count=len(samples),
            metrics_before=dict(metrics_before) if metrics_before is not None else None,
            metrics_after=dict(metrics_after) if metrics_after is not None else None,
            deltas=deltas,
            readiness=readiness,
            telemetry={
                "metrics": dict(metrics_after) if metrics_after is not None else None,
                "health": dict(health) if health is not None else None,
                "capacity": dict(capacity) if capacity is not None else None,
                "samples": len(samples),
                "sample_summaries": samples,
            },
        )

    @classmethod
    def _deltas(
        cls,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        capacity: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if before is None or after is None:
            return {}
        deltas: dict[str, Any] = {}
        for name in ("error_rate", "latency_ms"):
            old = cls._number(before.get(name))
            new = cls._number(after.get(name))
            if old is not None and new is not None:
                deltas[name] = round(new - old, 6)
        old_replicas = cls._number(before.get("replicas"))
        new_replicas = cls._number(
            capacity.get("replicas") if capacity is not None else after.get("replicas")
        )
        if old_replicas is not None and new_replicas is not None:
            deltas["replicas"] = round(new_replicas - old_replicas, 6)
        return deltas

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _integer(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None


verifier = Verifier()
