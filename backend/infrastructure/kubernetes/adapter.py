"""Infrastructure adapter for a local Kubernetes cluster.

Operates on exactly one allow-listed Deployment (and its Service) in the
``incidentpilot`` namespace, through :class:`KubernetesGateway`.

Observation
    metrics      HTTP probes of the Service through the API server proxy
                 (error rate = failed probes / probes, latency = median probe
                 time), combined with pod readiness. No Prometheus yet.
    health       derived from those metrics.
    version      the pod template's ``app.kubernetes.io/version`` label, or
                 the first container's image tag.
    capacity     desired and ready replicas. Utilization is reported as
                 unavailable rather than invented - there is no metrics
                 pipeline yet.
    logs         rollout conditions, container states (CrashLoopBackOff,
                 ImagePullBackOff, OOMKilled, ...), Warning events and recent
                 pod log lines, as ``{timestamp, level, message}`` entries.
    history      one entry per version from the Deployment's ReplicaSets,
                 ordered by rollout revision.

Remediation
    restart      ``kubectl rollout restart`` equivalent: stamps the pod
                 template's restartedAt annotation.
    rollback     restores the pod template of the ReplicaSet that ran the
                 requested version.
    scale        the scale subresource, within the configured bounds.

Remediation is refused unless the Deployment carries the
``incidentpilot.io/managed=true`` label, so a correctly named but unrelated
Deployment is never touched.
"""

import copy
import re
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.infrastructure.base import (
    Infrastructure,
    InfrastructureError,
    InfrastructureSafetyError,
)
from backend.infrastructure.kubernetes.config import (
    MANAGED_LABEL_KEY,
    MANAGED_LABEL_VALUE,
    VERSION_LABEL,
    KubernetesSettings,
)
from backend.infrastructure.kubernetes.gateway import KubernetesGateway
from backend.shared import slo

REVISION_ANNOTATION = "deployment.kubernetes.io/revision"
RESTARTED_AT_ANNOTATION = "kubectl.kubernetes.io/restartedAt"
POD_TEMPLATE_HASH_LABEL = "pod-template-hash"

_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

# Waiting reasons that are just a pod starting up, not a failure.
_STARTING_REASONS = {"ContainerCreating", "PodInitializing"}

_LOG_ERROR_WORDS = ("error", "exception", "fatal", "panic")

_MAX_LOG_ENTRIES = 50


def _get(obj: Any, *path: str, default: Any = None) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key)
    return default if obj is None else obj


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class KubernetesInfrastructure(Infrastructure):
    """A single allow-listed Deployment in the ``incidentpilot`` namespace."""

    name = "kubernetes"
    supports_scenario_injection = False

    def __init__(
            self,
            settings: Optional[KubernetesSettings] = None,
            gateway: Optional[KubernetesGateway] = None,
    ) -> None:
        self.settings = settings if settings is not None else KubernetesSettings.from_env()
        if gateway is not None and gateway.settings is not self.settings:
            if gateway.settings != self.settings:
                raise InfrastructureSafetyError(
                    "The gateway must be configured with the adapter's own settings."
                )
        self._gateway = gateway

    # ------------------------------------------------------------------
    # Connection and identity
    # ------------------------------------------------------------------

    @property
    def gateway(self) -> KubernetesGateway:
        """Connect on first use, never at construction."""
        if self._gateway is None:
            self._gateway = KubernetesGateway.connect(self.settings)
        return self._gateway

    def describe(self) -> Dict[str, Any]:
        context = self.settings.context
        if context is None and self._gateway is not None:
            context = self._gateway.context
        return {
            "environment": self.name,
            "namespace": self.settings.namespace,
            "deployment": self.settings.deployment,
            "service": self.settings.service,
            "context": context,
            "connected": self._gateway is not None,
            "replicas": {
                "min": self.settings.min_replicas,
                "max": self.settings.max_replicas,
            },
        }

    def check_connection(self) -> Dict[str, Any]:
        """Read-only connectivity check: namespace and target Deployment."""
        try:
            namespace = _get(self.gateway.read_namespace(self.settings.namespace), "metadata", "name")
        except InfrastructureError as error:
            # A namespace-scoped Role (deploy/kubernetes/rbac.yaml) cannot read
            # Namespace objects; reading the Deployment below still proves access.
            if "HTTP 403" not in str(error):
                raise
            namespace = f"{self.settings.namespace} (not readable with this identity)"
        deployment = self._deployment()
        return {
            "context": self.gateway.context,
            "namespace": namespace,
            "deployment": _get(deployment, "metadata", "name"),
            "managed": self._is_managed(deployment),
            "version": self._template_version(_get(deployment, "spec", "template", default={})),
            "replicas": _get(deployment, "spec", "replicas", default=1),
            "ready_replicas": _get(deployment, "status", "readyReplicas", default=0),
        }

    # ------------------------------------------------------------------
    # Resource helpers
    # ------------------------------------------------------------------

    def _deployment(self) -> Dict[str, Any]:
        deployment = self.gateway.read_deployment(
            self.settings.namespace,
            self.settings.deployment,
        )
        namespace = _get(deployment, "metadata", "namespace")
        name = _get(deployment, "metadata", "name")
        if namespace not in (None, self.settings.namespace) or name not in (None, self.settings.deployment):
            raise InfrastructureSafetyError(
                "The API returned a Deployment other than the configured target."
            )
        return deployment

    @staticmethod
    def _is_managed(deployment: Dict[str, Any]) -> bool:
        return _get(deployment, "metadata", "labels", default={}).get(MANAGED_LABEL_KEY) == MANAGED_LABEL_VALUE

    def _require_managed(self, deployment: Dict[str, Any]) -> None:
        if not self._is_managed(deployment):
            raise InfrastructureSafetyError(
                f"Deployment {self.settings.deployment!r} is not labelled "
                f"{MANAGED_LABEL_KEY}={MANAGED_LABEL_VALUE}; IncidentPilot will not modify it."
            )

    @staticmethod
    def _selector(deployment: Dict[str, Any]) -> str:
        match_labels = _get(deployment, "spec", "selector", "matchLabels", default={})
        if not match_labels:
            raise InfrastructureSafetyError(
                "The target Deployment has no matchLabels selector to scope pods by."
            )
        return ",".join(f"{key}={value}" for key, value in sorted(match_labels.items()))

    @staticmethod
    def _template_version(template: Dict[str, Any]) -> str:
        version = _get(template, "metadata", "labels", default={}).get(VERSION_LABEL)
        if version:
            return str(version)
        containers = _get(template, "spec", "containers", default=[])
        image = containers[0].get("image", "") if containers else ""
        if ":" in image.rsplit("/", 1)[-1]:
            return image.rsplit(":", 1)[-1]
        return "unknown"

    @staticmethod
    def _revision(resource: Dict[str, Any]) -> int:
        try:
            return int(_get(resource, "metadata", "annotations", default={}).get(REVISION_ANNOTATION, 0))
        except (TypeError, ValueError):
            return 0

    def _owned_replica_sets(self, deployment: Dict[str, Any]) -> List[Dict[str, Any]]:
        uid = _get(deployment, "metadata", "uid")
        replica_sets = self.gateway.list_replica_sets(
            self.settings.namespace,
            self._selector(deployment),
        )

        def owned(replica_set: Dict[str, Any]) -> bool:
            for reference in _get(replica_set, "metadata", "ownerReferences", default=[]):
                if reference.get("kind") != "Deployment":
                    continue
                if uid is not None:
                    if reference.get("uid") == uid:
                        return True
                elif reference.get("name") == self.settings.deployment:
                    return True
            return False

        return [replica_set for replica_set in replica_sets if owned(replica_set)]

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def get_metrics(self) -> Dict[str, Any]:
        deployment = self._deployment()
        desired = int(_get(deployment, "spec", "replicas", default=1))
        ready = int(_get(deployment, "status", "readyReplicas", default=0))

        samples = [
            self.gateway.probe_service(self.settings.namespace, self.settings.service)
            for _ in range(self.settings.probe_samples)
        ]
        failures = sum(1 for succeeded, _, _ in samples if not succeeded)
        error_rate = round(failures / len(samples), 2)
        latency_ms = int(statistics.median(latency for _, latency, _ in samples))

        healthy = (
                desired > 0
                and ready >= desired
                and error_rate <= slo.RECOVERY_MAX_ERROR_RATE
                and latency_ms <= slo.RECOVERY_MAX_LATENCY_MS
        )

        return {
            "status": "healthy" if healthy else "down",
            "error_rate": error_rate,
            "latency_ms": latency_ms,
            "ready_replicas": ready,
            "desired_replicas": desired,
            "probe_samples": len(samples),
            "source": "kubernetes_service_probe",
        }

    def check_health(self) -> Dict[str, Any]:
        status = self.get_metrics()["status"]
        return {"status": status, "is_healthy": status == "healthy"}

    def get_current_version(self) -> str:
        deployment = self._deployment()
        return self._template_version(_get(deployment, "spec", "template", default={}))

    def get_capacity(self) -> Dict[str, Any]:
        deployment = self._deployment()
        return {
            "replicas": int(_get(deployment, "spec", "replicas", default=1)),
            "ready_replicas": int(_get(deployment, "status", "readyReplicas", default=0)),
            "utilization": None,
            "telemetry": "unavailable",
        }

    def get_deployment_history(self) -> List[Dict[str, Any]]:
        deployment = self._deployment()
        current_revision = self._revision(deployment)

        latest_by_version: Dict[str, Dict[str, Any]] = {}
        for replica_set in self._owned_replica_sets(deployment):
            revision = self._revision(replica_set)
            version = self._template_version(_get(replica_set, "spec", "template", default={}))
            record = {
                "version": version,
                "order": revision,
                "revision": revision,
                "timestamp": _get(replica_set, "metadata", "creationTimestamp", default=""),
                "status": "current" if revision == current_revision else "superseded",
            }
            # A restart creates a new ReplicaSet for the same version; keep
            # the most recent revision of each version.
            if version not in latest_by_version or revision > latest_by_version[version]["order"]:
                latest_by_version[version] = record

        return sorted(latest_by_version.values(), key=lambda record: record["order"])

    def query_logs(self) -> List[Dict[str, str]]:
        namespace = self.settings.namespace
        deployment = self._deployment()
        name = self.settings.deployment
        selector = self._selector(deployment)
        version = self._template_version(_get(deployment, "spec", "template", default={}))
        desired = int(_get(deployment, "spec", "replicas", default=1))
        ready = int(_get(deployment, "status", "readyReplicas", default=0))

        replica_sets = self._owned_replica_sets(deployment)
        newest_revision = max((self._revision(rs) for rs in replica_sets), default=0)
        replica_set_revisions = {
            _get(rs, "metadata", "name"): self._revision(rs) for rs in replica_sets
        }
        # A rollout is still in flight while an older revision keeps serving.
        previous_revision_serving = any(
            self._revision(rs) < newest_revision and _get(rs, "status", "readyReplicas", default=0) > 0
            for rs in replica_sets
        )

        entries: List[Dict[str, str]] = []

        # -- Rollout conditions -------------------------------------------
        for condition in _get(deployment, "status", "conditions", default=[]):
            if condition.get("status") != "False":
                continue
            timestamp = condition.get("lastUpdateTime") or condition.get("lastTransitionTime") or ""
            reason = condition.get("reason", "Unknown")
            if condition.get("type") == "Progressing":
                entries.append({
                    "timestamp": timestamp,
                    "level": "ERROR",
                    "message": f"Deployment {name} rollout of {version} failed to progress: {reason}.",
                })
            elif condition.get("type") == "Available":
                entries.append({
                    "timestamp": timestamp,
                    "level": "WARNING",
                    "message": f"Workload {name} is below minimum availability ({reason}).",
                })

        # -- Pods ------------------------------------------------------------
        pods = self.gateway.list_pods(namespace, selector)
        pod_names = set()

        for pod in pods:
            pod_name = _get(pod, "metadata", "name", default="")
            pod_names.add(pod_name)
            owner = next(
                (ref.get("name") for ref in _get(pod, "metadata", "ownerReferences", default=[])
                 if ref.get("kind") == "ReplicaSet"),
                None,
            )
            in_stalled_rollout = (
                    previous_revision_serving
                    and replica_set_revisions.get(owner) == newest_revision
            )

            for status in _get(pod, "status", "containerStatuses", default=[]):
                container = status.get("name", "")
                restarts = status.get("restartCount", 0)

                waiting = _get(status, "state", "waiting")
                if waiting and waiting.get("reason") not in _STARTING_REASONS:
                    reason = waiting.get("reason", "Waiting")
                    if in_stalled_rollout:
                        message = (
                            f"Deployment {name} rollout of {version} is failing: pod "
                            f"{pod_name} container {container} is in {reason}."
                        )
                    else:
                        message = (
                            f"Pod {pod_name} container {container} is in {reason} "
                            f"(restarts: {restarts})."
                        )
                    entries.append({"timestamp": "", "level": "ERROR", "message": message})

                terminated = _get(status, "lastState", "terminated")
                if terminated:
                    reason = terminated.get("reason", "Terminated")
                    if reason == "OOMKilled":
                        message = (
                            f"Container {container} in pod {pod_name} was OOMKilled: "
                            f"out of memory (restarts: {restarts})."
                        )
                        level = "ERROR"
                    else:
                        message = (
                            f"Container {container} in pod {pod_name} last exited with "
                            f"{reason} (exit code {terminated.get('exitCode')}, restarts: {restarts})."
                        )
                        level = "WARNING"
                    entries.append({
                        "timestamp": terminated.get("finishedAt") or "",
                        "level": level,
                        "message": message,
                    })

        # -- Warning events for the Deployment, its ReplicaSets and pods -----
        related = {name} | set(replica_set_revisions) | pod_names
        for event in self.gateway.list_events(namespace):
            if event.get("type") != "Warning":
                continue
            involved = event.get("involvedObject") or {}
            if involved.get("name") not in related:
                continue
            kind = involved.get("kind", "")
            subject = "workload" if kind == "Deployment" else kind.lower()
            entries.append({
                "timestamp": (
                        event.get("lastTimestamp")
                        or event.get("eventTime")
                        or _get(event, "metadata", "creationTimestamp", default="")
                ),
                "level": "WARNING",
                "message": (
                    f"{event.get('reason', 'Warning')}: {event.get('message', '')} "
                    f"({subject} {involved.get('name')})"
                ).strip(),
            })

        # -- Recent application log lines ----------------------------------
        for pod in pods[: self.settings.max_pods_for_logs]:
            pod_name = _get(pod, "metadata", "name", default="")
            containers = _get(pod, "spec", "containers", default=[])
            if not containers:
                continue
            try:
                text = self.gateway.read_pod_log(
                    namespace,
                    pod_name,
                    containers[0].get("name", ""),
                    self.settings.log_tail_lines,
                )
            except InfrastructureError:
                continue  # e.g. the container has not started yet
            for line in text.splitlines():
                if not line.strip():
                    continue
                timestamp, _, message = line.partition(" ")
                if not message:
                    timestamp, message = "", line
                level = "ERROR" if any(word in message.lower() for word in _LOG_ERROR_WORDS) else "INFO"
                entries.append({"timestamp": timestamp, "level": level, "message": message})

        entries.sort(key=lambda entry: entry["timestamp"] or "")
        summary = {
            "timestamp": _now(),
            "level": "INFO" if ready >= desired else "WARNING",
            "message": f"Workload {name}: {ready}/{desired} replicas ready, running {version}.",
        }
        return [summary] + entries[-(_MAX_LOG_ENTRIES - 1):]

    # ------------------------------------------------------------------
    # Remediation
    # ------------------------------------------------------------------

    def restart_service(self) -> Dict[str, Any]:
        deployment = self._deployment()
        self._require_managed(deployment)

        restarted_at = _now()
        self.gateway.replace_pod_template(
            self.settings.namespace,
            self.settings.deployment,
            {"metadata": {"annotations": {RESTARTED_AT_ANNOTATION: restarted_at}}},
        )

        return {
            "action": "restart_service",
            "success": True,
            "status": "completed",
            "message": (
                f"Rollout restart requested for deployment/{self.settings.deployment} "
                f"in namespace {self.settings.namespace}. This reports only that "
                "the restart was issued - verify current status separately."
            ),
            "restarted_at": restarted_at,
        }

    def rollback_deployment(self, version: str) -> Dict[str, Any]:
        deployment = self._deployment()
        current_version = self._template_version(_get(deployment, "spec", "template", default={}))

        def rejected(message: str) -> Dict[str, Any]:
            return {
                "action": "rollback_deployment",
                "success": False,
                "status": "rejected",
                "message": message,
                "requested_version": version,
                "previous_version": current_version,
                "current_version": current_version,
            }

        if not isinstance(version, str) or not _VERSION.match(version):
            return rejected(f"Rollback rejected: {version!r} is not a valid version identifier.")

        candidates = [
            replica_set for replica_set in self._owned_replica_sets(deployment)
            if self._template_version(_get(replica_set, "spec", "template", default={})) == version
        ]
        if not candidates:
            known = [record["version"] for record in self.get_deployment_history()]
            return rejected(
                f"Rollback rejected: {version!r} is not a version in this "
                f"deployment's revision history. Known versions: {known}."
            )

        if version == current_version:
            return rejected(f"Rollback rejected: {version!r} is already the running version.")

        self._require_managed(deployment)

        source = max(candidates, key=self._revision)
        template = copy.deepcopy(_get(source, "spec", "template", default={}))
        labels = _get(template, "metadata", "labels", default={})
        labels.pop(POD_TEMPLATE_HASH_LABEL, None)

        self.gateway.replace_pod_template(
            self.settings.namespace,
            self.settings.deployment,
            {key: value for key, value in template.items() if key in ("metadata", "spec")},
        )

        return {
            "action": "rollback_deployment",
            "success": True,
            "status": "success",
            "message": (
                f"Rolled deployment/{self.settings.deployment} back from "
                f"'{current_version}' to '{version}' (revision {self._revision(source)}). "
                "This reports only that the rollback was applied - verify current "
                "status separately."
            ),
            "requested_version": version,
            "previous_version": current_version,
            "current_version": version,
        }

    def scale_service(self, replicas: int) -> Dict[str, Any]:
        bounds = (self.settings.min_replicas, self.settings.max_replicas)

        if (
                not isinstance(replicas, int)
                or isinstance(replicas, bool)
                or not bounds[0] <= replicas <= bounds[1]
        ):
            return {
                "action": "scale_service",
                "success": False,
                "status": "rejected",
                "message": (
                    f"Scaling rejected: {replicas!r} replicas is outside the safe "
                    f"range [{bounds[0]}, {bounds[1]}]."
                ),
                "requested_replicas": replicas,
            }

        deployment = self._deployment()
        self._require_managed(deployment)
        previous = int(_get(deployment, "spec", "replicas", default=1))

        self.gateway.scale_deployment(
            self.settings.namespace,
            self.settings.deployment,
            replicas,
        )

        return {
            "action": "scale_service",
            "success": True,
            "status": "success",
            "message": (
                f"Scaled deployment/{self.settings.deployment} from {previous} to "
                f"{replicas} replica(s). This reports only that the scaling request "
                "was applied - verify current status separately."
            ),
            "requested_replicas": replicas,
            "previous_replicas": previous,
            "current_replicas": replicas,
        }
