"""
IncidentPilot - Remediation Tools
====================================

This module implements the remediation actions that a future AI
incident-response agent will be able to safely invoke against the
simulated production service in `backend/simulator/service.py`.

Every action here is simulated: nothing shells out, nothing touches
real infrastructure, and nothing calls an LLM. Each function mutates
only the simulator's in-memory state (or this module's own in-memory
replica count) and returns a structured dictionary describing the
outcome of that specific action.

Design principle - actions report on themselves, not on the incident:
    A remediation action can succeed or fail *as an action* (e.g. "the
    restart command was issued", "that version doesn't exist so the
    rollback was rejected", "5 replicas is outside the safe range").
    Whether that action actually fixed the underlying incident is a
    separate question that only the diagnostic tools (see
    `backend/tools/diagnostics.py`) can answer, by re-checking health/metrics
    after the action runs. None of the functions below ever claim the
    incident is "resolved" or "fixed" - that determination belongs to
    the calling agent (or a human), made deliberately, after
    verification.
"""

from typing import Dict, List, Union

from backend.shared import slo
from backend.simulator import service
from backend.tools import diagnostics

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_REPLICAS: int = slo.MIN_REPLICAS
MAX_REPLICAS: int = slo.MAX_REPLICAS

# ---------------------------------------------------------------------------
# Module-level simulated infrastructure state
# ---------------------------------------------------------------------------
# The simulator (backend/simulator/service.py) doesn't model replica count, so
# remediation.py tracks it independently, in-memory, without modifying
# backend/simulator/service.py.

_current_replicas: int = 1


# ---------------------------------------------------------------------------
# Remediation tools
# ---------------------------------------------------------------------------

def reset_replicas() -> int:
    """Reset the simulated replica count to the baseline of one.

    Exposed so ``POST /reset`` can restore replica state without reaching
    into this module's private global.
    """
    global _current_replicas
    _current_replicas = MIN_REPLICAS
    return _current_replicas


def restart_service() -> Dict[str, Union[str, bool]]:
    """Simulate restarting the application.

    A restart is modeled as clearing the simulated service's error
    rate and latency back to their healthy baseline values (the kind
    of transient-state reset a real process restart can provide).
    Restarting does NOT, by itself, mean the underlying incident is
    resolved - a bad deployment, for example, would still be bad after
    a restart. The caller is responsible for re-checking health via
    `tools.diagnostics.check_health()` or `get_metrics()` afterward.

    Returns:
        dict: A structured result with keys:
            - "action" (str): "restart_service".
            - "success" (bool): whether the restart action itself was executed.
            - "status" (str): "completed" for this simulated action.
            - "message" (str): a human-readable description of what
              happened. Deliberately does NOT claim the incident is
              resolved.
    """
    cleared = service.clear_transient_failure()

    if service.adaptive_incident_active:
        service.simulate_adaptive_restart_effect()

    detail = (
        "Transient state was cleared."
        if cleared
        else (
            "The restart completed, but the incident cause is still "
            "deployed, so transient state could not be cleared."
        )
    )

    return {
        "action": "restart_service",
        "success": True,
        "status": "completed",
        "message": (
            "Restart action was executed against the simulated service. "
            f"{detail} This reports only that the restart action itself "
            "completed - it says nothing about the underlying incident. "
            "Verify current status separately, e.g. with "
            "diagnostics.check_health()."
        ),
    }


def rollback_deployment(version: str) -> Dict[str, Union[str, bool, None]]:
    """Roll the simulated application back to a previously deployed version.

    Rollback is only permitted to a version that appears in the
    deployment history returned by
    `tools.diagnostics.get_deployment_history()`. Attempting to roll
    back to an unknown version is rejected rather than raising an
    exception, so callers (including an automated agent) can inspect
    the structured result and decide how to proceed.

    Rolling back changes the deployed version. Whether that also
    changes service status/metrics is determined deterministically by
    the simulator (see `simulator.service.simulate_rollback`): moving
    away from a version that was itself the tracked cause of an
    incident heals the service, while rolling back during an incident
    that was never tied to the deployed version does not. Either way,
    this function's returned message never makes any claim about the
    underlying incident - its actual effect must always be verified
    separately via the diagnostic tools.

    Args:
        version: The version string to roll back to (e.g. "v40").

    Returns:
        dict: A structured result with keys:
            - "action" (str): "rollback_deployment".
            - "success" (bool): True if the rollback was applied.
            - "status" (str): "success" or "rejected".
            - "message" (str): human-readable description of the outcome.
            - "requested_version" (str): the version that was requested.
            - "previous_version" (str): the version deployed before this call.
            - "current_version" (str): the version deployed after this call
              (unchanged from previous_version if the rollback was rejected).
    """
    known_versions: List[str] = [
        record["version"] for record in diagnostics.get_deployment_history()
    ]
    previous_version = service.state.current_version

    if version not in known_versions:
        return {
            "action": "rollback_deployment",
            "success": False,
            "status": "rejected",
            "message": (
                f"Rollback rejected: '{version}' is not a known version in "
                f"deployment history. Known versions: {known_versions}."
            ),
            "requested_version": version,
            "previous_version": previous_version,
            "current_version": previous_version,
        }

    service.simulate_rollback(version)

    return {
        "action": "rollback_deployment",
        "success": True,
        "status": "success",
        "message": (
            f"Rolled back deployed version from '{previous_version}' to "
            f"'{version}'. This reports only that the version change was "
            "applied - it says nothing about the underlying incident. "
            "Verify current status separately."
        ),
        "requested_version": version,
        "previous_version": previous_version,
        "current_version": version,
    }


def scale_service(replicas: int) -> Dict[str, Union[str, bool, int]]:
    """Simulate changing the number of running service replicas.

    Only a safe range of replica counts is permitted
    (MIN_REPLICAS..MAX_REPLICAS, inclusive). Values outside that range
    are rejected rather than applied, to avoid a future agent
    accidentally scaling to zero (an outage) or to an unbounded number
    (a runaway resource cost). Replica count is simulated state local
    to this module; it does not represent real infrastructure.

    Args:
        replicas: The desired number of replicas.

    Returns:
        dict: A structured result with keys:
            - "action" (str): "scale_service".
            - "success" (bool): True if the scaling request was applied.
            - "status" (str): "success" or "rejected".
            - "message" (str): human-readable description of the outcome.
            - "requested_replicas" (int): the replica count that was requested.
            - "current_replicas" (int): the replica count after this call
              (unchanged if the request was rejected).
    """
    global _current_replicas

    if replicas < MIN_REPLICAS or replicas > MAX_REPLICAS:
        return {
            "action": "scale_service",
            "success": False,
            "status": "rejected",
            "message": (
                f"Scaling rejected: {replicas} replicas is outside the safe "
                f"range [{MIN_REPLICAS}, {MAX_REPLICAS}]."
            ),
            "requested_replicas": replicas,
            "current_replicas": _current_replicas,
        }

    _current_replicas = replicas

    if service.adaptive_incident_active:
        service.simulate_adaptive_scale_effect()

    return {
        "action": "scale_service",
        "success": True,
        "status": "success",
        "message": (
            f"Service scaled to {replicas} replica(s). This reports only "
            "that the scaling request was applied - it says nothing about "
            "the underlying incident. Verify current status separately."
        ),
        "requested_replicas": replicas,
        "current_replicas": replicas,
    }


def get_current_replicas() -> int:
    """Return the current simulated replica count.

    This is a small helper (not a remediation action itself) that lets
    callers and tests inspect the module-level replica state tracked
    by `scale_service()`.

    Returns:
        int: The current number of simulated replicas.
    """
    return _current_replicas
