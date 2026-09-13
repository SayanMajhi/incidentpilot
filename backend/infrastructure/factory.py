"""Select the execution environment from configuration.

``ENVIRONMENT`` chooses the adapter:

* ``simulator``  (default) - the in-memory simulator; needs nothing else.
* ``kubernetes`` - a local cluster, restricted to the ``incidentpilot``
  namespace. See docs/kubernetes.md.

Creating the Kubernetes adapter never contacts the cluster; the connection is
made on first use, so importing the backend cannot fail just because a
cluster is not running.
"""

import os
from typing import Optional

from backend.infrastructure.base import Infrastructure, InfrastructureError

SIMULATOR = "simulator"
KUBERNETES = "kubernetes"
SUPPORTED_ENVIRONMENTS = (SIMULATOR, KUBERNETES)
DEFAULT_ENVIRONMENT = SIMULATOR

_cached: Optional[Infrastructure] = None


def selected_environment() -> str:
    """Return the configured environment name, validated."""
    value = (os.getenv("ENVIRONMENT") or DEFAULT_ENVIRONMENT).strip().lower()
    if value not in SUPPORTED_ENVIRONMENTS:
        raise InfrastructureError(
            f"Unsupported ENVIRONMENT={value!r}. "
            f"Supported values: {', '.join(SUPPORTED_ENVIRONMENTS)}."
        )
    return value


def create_infrastructure(environment: Optional[str] = None) -> Infrastructure:
    """Build a new adapter for ``environment`` (or the configured one)."""
    name = (environment or selected_environment()).strip().lower()

    if name == SIMULATOR:
        from backend.infrastructure.simulator import SimulatorInfrastructure

        return SimulatorInfrastructure()

    if name == KUBERNETES:
        from backend.infrastructure.kubernetes.adapter import KubernetesInfrastructure

        return KubernetesInfrastructure()

    raise InfrastructureError(
        f"Unsupported environment {name!r}. "
        f"Supported values: {', '.join(SUPPORTED_ENVIRONMENTS)}."
    )


def get_infrastructure() -> Infrastructure:
    """Return the process-wide adapter for the configured environment."""
    global _cached
    if _cached is None:
        _cached = create_infrastructure()
    return _cached


def reset_infrastructure_cache() -> None:
    """Forget the cached adapter so the next call re-reads configuration."""
    global _cached
    _cached = None
