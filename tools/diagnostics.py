"""
IncidentPilot - Diagnostic Tools
=================================

This module implements the diagnostic tools that a future AI
incident-response agent will use to investigate the health of the
simulated production service defined in `simulator/service.py`.

Each function below is a small, independent, reusable Python function
that reads from the simulator's in-memory state and returns plain,
structured Python data.

Nothing here is random, non-deterministic, or dependent on an LLM or
any external service.
"""

from typing import Dict, List, Union

from simulator import service


# ---------------------------------------------------------------------------
# Simulated log messages
# ---------------------------------------------------------------------------

_HEALTHY_LOG_TEMPLATE: List[Dict[str, str]] = [
    {
        "timestamp": "2026-09-10T09:00:00Z",
        "level": "INFO",
        "message": "GET /api/orders completed with status 200 in 98ms.",
    },
    {
        "timestamp": "2026-09-10T09:00:05Z",
        "level": "INFO",
        "message": "POST /api/checkout completed with status 200 in 104ms.",
    },
    {
        "timestamp": "2026-09-10T09:00:10Z",
        "level": "INFO",
        "message": "Scheduled health check passed.",
    },
]


_OUTAGE_LOG_TEMPLATE: List[Dict[str, str]] = [
    {
        "timestamp": "2026-09-10T09:05:00Z",
        "level": "ERROR",
        "message": "GET /api/orders failed with status 503 after a 1000ms timeout.",
    },
    {
        "timestamp": "2026-09-10T09:05:02Z",
        "level": "ERROR",
        "message": "POST /api/checkout failed: upstream connection timeout.",
    },
    {
        "timestamp": "2026-09-10T09:05:04Z",
        "level": "WARNING",
        "message": "Elevated latency detected on the primary request path.",
    },
    {
        "timestamp": "2026-09-10T09:05:06Z",
        "level": "ERROR",
        "message": "Error rate has crossed the alerting threshold.",
    },
    {
        "timestamp": "2026-09-10T09:05:08Z",
        "level": "ERROR",
        "message": "Scheduled health check failed: service status is 'down'.",
    },
]


_BAD_DEPLOYMENT_LOG_TEMPLATE: List[Dict[str, str]] = [
    {
        "timestamp": "2026-09-10T09:10:00Z",
        "level": "ERROR",
        "message": "Deployment v42 introduced application failures.",
    },
    {
        "timestamp": "2026-09-10T09:10:02Z",
        "level": "ERROR",
        "message": "HTTP 503 responses increased after deployment v42.",
    },
    {
        "timestamp": "2026-09-10T09:10:04Z",
        "level": "WARNING",
        "message": "Error rate exceeded threshold after deployment v42.",
    },
    {
        "timestamp": "2026-09-10T09:10:06Z",
        "level": "WARNING",
        "message": "Latency increased after deployment v42.",
    },
    {
        "timestamp": "2026-09-10T09:10:08Z",
        "level": "ERROR",
        "message": "Scheduled health check failed: service status is 'down'.",
    },
]


# ---------------------------------------------------------------------------
# Deterministic deployment history
# ---------------------------------------------------------------------------

_DEPLOYMENT_HISTORY: List[Dict[str, Union[str, int]]] = [
    {
        "version": "v39",
        "order": 1,
        "timestamp": "2026-09-07T10:00:00Z",
        "status": "success",
    },
    {
        "version": "v40",
        "order": 2,
        "timestamp": "2026-09-08T10:00:00Z",
        "status": "success",
    },
    {
        "version": "v41",
        "order": 3,
        "timestamp": "2026-09-09T10:00:00Z",
        "status": "success",
    },
]


# ---------------------------------------------------------------------------
# Diagnostic tools
# ---------------------------------------------------------------------------

def get_metrics() -> Dict[str, Union[str, float, int]]:
    """Read the current metrics from the simulator."""

    metrics = service.get_metrics()

    return {
        "status": metrics.status,
        "error_rate": metrics.error_rate,
        "latency_ms": metrics.latency_ms,
    }


def check_health() -> Dict[str, Union[str, bool]]:
    """Check whether the simulated service is currently healthy."""

    health = service.get_health()

    return {
        "status": health.status,
        "is_healthy": health.status == "healthy",
    }


def get_current_version() -> str:
    """Get the current deployed application version."""

    version = service.get_version()

    return version.current_version


def query_logs() -> List[Dict[str, str]]:
    """Return deterministic simulated logs for the current service state.

    The diagnostic evidence changes depending on the current incident:

    1. Healthy service
    2. Adaptive incident after failed restart
    3. Bad deployment
    4. Generic outage

    The adaptive incident is deliberately checked before the generic
    outage because its state is also unhealthy.
    """

    # -----------------------------------------------------------------------
    # HEALTHY SERVICE
    # -----------------------------------------------------------------------

    if service.state.status == "healthy":
        return [
            dict(entry)
            for entry in _HEALTHY_LOG_TEMPLATE
        ]

    # -----------------------------------------------------------------------
    # ADAPTIVE INCIDENT AFTER FAILED RESTART
    # -----------------------------------------------------------------------

    if (
            service.adaptive_incident_active
            and service.adaptive_restart_attempted
    ):
        adaptive_logs = [
            dict(entry)
            for entry in _OUTAGE_LOG_TEMPLATE
        ]

        adaptive_logs.append(
            {
                "timestamp": "2026-09-10T09:05:10Z",
                "level": "ERROR",
                "message": (
                    "Connection pool exhausted: upstream connections are "
                    "saturated and requests are timing out."
                ),
            }
        )

        adaptive_logs.append(
            {
                "timestamp": "2026-09-10T09:05:12Z",
                "level": "WARNING",
                "message": (
                    "Resource pressure detected after restart; "
                    "additional service capacity may be required."
                ),
            }
        )

        return adaptive_logs

    # -----------------------------------------------------------------------
    # BAD DEPLOYMENT
    # -----------------------------------------------------------------------

    if service.state.current_version == service.BAD_DEPLOYMENT_VERSION:
        return [
            dict(entry)
            for entry in _BAD_DEPLOYMENT_LOG_TEMPLATE
        ]

    # -----------------------------------------------------------------------
    # GENERIC OUTAGE
    # -----------------------------------------------------------------------

    return [
        dict(entry)
        for entry in _OUTAGE_LOG_TEMPLATE
    ]


def get_deployment_history() -> List[Dict[str, Union[str, int]]]:
    """Return a deterministic list of recent deployments."""

    return [
        dict(entry)
        for entry in _DEPLOYMENT_HISTORY
    ]