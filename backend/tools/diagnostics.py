"""
IncidentPilot - Diagnostic Tools
=================================

This module implements the diagnostic tools that a future AI
incident-response agent will use to investigate the health of the
simulated production service defined in `backend/simulator/service.py`.

Each function below is a small, independent, reusable Python function
that reads from the simulator's in-memory state and returns plain,
structured Python data.

Nothing here is random, non-deterministic, or dependent on an LLM or
any external service.
"""

from typing import Dict, List, Union

from backend.simulator import service


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


def _capacity_pressure_logs() -> List[Dict[str, str]]:
    """Logs a service emits while demand exceeds its provisioned capacity."""
    replicas = service.get_replicas()
    utilization_pct = int(round(service.capacity_utilization() * 100))

    return [
        {
            "timestamp": "2026-09-10T09:15:00Z",
            "level": "ERROR",
            "message": (
                "Connection pool exhausted: all upstream connections are in "
                f"use across {replicas} replica(s)."
            ),
        },
        {
            "timestamp": "2026-09-10T09:15:02Z",
            "level": "ERROR",
            "message": "POST /api/checkout rejected: request queue is full.",
        },
        {
            "timestamp": "2026-09-10T09:15:04Z",
            "level": "WARNING",
            "message": (
                f"Resource pressure: CPU utilization at {utilization_pct}% of "
                "provisioned capacity."
            ),
        },
        {
            "timestamp": "2026-09-10T09:15:06Z",
            "level": "INFO",
            "message": "Worker processes are responsive and accepting connections.",
        },
    ]


def query_logs() -> List[Dict[str, str]]:
    """Return deterministic simulated logs for the current service state.

    Logs are rendered from whichever incident cause is currently dominant,
    never from the name of the active scenario:

    1. Healthy service
    2. Hung workers - requests time out before reaching application code,
       so they mask any application-level evidence behind them
    3. Bad deployment running
    4. Capacity shortfall
    5. Unhealthy for an unmodelled reason - generic outage symptoms

    Because hung workers mask the other causes, clearing them (a restart)
    can reveal evidence that simply was not observable before.
    """

    if service.state.status == "healthy":
        return [
            dict(entry)
            for entry in _HEALTHY_LOG_TEMPLATE
        ]

    if service.transient_fault_active():
        return [
            dict(entry)
            for entry in _OUTAGE_LOG_TEMPLATE
        ]

    if service.deployment_regression_active():
        return [
            dict(entry)
            for entry in _BAD_DEPLOYMENT_LOG_TEMPLATE
        ]

    if service.capacity_utilization() > 1.0:
        return _capacity_pressure_logs()

    return [
        dict(entry)
        for entry in _OUTAGE_LOG_TEMPLATE
    ]


def get_capacity() -> Dict[str, Union[str, int, float, None]]:
    """Read provisioned replicas and utilization from the simulator.

    Hung workers stop reporting utilization, so while they are hung the
    utilization reading is unavailable rather than invented.
    """

    replicas = service.get_replicas()

    if service.transient_fault_active():
        return {
            "replicas": replicas,
            "utilization": None,
            "telemetry": "unavailable",
        }

    return {
        "replicas": replicas,
        "utilization": service.capacity_utilization(),
        "telemetry": "available",
    }


def get_deployment_history() -> List[Dict[str, Union[str, int]]]:
    """Return a deterministic list of recent deployments."""

    return [
        dict(entry)
        for entry in _DEPLOYMENT_HISTORY
    ]