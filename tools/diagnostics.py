"""
IncidentPilot - Diagnostic Tools
==================================

This module implements the diagnostic tools that a future AI
incident-response agent will use to investigate the health of the
simulated production service defined in `simulator/service.py`.

Each function below is a small, independent, reusable Python function
that reads from the simulator's in-memory state (via its endpoint
functions) and returns plain, structured Python data (dicts / lists of
dicts). Nothing here is random, non-deterministic, or dependent on an
LLM or any external service - every function returns the same output
for the same simulator state, which makes it easy to test and easy for
a future agent to reason about.

Design note: these tools call the simulator's endpoint functions
in-process (e.g. `service.get_metrics()`), rather than over HTTP, so
that they remain lightweight, dependency-free, and independently
testable without needing a running server.
"""

from typing import Dict, List, Union

from simulator import service

# ---------------------------------------------------------------------------
# Simulated log messages (deterministic, keyed by service status)
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
    """Read the current metrics from the simulator.

    Returns:
        dict: A dictionary with keys:
            - "status" (str): "healthy" or "down".
            - "error_rate" (float): the current error rate.
            - "latency_ms" (int): the current latency, in milliseconds.
    """
    metrics = service.get_metrics()
    return {
        "status": metrics.status,
        "error_rate": metrics.error_rate,
        "latency_ms": metrics.latency_ms,
    }


def check_health() -> Dict[str, Union[str, bool]]:
    """Check whether the simulated service is currently healthy.

    Returns:
        dict: A dictionary with keys:
            - "status" (str): "healthy" or "down", as reported by the simulator.
            - "is_healthy" (bool): True if status is "healthy", False otherwise.
    """
    health = service.get_health()
    return {
        "status": health.status,
        "is_healthy": health.status == "healthy",
    }


def get_current_version() -> str:
    """Get the current deployed application version.

    Returns:
        str: The current deployment version string (e.g. "v41").
    """
    version = service.get_version()
    return version.current_version


def query_logs() -> List[Dict[str, str]]:
    """Return a deterministic simulated log stream for the current state.

    The content returned depends solely on the simulator's current
    status (and, for the bad-deployment scenario, its current
    version), with no randomness involved:
        - If the service is healthy, normal application logs are
          returned (successful requests, passing health checks).
        - If the service is down because of the bad-deployment
          scenario (current_version == service.BAD_DEPLOYMENT_VERSION),
          logs are returned that explicitly tie the incident to that
          deployment: the deployed version, HTTP 503 responses, and
          the resulting error-rate/latency increase - the evidence a
          future agent needs to correlate the incident with its cause.
        - Otherwise (a generic outage not tied to a deployment),
          realistic error logs are returned (timeouts, elevated
          latency/error-rate warnings, failed health checks).

    Returns:
        list[dict]: A list of log entries, each with keys:
            - "timestamp" (str): ISO-8601 timestamp of the log entry.
            - "level" (str): "INFO", "WARNING", or "ERROR".
            - "message" (str): human-readable log message.
    """
    if service.state.status == "healthy":
        # Return a copy so callers can't mutate the shared template.
        return [dict(entry) for entry in _HEALTHY_LOG_TEMPLATE]

    if service.state.current_version == service.BAD_DEPLOYMENT_VERSION:
        return [dict(entry) for entry in _BAD_DEPLOYMENT_LOG_TEMPLATE]

    return [dict(entry) for entry in _OUTAGE_LOG_TEMPLATE]


def get_deployment_history() -> List[Dict[str, Union[str, int]]]:
    """Return a deterministic list of recent deployments.

    The list is static test/demo data representing the deployment
    history of the simulated service. Each record includes an "order"
    field - a monotonically increasing sequence number - so a future
    agent can reliably determine which deployment was most recent,
    e.g.:

        history = get_deployment_history()
        most_recent = max(history, key=lambda d: d["order"])

    Returns:
        list[dict]: A list of deployment records, each with keys:
            - "version" (str): the deployed version string.
            - "order" (int): sequence number; higher means more recent.
            - "timestamp" (str): ISO-8601 deployment timestamp.
            - "status" (str): outcome of the deployment, e.g. "success".
    """
    # Return copies so callers can't mutate the shared module-level data.
    return [dict(entry) for entry in _DEPLOYMENT_HISTORY]