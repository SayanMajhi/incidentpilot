"""Simulator remediation actions.

Action success reports execution only; recovery is decided by fresh diagnostics.
"""

from typing import Dict, List, Union

from backend.shared import slo
from backend.simulator.environment import simulator
from backend.tools import diagnostics

MIN_REPLICAS: int = slo.MIN_REPLICAS
MAX_REPLICAS: int = slo.MAX_REPLICAS

# Replica count is simulator state: provisioned
# capacity is one of the causes the simulator derives service health from.
# None of the tools below know which scenario is active - each one applies
# only the effect its real-world counterpart would have.


def reset_replicas() -> int:
    """Restore the baseline replica count for ``POST /reset``."""
    simulator.scale(MIN_REPLICAS)
    return simulator.get_replicas()


def restart_service() -> Dict[str, Union[str, bool]]:
    """Clear transient process state without claiming recovery."""
    cleared, mutation = simulator.clear_transient_failure()

    if cleared:
        detail = "Transient state was cleared."
    elif simulator.deployment_regression_active():
        detail = (
            "The restart completed, but the incident cause is still "
            "deployed, so transient state could not be cleared."
        )
    else:
        detail = "Worker processes were restarted."

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
        "observed_at": mutation["observed_at"],
        "before": mutation["before"],
        "after": mutation["after"],
    }


def rollback_deployment(version: str) -> Dict[str, Union[str, bool, None]]:
    """Roll back to a known version; reject unknown targets."""
    known_versions: List[str] = [
        record["version"] for record in diagnostics.get_deployment_history()
    ]
    previous_version = simulator.state.current_version

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

    mutation = simulator.rollback(version)

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
        "observed_at": mutation["observed_at"],
        "before": mutation["before"],
        "after": mutation["after"],
    }


def scale_service(replicas: int) -> Dict[str, Union[str, bool, int]]:
    """Apply a replica count within the configured safety bounds."""
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
            "current_replicas": simulator.get_replicas(),
        }

    mutation = simulator.scale(replicas)

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
        "observed_at": mutation["observed_at"],
        "before": mutation["before"],
        "after": mutation["after"],
    }


def get_current_replicas() -> int:
    return simulator.get_replicas()
