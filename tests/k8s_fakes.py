"""In-memory stand-in for the Kubernetes API, for adapter tests.

``FakeCluster`` implements the handful of ``CoreV1Api`` / ``AppsV1Api``
methods ``KubernetesGateway`` calls, returning JSON-shaped dicts (what the
real gateway produces via ``sanitize_for_serialization``). It records every
call so tests can assert exactly which namespace and resources were touched.

It models just enough of a Deployment to be useful: pod-template changes roll
out a new revision (reusing an identical earlier ReplicaSet, as Kubernetes
does), versions listed in ``bad_versions`` never become ready and fail
probes, and scaling changes the replica count.
"""

import copy

from backend.infrastructure.kubernetes.config import (
    ALLOWED_NAMESPACE,
    MANAGED_LABEL_KEY,
    VERSION_LABEL,
    KubernetesSettings,
)
from backend.infrastructure.kubernetes.gateway import KubernetesGateway
from backend.infrastructure.kubernetes.adapter import (
    POD_TEMPLATE_HASH_LABEL,
    REVISION_ANNOTATION,
    KubernetesInfrastructure,
)

NAME = "incidentpilot-demo"
SELECTOR = {"app.kubernetes.io/name": NAME}


class FakeApiException(Exception):
    def __init__(self, status, reason=""):
        super().__init__(f"({status}) {reason}")
        self.status = status
        self.reason = reason


def pod_template(version, image="nginx:1.27-alpine"):
    return {
        "metadata": {
            "labels": {**SELECTOR, VERSION_LABEL: version},
            "annotations": {},
        },
        "spec": {"containers": [{"name": "app", "image": image}]},
    }


def _merge(base, patch):
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _comparable(template):
    template = copy.deepcopy(template)
    template["metadata"]["labels"].pop(POD_TEMPLATE_HASH_LABEL, None)
    return template


class FakeCluster:
    def __init__(self, versions=("v41",), bad_versions=(), managed=True, replicas=1):
        self.calls = []
        self.bad_versions = set(bad_versions)
        self.managed = managed
        self.replicas = replicas
        self.uid = "uid-incidentpilot-demo"
        self.revision = 0
        self.replica_sets = []
        self.template = None
        self.events = []
        self.returned_namespace = ALLOWED_NAMESPACE

        for version in versions:
            self._roll_out(pod_template(version))

        # A ReplicaSet matching the selector but owned by something else.
        self.replica_sets.append({
            "metadata": {
                "name": "unrelated-rs",
                "namespace": ALLOWED_NAMESPACE,
                "annotations": {REVISION_ANNOTATION: "99"},
                "ownerReferences": [{"kind": "Deployment", "name": "other", "uid": "uid-other"}],
            },
            "spec": {"template": pod_template("v1")},
            "status": {"readyReplicas": 0},
        })

    # -- model ----------------------------------------------------------------

    @property
    def version(self):
        return self.template["metadata"]["labels"][VERSION_LABEL]

    @property
    def healthy(self):
        return self.version not in self.bad_versions

    def _owned(self):
        return [rs for rs in self.replica_sets if rs["metadata"]["name"] != "unrelated-rs"]

    def _current_rs(self):
        return max(self._owned(), key=lambda rs: int(rs["metadata"]["annotations"][REVISION_ANNOTATION]))

    def _roll_out(self, template):
        self.revision += 1
        existing = next(
            (rs for rs in self._owned() if _comparable(rs["spec"]["template"]) == _comparable(template)),
            None,
        )
        if existing is not None:
            existing["metadata"]["annotations"][REVISION_ANNOTATION] = str(self.revision)
        else:
            index = len(self._owned()) + 1
            stored = copy.deepcopy(template)
            stored["metadata"]["labels"][POD_TEMPLATE_HASH_LABEL] = f"hash{index}"
            self.replica_sets.append({
                "metadata": {
                    "name": f"{NAME}-rs{index}",
                    "namespace": ALLOWED_NAMESPACE,
                    "creationTimestamp": f"2026-09-13T10:0{index}:00Z",
                    "annotations": {REVISION_ANNOTATION: str(self.revision)},
                    "ownerReferences": [{"kind": "Deployment", "name": NAME, "uid": self.uid}],
                },
                "spec": {"template": stored},
                "status": {"readyReplicas": 0},
            })
        self.template = copy.deepcopy(template)
        self.template["metadata"]["labels"].pop(POD_TEMPLATE_HASH_LABEL, None)
        for rs in self._owned():
            rs["status"]["readyReplicas"] = 0
        if self.healthy:
            self._current_rs()["status"]["readyReplicas"] = self.replicas

    def _deployment(self):
        labels = {**SELECTOR}
        if self.managed:
            labels[MANAGED_LABEL_KEY] = "true"
        conditions = []
        if not self.healthy:
            conditions = [
                {"type": "Available", "status": "False", "reason": "MinimumReplicasUnavailable",
                 "lastUpdateTime": "2026-09-13T10:10:00Z"},
                {"type": "Progressing", "status": "False", "reason": "ProgressDeadlineExceeded",
                 "lastUpdateTime": "2026-09-13T10:10:00Z"},
            ]
        return {
            "metadata": {
                "name": NAME,
                "namespace": self.returned_namespace,
                "uid": self.uid,
                "labels": labels,
                "annotations": {REVISION_ANNOTATION: str(self.revision)},
            },
            "spec": {
                "replicas": self.replicas,
                "selector": {"matchLabels": dict(SELECTOR)},
                "template": copy.deepcopy(self.template),
            },
            "status": {
                "readyReplicas": self.replicas if self.healthy else 0,
                "conditions": conditions,
            },
        }

    def _pods(self):
        rs = self._current_rs()
        pods = []
        for index in range(self.replicas):
            if self.healthy:
                container = {"name": "app", "ready": True, "restartCount": 0, "state": {"running": {}}}
            else:
                container = {
                    "name": "app", "ready": False, "restartCount": 0,
                    "state": {"waiting": {"reason": "ImagePullBackOff", "message": "Back-off pulling image"}},
                }
            pods.append({
                "metadata": {
                    "name": f"{rs['metadata']['name']}-p{index}",
                    "namespace": ALLOWED_NAMESPACE,
                    "labels": dict(rs["spec"]["template"]["metadata"]["labels"]),
                    "ownerReferences": [{"kind": "ReplicaSet", "name": rs["metadata"]["name"]}],
                },
                "spec": {"containers": [{"name": "app"}]},
                "status": {"containerStatuses": [container]},
            })
        return pods

    # -- CoreV1Api ------------------------------------------------------------

    def read_namespace(self, name):
        self.calls.append(("read_namespace", name, None))
        return {"metadata": {"name": name}}

    def list_namespaced_pod(self, namespace, label_selector=None):
        self.calls.append(("list_namespaced_pod", namespace, label_selector))
        return {"items": self._pods()}

    def list_namespaced_event(self, namespace):
        self.calls.append(("list_namespaced_event", namespace, None))
        return {"items": copy.deepcopy(self.events)}

    def read_namespaced_pod_log(self, name, namespace, container=None, tail_lines=None, timestamps=False):
        self.calls.append(("read_namespaced_pod_log", namespace, name))
        if not self.healthy:
            raise FakeApiException(400, "container is waiting to start")
        return "2026-09-13T10:00:00Z GET / HTTP/1.1 200\n"

    def connect_get_namespaced_service_proxy(self, name, namespace, _request_timeout=None):
        self.calls.append(("connect_get_namespaced_service_proxy", namespace, name))
        if not self.healthy:
            raise FakeApiException(503, "no endpoints available for service")
        return "ok"

    # -- AppsV1Api ------------------------------------------------------------

    def read_namespaced_deployment(self, name, namespace):
        self.calls.append(("read_namespaced_deployment", namespace, name))
        return self._deployment()

    def list_namespaced_replica_set(self, namespace, label_selector=None):
        self.calls.append(("list_namespaced_replica_set", namespace, label_selector))
        return {"items": copy.deepcopy(self.replica_sets)}

    def patch_namespaced_deployment(self, name, namespace, body):
        self.calls.append(("patch_namespaced_deployment", namespace, name, copy.deepcopy(body)))
        self._roll_out(_merge(self.template, body["spec"]["template"]))
        return self._deployment()

    def patch_namespaced_deployment_scale(self, name, namespace, body):
        self.calls.append(("patch_namespaced_deployment_scale", namespace, name, copy.deepcopy(body)))
        self.replicas = body["spec"]["replicas"]
        if self.healthy:
            self._current_rs()["status"]["readyReplicas"] = self.replicas
        return {"spec": {"replicas": self.replicas}}

    # -- helpers --------------------------------------------------------------

    def mutating_calls(self):
        return [call for call in self.calls if call[0].startswith("patch_")]


def make_adapter(cluster=None, settings=None):
    cluster = cluster if cluster is not None else FakeCluster()
    settings = settings if settings is not None else KubernetesSettings(probe_samples=3)
    gateway = KubernetesGateway(
        settings,
        core_api=cluster,
        apps_api=cluster,
        api_exception=FakeApiException,
    )
    gateway.context = "kind-incidentpilot"
    return KubernetesInfrastructure(settings=settings, gateway=gateway), cluster
