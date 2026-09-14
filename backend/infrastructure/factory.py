"""Select the execution environment from configuration.

``ENVIRONMENT`` chooses the adapter:

* ``simulator``  (default) - the in-memory simulator; needs nothing else.
* ``kubernetes`` - a local cluster, restricted to the ``incidentpilot``
  namespace. See docs/kubernetes.md.

Creating the Kubernetes adapter never contacts the cluster; the connection is
made on first use, so importing the backend cannot fail just because a
cluster is not running.
"""

from contextlib import contextmanager
from typing import Iterator, Optional

from pydantic import ValidationError

from backend.config import IncidentPilotSettings
from backend.infrastructure.base import Infrastructure, InfrastructureError

SIMULATOR = "simulator"
KUBERNETES = "kubernetes"
SUPPORTED_ENVIRONMENTS = (SIMULATOR, KUBERNETES)
DEFAULT_ENVIRONMENT = SIMULATOR

_cached: Optional[Infrastructure] = None
_override: Optional[Infrastructure] = None


def selected_environment() -> str:
    """Return the configured environment name, validated."""
    try:
        value = IncidentPilotSettings().environment.value
    except ValidationError as error:
        raise InfrastructureError(
            "Unsupported ENVIRONMENT. "
            f"Supported values: {', '.join(SUPPORTED_ENVIRONMENTS)}."
        ) from error
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
    """Return the adapter the API and controller should use right now."""
    global _cached
    if _override is not None:
        return _override
    if _cached is None:
        _cached = create_infrastructure()
    return _cached


def reset_infrastructure_cache() -> None:
    """Forget the cached adapter so the next call re-reads configuration."""
    global _cached
    _cached = None


@contextmanager
def use_infrastructure(adapter: Infrastructure) -> Iterator[Infrastructure]:
    """Run a block against ``adapter`` instead of the configured environment.

    This is the single supported injection point. Tests and the Kubernetes
    dry-run script use it to drive the whole API against a different adapter
    without mutating process configuration.
    """
    global _override
    previous = _override
    _override = adapter
    try:
        yield adapter
    finally:
        _override = previous
