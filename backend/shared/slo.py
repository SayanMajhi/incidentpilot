"""Shared SLO thresholds and action bounds exposed by ``GET /config``.

``RECOVERY_*`` defines recovery. ``ELEVATED_*`` only signals evidence worth
investigating and must not be treated as a recovery verdict.
"""

from typing import Any, Dict

HEALTHY_ERROR_RATE: float = 0.01
HEALTHY_LATENCY_MS: int = 100

# Values the simulator injects when an incident is active.
OUTAGE_ERROR_RATE: float = 0.70
OUTAGE_LATENCY_MS: int = 1000

RECOVERY_MAX_ERROR_RATE: float = 0.05
RECOVERY_MAX_LATENCY_MS: int = 200

# Diagnosis evidence bar - looser than the SLO, used only to weigh evidence
ELEVATED_ERROR_RATE: float = 0.10
ELEVATED_LATENCY_MS: int = 300

MIN_REPLICAS: int = 1
MAX_REPLICAS: int = 3

# Upper bound of the dashboard latency chart's y-axis, in milliseconds.
LATENCY_CHART_CEILING_MS: int = 1200

INITIAL_VERSION: str = "v41"
BAD_DEPLOYMENT_VERSION: str = "v42"


def as_dict() -> Dict[str, Any]:
    """Return JSON-friendly configuration for the dashboard."""
    return {
        "recovery": {
            "max_error_rate": RECOVERY_MAX_ERROR_RATE,
            "max_latency_ms": RECOVERY_MAX_LATENCY_MS,
        },
        "elevated": {
            "error_rate": ELEVATED_ERROR_RATE,
            "latency_ms": ELEVATED_LATENCY_MS,
        },
        "replicas": {
            "min": MIN_REPLICAS,
            "max": MAX_REPLICAS,
        },
        "baseline": {
            "error_rate": HEALTHY_ERROR_RATE,
            "latency_ms": HEALTHY_LATENCY_MS,
            "version": INITIAL_VERSION,
        },
        "chart": {
            "latency_ceiling_ms": LATENCY_CHART_CEILING_MS,
        },
        "bad_deployment_version": BAD_DEPLOYMENT_VERSION,
    }
