"""Execution environment contract used by IncidentController.

The controller observes and acts only through this interface. This keeps the
same observe > investigate > diagnose > decide > safety > act > verify loop
working with both the in-memory simulator and a local Kubernetes cluster.

Every method returns plain JSON data in the format already used by the
decision engine and dashboard:

    get_metrics()            -> {"status", "error_rate", "latency_ms", ...}
    check_health()           -> {"status", "is_healthy"}
    get_current_version()    -> "v41"
    get_capacity()           -> {"replicas", "utilization", "telemetry"}
    query_logs()             -> [{"timestamp", "level", "message"}, ...]
    get_deployment_history() -> [{"version", "order", "timestamp", "status"}, ...]

Remediation methods only report the action itself, including "action",
"success", "status", and "message". They never claim that the incident is
resolved. Recovery is always verified separately using fresh telemetry.

Implementations expose a fixed set of operations. There is no generic
"run a command" or "apply a resource" capability.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class InfrastructureError(RuntimeError):
    """The environment is not configured correctly or could not be reached."""


class InfrastructureSafetyError(InfrastructureError):
    """The operation was refused because it is outside the permitted scope."""


class Infrastructure(ABC):
    """An environment that IncidentController can monitor and fix."""

    #: Short identifier, e.g. "simulator" or "kubernetes".
    name: str = "abstract"

    #: Whether demo scenarios can be injected (simulator only).
    supports_scenario_injection: bool = False

    @abstractmethod
    def describe(self) -> Dict[str, Any]:
        """Identify the environment and its target without contacting it."""

    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """Get the current service-level metrics."""

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """Check whether the service is currently healthy."""

    @abstractmethod
    def get_current_version(self) -> str:
        """Get the version that is currently deployed."""

    @abstractmethod
    def get_capacity(self) -> Dict[str, Any]:
        """Get the number of replicas and available utilization data."""

    @abstractmethod
    def query_logs(self) -> List[Dict[str, str]]:
        """Get recent logs for troubleshooting."""

    @abstractmethod
    def get_deployment_history(self) -> List[Dict[str, Any]]:
        """Get previously deployed versions, with ``order`` increasing with recency."""

    @abstractmethod
    def restart_service(self) -> Dict[str, Any]:
        """Restart the service."""

    @abstractmethod
    def rollback_deployment(self, version: str) -> Dict[str, Any]:
        """Roll the service back to a previously deployed version."""

    @abstractmethod
    def scale_service(self, replicas: int) -> Dict[str, Any]:
        """Scale the service to a bounded number of replicas."""

    def wait_for_reconciliation(self, action_result: Dict[str, Any]) -> Dict[str, Any] | None:
        """Optionally wait for an asynchronous remediation to settle.

        Simulator actions take effect synchronously, so the default is a
        no-op.  Kubernetes overrides this after restart, rollback and scale
        requests: the API accepting a patch is not proof that the workload
        has finished reconciling.
        """
        return None
