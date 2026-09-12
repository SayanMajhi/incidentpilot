"""Validated settings for the Kubernetes adapter.

Everything the adapter may touch is decided here, once, and then frozen:

* the namespace, which can only ever be ``incidentpilot``;
* the single target Deployment and the Service used for probing, each of
  which must appear in an explicit allow-list;
* the kubeconfig contexts the adapter may connect through - local
  development clusters only by default;
* replica bounds, which may be tightened but never loosened beyond the
  shared SLO bounds the safety policy enforces.

Misconfiguration raises immediately rather than silently widening scope.
"""

import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from backend.infrastructure.base import InfrastructureSafetyError
from backend.shared import slo

#: The only namespace IncidentPilot may ever operate in.
ALLOWED_NAMESPACE = "incidentpilot"

#: Label a Deployment must carry before IncidentPilot will modify it.
MANAGED_LABEL_KEY = "incidentpilot.io/managed"
MANAGED_LABEL_VALUE = "true"

#: Pod-template label that carries the application version.
VERSION_LABEL = "app.kubernetes.io/version"

DEFAULT_DEPLOYMENT = "incidentpilot-demo"
DEFAULT_SERVICE = "incidentpilot-demo"
DEFAULT_SERVICE_PORT = "http"

#: Local development clusters: kind (cluster named "incidentpilot"),
#: minikube, and Docker Desktop.
DEFAULT_ALLOWED_CONTEXTS = ("kind-incidentpilot", "minikube", "docker-desktop")

# RFC 1123 label: what Kubernetes itself requires of namespace, Deployment and
# Service names. Rejecting anything else rules out selectors, paths and
# wildcards being smuggled in as a "name".
_DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
_PORT_NAME = re.compile(r"^([a-z0-9]([-a-z0-9]{0,13}[a-z0-9])?|[0-9]{1,5})$")
_PROBE_PATH = re.compile(r"^/[A-Za-z0-9._~/-]{0,200}$")
_CONTEXT_NAME = re.compile(r"^[A-Za-z0-9._@:/-]{1,253}$")


def _split(value: Optional[str], default: Tuple[str, ...]) -> Tuple[str, ...]:
    if value is None or not value.strip():
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise InfrastructureSafetyError(f"{key} must be an integer, got {raw!r}.") from error


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise InfrastructureSafetyError(f"{key} must be a number, got {raw!r}.") from error


def is_dns_label(value: object) -> bool:
    return isinstance(value, str) and bool(_DNS_LABEL.match(value))


@dataclass(frozen=True)
class KubernetesSettings:
    namespace: str = ALLOWED_NAMESPACE
    deployment: str = DEFAULT_DEPLOYMENT
    service: str = DEFAULT_SERVICE
    service_port: str = DEFAULT_SERVICE_PORT
    probe_path: str = "/"
    allowed_deployments: Tuple[str, ...] = (DEFAULT_DEPLOYMENT,)
    allowed_services: Tuple[str, ...] = (DEFAULT_SERVICE,)
    context: Optional[str] = None
    allowed_contexts: Tuple[str, ...] = DEFAULT_ALLOWED_CONTEXTS
    min_replicas: int = slo.MIN_REPLICAS
    max_replicas: int = slo.MAX_REPLICAS
    probe_samples: int = 5
    probe_timeout_seconds: float = 2.0
    log_tail_lines: int = 20
    max_pods_for_logs: int = 3

    def __post_init__(self) -> None:
        if self.namespace != ALLOWED_NAMESPACE:
            raise InfrastructureSafetyError(
                f"IncidentPilot may only operate in the {ALLOWED_NAMESPACE!r} "
                f"namespace, not {self.namespace!r}."
            )

        for label, names in (
                ("K8S_ALLOWED_DEPLOYMENTS", self.allowed_deployments),
                ("K8S_ALLOWED_SERVICES", self.allowed_services),
        ):
            if not names:
                raise InfrastructureSafetyError(f"{label} must list at least one name.")
            invalid = [name for name in names if not is_dns_label(name)]
            if invalid:
                raise InfrastructureSafetyError(f"{label} contains invalid names: {invalid}.")

        if not is_dns_label(self.deployment) or self.deployment not in self.allowed_deployments:
            raise InfrastructureSafetyError(
                f"Deployment {self.deployment!r} is not in the allow-list "
                f"{list(self.allowed_deployments)}."
            )

        if not is_dns_label(self.service) or self.service not in self.allowed_services:
            raise InfrastructureSafetyError(
                f"Service {self.service!r} is not in the allow-list "
                f"{list(self.allowed_services)}."
            )

        if not _PORT_NAME.match(self.service_port):
            raise InfrastructureSafetyError(f"Invalid service port {self.service_port!r}.")

        if not _PROBE_PATH.match(self.probe_path) or ".." in self.probe_path:
            raise InfrastructureSafetyError(f"Invalid probe path {self.probe_path!r}.")

        if not self.allowed_contexts or any(
                not _CONTEXT_NAME.match(name) for name in self.allowed_contexts
        ):
            raise InfrastructureSafetyError("K8S_ALLOWED_CONTEXTS must list valid context names.")

        if self.context is not None and self.context not in self.allowed_contexts:
            raise InfrastructureSafetyError(
                f"Kubernetes context {self.context!r} is not in the allow-list "
                f"{list(self.allowed_contexts)}."
            )

        # Bounds may be narrowed, never widened past what the safety policy
        # approves - otherwise the gate and the executor would disagree.
        if not (slo.MIN_REPLICAS <= self.min_replicas <= self.max_replicas <= slo.MAX_REPLICAS):
            raise InfrastructureSafetyError(
                f"Replica bounds [{self.min_replicas}, {self.max_replicas}] must lie "
                f"within [{slo.MIN_REPLICAS}, {slo.MAX_REPLICAS}]."
            )

        if not 1 <= self.probe_samples <= 20:
            raise InfrastructureSafetyError("K8S_PROBE_SAMPLES must be between 1 and 20.")

        if not 0 < self.probe_timeout_seconds <= 10:
            raise InfrastructureSafetyError("K8S_PROBE_TIMEOUT_SECONDS must be in (0, 10].")

        if not 1 <= self.log_tail_lines <= 200:
            raise InfrastructureSafetyError("K8S_LOG_TAIL_LINES must be between 1 and 200.")

    @property
    def probe_timeout_ms(self) -> int:
        return int(self.probe_timeout_seconds * 1000)

    def assert_namespace(self, namespace: object) -> None:
        """Refuse any request aimed outside the permitted namespace."""
        if namespace != self.namespace:
            raise InfrastructureSafetyError(
                f"Refusing to access namespace {namespace!r}; only "
                f"{self.namespace!r} is permitted."
            )

    def assert_context(self, context: object) -> None:
        """Refuse to use a kubeconfig context that is not allow-listed."""
        if context not in self.allowed_contexts:
            raise InfrastructureSafetyError(
                f"Kubernetes context {context!r} is not in the allow-list "
                f"{list(self.allowed_contexts)}. IncidentPilot only connects "
                "to local development clusters."
            )

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "KubernetesSettings":
        env = os.environ if env is None else env
        deployment = env.get("K8S_DEPLOYMENT") or DEFAULT_DEPLOYMENT
        service = env.get("K8S_SERVICE") or DEFAULT_SERVICE

        return cls(
            namespace=env.get("K8S_NAMESPACE") or ALLOWED_NAMESPACE,
            deployment=deployment,
            service=service,
            service_port=env.get("K8S_SERVICE_PORT") or DEFAULT_SERVICE_PORT,
            probe_path=env.get("K8S_PROBE_PATH") or "/",
            allowed_deployments=_split(env.get("K8S_ALLOWED_DEPLOYMENTS"), (DEFAULT_DEPLOYMENT,)),
            allowed_services=_split(env.get("K8S_ALLOWED_SERVICES"), (DEFAULT_SERVICE,)),
            context=env.get("K8S_CONTEXT") or None,
            allowed_contexts=_split(env.get("K8S_ALLOWED_CONTEXTS"), DEFAULT_ALLOWED_CONTEXTS),
            min_replicas=_int(env, "K8S_MIN_REPLICAS", slo.MIN_REPLICAS),
            max_replicas=_int(env, "K8S_MAX_REPLICAS", slo.MAX_REPLICAS),
            probe_samples=_int(env, "K8S_PROBE_SAMPLES", 5),
            probe_timeout_seconds=_float(env, "K8S_PROBE_TIMEOUT_SECONDS", 2.0),
            log_tail_lines=_int(env, "K8S_LOG_TAIL_LINES", 20),
        )
