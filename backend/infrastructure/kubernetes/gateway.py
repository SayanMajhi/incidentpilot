"""The only code in IncidentPilot that talks to the Kubernetes API.

``KubernetesGateway`` exposes a short, fixed list of operations. It has no
method that accepts an arbitrary resource kind, request path, command,
manifest or patch body, so nothing above it - neither the adapter nor an LLM
proposal routed through the controller - can widen what is possible:

reads   namespace, the target Deployment, its pods, ReplicaSets and events,
        pod logs, and an HTTP probe of the target Service (via the API
        server's service proxy)
writes  replace the target Deployment's pod template (restart / rollback),
        and set its replica count through the scale subresource

Every call re-checks, independently of the adapter, that it targets the
``incidentpilot`` namespace and an allow-listed Deployment or Service, and
that replica counts are within bounds.

The ``kubernetes`` Python package is imported only when a real connection is
made, so none of this is needed to run the simulator or the normal test suite.
"""

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.infrastructure.base import InfrastructureError, InfrastructureSafetyError
from backend.infrastructure.kubernetes.config import KubernetesSettings, is_dns_label

# Pod-template keys a restart or rollback may set. Anything else in a
# proposed template is refused.
_TEMPLATE_KEYS = {"metadata", "spec"}

_LABEL_PAIR = r"[A-Za-z0-9]([A-Za-z0-9._/-]{0,251}[A-Za-z0-9])?=[A-Za-z0-9]([A-Za-z0-9._-]{0,61}[A-Za-z0-9])?"
_SELECTOR = re.compile(rf"^{_LABEL_PAIR}(,{_LABEL_PAIR}){{0,9}}$")


class KubernetesGateway:
    """Namespaced, allow-listed access to the Kubernetes API."""

    def __init__(
            self,
            settings: KubernetesSettings,
            core_api: Any,
            apps_api: Any,
            api_client: Any = None,
            api_exception: type = Exception,
    ) -> None:
        self.settings = settings
        self._core = core_api
        self._apps = apps_api
        self._api_client = api_client
        self._api_exception = api_exception
        self.context: Optional[str] = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @classmethod
    def connect(cls, settings: KubernetesSettings) -> "KubernetesGateway":
        """Connect through the local kubeconfig, refusing non-allow-listed contexts."""
        try:
            from kubernetes import client, config
            from kubernetes.client.exceptions import ApiException
        except ImportError as error:
            raise InfrastructureError(
                "Kubernetes mode needs the 'kubernetes' Python package: "
                "pip install -r requirements-kubernetes.txt"
            ) from error

        try:
            _, active_context = config.list_kube_config_contexts()
        except Exception as error:  # missing or unreadable kubeconfig
            raise InfrastructureError(
                f"Could not read a kubeconfig: {type(error).__name__}: {error}"
            ) from error

        context = settings.context or (active_context or {}).get("name")
        settings.assert_context(context)

        try:
            api_client = config.new_client_from_config(context=context)
        except Exception as error:
            raise InfrastructureError(
                f"Could not load kubeconfig context {context!r}: {error}"
            ) from error

        gateway = cls(
            settings,
            core_api=client.CoreV1Api(api_client),
            apps_api=client.AppsV1Api(api_client),
            api_client=api_client,
            api_exception=ApiException,
        )
        gateway.context = context
        return gateway

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _check_namespace(self, namespace: str) -> None:
        self.settings.assert_namespace(namespace)

    def _check_deployment(self, name: str) -> None:
        if not is_dns_label(name) or name not in self.settings.allowed_deployments:
            raise InfrastructureSafetyError(
                f"Deployment {name!r} is not in the allow-list "
                f"{list(self.settings.allowed_deployments)}."
            )

    def _check_service(self, name: str) -> None:
        if not is_dns_label(name) or name not in self.settings.allowed_services:
            raise InfrastructureSafetyError(
                f"Service {name!r} is not in the allow-list "
                f"{list(self.settings.allowed_services)}."
            )

    @staticmethod
    def _check_selector(selector: str) -> None:
        # Only plain equality selectors ("a=b,c=d") built from the target
        # Deployment's own matchLabels; never an empty (match-everything) one.
        if not isinstance(selector, str) or not _SELECTOR.match(selector):
            raise InfrastructureSafetyError(f"Invalid label selector {selector!r}.")

    @staticmethod
    def _check_name(kind: str, name: str) -> None:
        # Pod and container names generated for a Deployment are DNS labels.
        if not is_dns_label(name):
            raise InfrastructureSafetyError(f"Invalid {kind} name {name!r}.")

    def _serialize(self, obj: Any) -> Any:
        if self._api_client is not None:
            return self._api_client.sanitize_for_serialization(obj)
        return obj

    def _call(self, description: str, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except InfrastructureError:
            raise
        except self._api_exception as error:
            status = getattr(error, "status", None)
            reason = getattr(error, "reason", None) or str(error)
            raise InfrastructureError(
                f"Kubernetes API error while trying to {description}"
                + (f" (HTTP {status})" if status else "")
                + f": {reason}"
            ) from error
        except Exception as error:
            raise InfrastructureError(
                f"Could not reach the Kubernetes API to {description}: "
                f"{type(error).__name__}: {error}"
            ) from error

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def read_namespace(self, namespace: str) -> Dict[str, Any]:
        self._check_namespace(namespace)
        return self._serialize(
            self._call("read the namespace", self._core.read_namespace, namespace)
        )

    def read_deployment(self, namespace: str, name: str) -> Dict[str, Any]:
        self._check_namespace(namespace)
        self._check_deployment(name)
        return self._serialize(
            self._call(
                "read the deployment",
                self._apps.read_namespaced_deployment,
                name,
                namespace,
            )
        )

    def list_pods(self, namespace: str, label_selector: str) -> List[Dict[str, Any]]:
        self._check_namespace(namespace)
        self._check_selector(label_selector)
        result = self._serialize(
            self._call(
                "list pods",
                self._core.list_namespaced_pod,
                namespace,
                label_selector=label_selector,
            )
        )
        return list((result or {}).get("items") or [])

    def list_replica_sets(self, namespace: str, label_selector: str) -> List[Dict[str, Any]]:
        self._check_namespace(namespace)
        self._check_selector(label_selector)
        result = self._serialize(
            self._call(
                "list replica sets",
                self._apps.list_namespaced_replica_set,
                namespace,
                label_selector=label_selector,
            )
        )
        return list((result or {}).get("items") or [])

    def list_events(self, namespace: str) -> List[Dict[str, Any]]:
        self._check_namespace(namespace)
        result = self._serialize(
            self._call("list events", self._core.list_namespaced_event, namespace)
        )
        return list((result or {}).get("items") or [])

    def read_pod_log(
            self,
            namespace: str,
            pod: str,
            container: str,
            tail_lines: int,
    ) -> str:
        self._check_namespace(namespace)
        self._check_name("pod", pod)
        self._check_name("container", container)
        tail = max(1, min(int(tail_lines), self.settings.log_tail_lines))
        return self._call(
            "read pod logs",
            self._core.read_namespaced_pod_log,
            pod,
            namespace,
            container=container,
            tail_lines=tail,
            timestamps=True,
        ) or ""

    def probe_service(self, namespace: str, service: str) -> Tuple[bool, int, str]:
        """Send one HTTP GET to the Service through the API server proxy.

        Returns ``(succeeded, latency_ms, detail)``. A failed or timed-out
        request is reported as a failure at no less than the timeout, never
        as a fabricated fast success.
        """
        self._check_namespace(namespace)
        self._check_service(service)

        proxy_name = f"{service}:{self.settings.service_port}"
        timeout = self.settings.probe_timeout_seconds
        started = time.perf_counter()

        try:
            if self.settings.probe_path == "/":
                self._core.connect_get_namespaced_service_proxy(
                    proxy_name, namespace, _request_timeout=timeout,
                )
            else:
                self._core.connect_get_namespaced_service_proxy_with_path(
                    proxy_name,
                    namespace,
                    self.settings.probe_path.lstrip("/"),
                    _request_timeout=timeout,
                )
        except self._api_exception as error:
            elapsed = int((time.perf_counter() - started) * 1000)
            status = getattr(error, "status", None)
            return False, max(elapsed, 1), f"HTTP {status}" if status else str(error)
        except Exception as error:
            return False, self.settings.probe_timeout_ms, type(error).__name__

        elapsed = int((time.perf_counter() - started) * 1000)
        return True, max(elapsed, 1), "HTTP 200"

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def replace_pod_template(
            self,
            namespace: str,
            name: str,
            template: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Patch only ``spec.template`` of the allow-listed Deployment."""
        self._check_namespace(namespace)
        self._check_deployment(name)

        if not isinstance(template, dict) or not set(template) <= _TEMPLATE_KEYS:
            raise InfrastructureSafetyError(
                "A pod template patch may only contain 'metadata' and 'spec'."
            )

        body = {"spec": {"template": template}}
        return self._serialize(
            self._call(
                "patch the deployment pod template",
                self._apps.patch_namespaced_deployment,
                name,
                namespace,
                body,
            )
        )

    def scale_deployment(self, namespace: str, name: str, replicas: int) -> Dict[str, Any]:
        """Set replicas through the scale subresource, within bounds."""
        self._check_namespace(namespace)
        self._check_deployment(name)

        if (
                not isinstance(replicas, int)
                or isinstance(replicas, bool)
                or not self.settings.min_replicas <= replicas <= self.settings.max_replicas
        ):
            raise InfrastructureSafetyError(
                f"Replica count {replicas!r} is outside the permitted range "
                f"[{self.settings.min_replicas}, {self.settings.max_replicas}]."
            )

        return self._serialize(
            self._call(
                "scale the deployment",
                self._apps.patch_namespaced_deployment_scale,
                name,
                namespace,
                {"spec": {"replicas": replicas}},
            )
        )
