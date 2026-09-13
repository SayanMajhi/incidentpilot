"""Deterministic safety gate for every remediation IncidentPilot proposes.

The policy is the authoritative allow-list: it runs before any state
mutation, it is the only thing permitted to approve an action, and it shares
its replica bounds with ``backend.tools.remediation`` via
``backend.shared.slo`` so the gate can never approve an action the executor
would then reject.
"""

from typing import Any

from backend.shared import slo


class SafetyPolicy:
    """Allow-list of bounded actions the agent may execute."""

    ALLOWED_NAMESPACE = "incidentpilot"
    MIN_REPLICAS = slo.MIN_REPLICAS
    MAX_REPLICAS = slo.MAX_REPLICAS

    def allows(self, action: str, **kwargs: Any) -> bool:
        """Return True only for a known action within its declared bounds."""
        # Existing callers omit the scope because both infrastructure
        # adapters are pre-bound to the demo target. Any explicitly supplied
        # scope must still match the one namespace IncidentPilot owns.
        namespace = kwargs.get("namespace", self.ALLOWED_NAMESPACE)
        if namespace != self.ALLOWED_NAMESPACE:
            return False

        if action == "restart_service":
            return True

        if action == "scale_service":
            replicas = kwargs.get("replicas")
            return (
                isinstance(replicas, int)
                and not isinstance(replicas, bool)
                and self.MIN_REPLICAS <= replicas <= self.MAX_REPLICAS
            )

        if action == "rollback_deployment":
            version = kwargs.get("version")
            return isinstance(version, str) and bool(version.strip())

        # Explicitly destructive actions are never permitted, and anything
        # not on the allow-list above is denied by default.
        return False


policy = SafetyPolicy()
