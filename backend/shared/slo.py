"""Single source of truth for IncidentPilot's SLO thresholds and action bounds.

Every layer that needs to answer "is this service healthy?", "is this metric
elevated enough to be evidence?", or "how many replicas may we run?" reads
these values from here. Previously the same numbers were re-declared in
``verification/verifier.py``, ``agent/decision.py``, ``safety/policy.py``,
``tools/remediation.py`` and again in the React components, which let them
drift apart (the dashboard advertised a 10%/300ms SLA while the verifier
actually required 5%/200ms, and the safety policy permitted 10 replicas while
remediation rejected anything above 5).

Two distinct threshold families live here and must not be conflated:

* ``RECOVERY_*`` - the SLO. A service at or below these values is healthy, and
  recovery is verified against them. This is the authoritative definition of
  "recovered".
* ``ELEVATED_*`` - the evidence bar used during diagnosis. Deliberately looser
  than the SLO so that genuine incidents clear it comfortably while healthy
  noise does not. Crossing it is a signal to investigate, never a verdict.

The frontend reads all of these from ``GET /config`` instead of hardcoding
them, so changing a number here changes the backend, the safety gate and the
dashboard together.
"""

from typing import Any, Dict

# ---------------------------------------------------------------------------
# Healthy baseline of the simulated service
# ---------------------------------------------------------------------------

HEALTHY_ERROR_RATE: float = 0.01
HEALTHY_LATENCY_MS: int = 100

# Values the simulator injects when an incident is active.
OUTAGE_ERROR_RATE: float = 0.70
OUTAGE_LATENCY_MS: int = 1000

# ---------------------------------------------------------------------------
# Recovery SLO - the authoritative definition of "healthy"
# ---------------------------------------------------------------------------

RECOVERY_MAX_ERROR_RATE: float = 0.05
RECOVERY_MAX_LATENCY_MS: int = 200

# ---------------------------------------------------------------------------
# Diagnosis evidence bar - looser than the SLO, used only to weigh evidence
# ---------------------------------------------------------------------------

ELEVATED_ERROR_RATE: float = 0.10
ELEVATED_LATENCY_MS: int = 300

# ---------------------------------------------------------------------------
# Bounded action limits
# ---------------------------------------------------------------------------

MIN_REPLICAS: int = 1
MAX_REPLICAS: int = 5

# Upper bound of the dashboard latency chart's y-axis, in milliseconds.
LATENCY_CHART_CEILING_MS: int = 1200

# ---------------------------------------------------------------------------
# Versions tracked by the deterministic simulator
# ---------------------------------------------------------------------------

INITIAL_VERSION: str = "v41"
BAD_DEPLOYMENT_VERSION: str = "v42"


def as_dict() -> Dict[str, Any]:
    """Return the configuration the dashboard needs, as JSON-friendly values.

    Served by ``GET /config`` so the frontend renders the same thresholds the
    backend enforces.
    """
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
