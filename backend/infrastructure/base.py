"""The execution-environment contract IncidentController operates through.

The controller observes and acts only through this interface, so the same
observe -> investigate -> diagnose -> decide -> safety -> act -> verify loop
runs unchanged against the in-memory simulator or a local Kubernetes cluster.

Every method returns plain, JSON-friendly data in the shapes the decision
engine and dashboard already understand:

* ``get_metrics()``            -> ``{"status", "error_rate", "latency_ms", ...}``
* ``check_health()``           -> ``{"status", "is_healthy"}``
* ``get_current_version()``    -> ``"v41"``
* ``get_capacity()``           -> ``{"replicas", "utilization", "telemetry"}``
* ``query_logs()``             -> ``[{"timestamp", "level", "message"}, ...]``
* ``get_deployment_history()`` -> ``[{"version", "order", "timestamp", "status"}, ...]``

Remediation methods report only on the action itself (``action``,
``success``, ``status``, ``message``) and never claim the incident is
resolved; recovery is always verified separately from fresh telemetry.

Implementations expose a fixed set of operations. There is deliberately no
generic "run a command" or "apply a resource" capability.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class InfrastructureError(RuntimeError):
    """The environment is misconfigured or could not be reached."""


class InfrastructureSafetyError(InfrastructureError):
    """An operation was refused because it falls outside the permitted scope."""


class Infrastructure(ABC):
    """An environment IncidentController can observe and remediate."""

    #: Short identifier, e.g. "simulator" or "kubernetes".
    name: str = "abstract"

    #: Whether demo scenarios can be injected (simulator only).
    supports_scenario_injection: bool = False

    @abstractmethod
    def describe(self) -> Dict[str, Any]:
        """Identify the environment and its target, without contacting it."""

    # -- Observation -------------------------------------------------------

    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """Current service-level indicators."""

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """Whether the service is currently healthy."""

    @abstractmethod
    def get_current_version(self) -> str:
        """The version currently deployed."""

    @abstractmethod
    def get_capacity(self) -> Dict[str, Any]:
        """Provisioned replicas and, where measurable, utilization."""

    @abstractmethod
    def query_logs(self) -> List[Dict[str, str]]:
        """Recent diagnostic log entries."""

    @abstractmethod
    def get_deployment_history(self) -> List[Dict[str, Any]]:
        """Previously deployed versions, with ``order`` increasing with recency."""

    # -- Remediation -------------------------------------------------------

    @abstractmethod
    def restart_service(self) -> Dict[str, Any]:
        """Restart the service."""

    @abstractmethod
    def rollback_deployment(self, version: str) -> Dict[str, Any]:
        """Roll the service back to a previously deployed version."""

    @abstractmethod
    def scale_service(self, replicas: int) -> Dict[str, Any]:
        """Scale the service to a bounded number of replicas."""
