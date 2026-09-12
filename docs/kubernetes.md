# Kubernetes mode

IncidentPilot can run the same `IncidentController` against a **local**
Kubernetes cluster instead of the in-memory simulator. The simulator remains
the default and needs none of this.

```text
IncidentController
        │  (observe / investigate / diagnose / decide / safety / act / verify)
        ▼
Infrastructure interface            backend/infrastructure/base.py
   ┌────┴─────────────────┐
SimulatorInfrastructure   KubernetesInfrastructure        backend/infrastructure/kubernetes/adapter.py
   │                          │
backend/tools + simulator  KubernetesGateway              backend/infrastructure/kubernetes/gateway.py
                              │   (fixed, namespaced, allow-listed operations only)
                              ▼
                       Kubernetes API  ──►  namespace "incidentpilot"
```

The recommended cluster is **kind** (Kubernetes in Docker): one command
creates it, one command deletes it, and it never touches anything else.
Minikube and Docker Desktop's built-in Kubernetes also work.

---

## 1. Create the local cluster

Prerequisites:

- Docker (Docker Desktop on Windows/macOS, or Docker Engine on Linux), running
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)

Windows (PowerShell), after installing and starting Docker Desktop:

```powershell
winget install Kubernetes.kind
winget install Kubernetes.kubectl
```

macOS: `brew install kind kubectl`. Linux: see the links above.

Create the cluster from the repository root:

```bash
kind create cluster --config deploy/kubernetes/kind-cluster.yaml
```

This creates a cluster named `incidentpilot` and switches `kubectl` to the
context `kind-incidentpilot`. Confirm:

```bash
kubectl config current-context
```

> **Minikube / Docker Desktop:** `minikube start` gives the context
> `minikube`; enabling Kubernetes in Docker Desktop gives `docker-desktop`.
> Both are on the default allow-list. Any other context name must be added to
> `K8S_ALLOWED_CONTEXTS` deliberately.

## 2. Create the `incidentpilot` namespace

```bash
kubectl apply -f deploy/kubernetes/namespace.yaml
```

IncidentPilot refuses to operate in any other namespace; this is enforced in
code and cannot be configured away.

## 3. Deploy the demo workload

```bash
kubectl apply -f deploy/kubernetes/demo-workload.yaml
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo
```

This deploys `incidentpilot-demo` (nginx, version label `v41`, one replica)
and a Service with a port named `http`.

Optional - create a second revision so rollback has a target:

```bash
kubectl -n incidentpilot patch deployment incidentpilot-demo --type merge \
  -p '{"spec":{"template":{"metadata":{"labels":{"app.kubernetes.io/version":"v42"}}}}}'
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo
```

### Least-privilege access (optional)

The adapter already confines itself to the namespace and allow-listed
resources. To have the *cluster* enforce the same boundary, apply
`deploy/kubernetes/rbac.yaml` and use its ServiceAccount through a dedicated
context:

```bash
kubectl apply -f deploy/kubernetes/rbac.yaml
TOKEN=$(kubectl -n incidentpilot create token incidentpilot-agent --duration=8h)
kubectl config set-credentials incidentpilot-agent --token="$TOKEN"
kubectl config set-context kind-incidentpilot-agent \
  --cluster=kind-incidentpilot --user=incidentpilot-agent --namespace=incidentpilot
```

Then set `K8S_CONTEXT=kind-incidentpilot-agent` and add it to
`K8S_ALLOWED_CONTEXTS`.

## 4. Select Kubernetes mode

Install the optional client library:

```bash
./.venv/bin/python -m pip install -r requirements-kubernetes.txt
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-kubernetes.txt
```

Check connectivity. This is read-only and modifies nothing:

```bash
ENVIRONMENT=kubernetes ./.venv/bin/python scripts/check_kubernetes_connection.py
```

Start the API in Kubernetes mode:

```bash
ENVIRONMENT=kubernetes ./.venv/bin/python -m uvicorn backend.simulator.service:app --host 127.0.0.1 --port 8000
```

```powershell
$env:ENVIRONMENT='kubernetes'
.\.venv\Scripts\python.exe -m uvicorn backend.simulator.service:app --host 127.0.0.1 --port 8000
```

`GET /config` and `GET /status` now report `"environment": "kubernetes"`, and
`POST /run-incident` runs the controller against the demo Deployment.

In Kubernetes mode the simulator-only endpoints (`/simulate/*`, `/health`,
`/metrics`, `/version`) return **409**, and the dashboard's scenario buttons
therefore report an error: there is no scenario injection against a real
cluster yet.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `simulator` | `simulator` or `kubernetes`. |
| `K8S_NAMESPACE` | `incidentpilot` | Must be `incidentpilot`; anything else is refused. |
| `K8S_DEPLOYMENT` | `incidentpilot-demo` | Target Deployment. Must be in the allow-list. |
| `K8S_ALLOWED_DEPLOYMENTS` | `incidentpilot-demo` | Comma-separated Deployment allow-list. |
| `K8S_SERVICE` | `incidentpilot-demo` | Service probed for error rate and latency. |
| `K8S_ALLOWED_SERVICES` | `incidentpilot-demo` | Comma-separated Service allow-list. |
| `K8S_SERVICE_PORT` | `http` | Service port name (or number) to probe. |
| `K8S_PROBE_PATH` | `/` | HTTP path probed on the Service. |
| `K8S_CONTEXT` | active context | Kubeconfig context to use. Must be allow-listed. |
| `K8S_ALLOWED_CONTEXTS` | `kind-incidentpilot,minikube,docker-desktop` | Contexts IncidentPilot may connect through. |
| `K8S_MIN_REPLICAS` / `K8S_MAX_REPLICAS` | `1` / `5` | May narrow, never widen, the shared SLO bounds. |
| `K8S_PROBE_SAMPLES` | `5` | Probes per metrics reading (1-20). |
| `K8S_PROBE_TIMEOUT_SECONDS` | `2` | Per-probe timeout (up to 10). |
| `K8S_LOG_TAIL_LINES` | `20` | Pod log lines read per pod (1-200). |

## 5. Reset and clean up

Reset the workload to its baseline (v41, one replica):

```bash
kubectl apply -f deploy/kubernetes/demo-workload.yaml
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo
```

`POST /reset` in Kubernetes mode clears IncidentPilot's run history only; the
API never deletes or re-creates cluster resources.

Remove everything IncidentPilot created. These are commands for **you** to
run; IncidentPilot itself has no capability to delete namespaces or clusters:

```bash
kubectl delete namespace incidentpilot
kind delete cluster --name incidentpilot
```

---

## What the adapter observes and does

| Interface method | Kubernetes implementation |
| --- | --- |
| `get_metrics` | `K8S_PROBE_SAMPLES` HTTP GETs to the Service through the API server proxy. Error rate = failed / total, latency = median, combined with Deployment readiness. |
| `check_health` | Derived from `get_metrics`. |
| `get_current_version` | Pod template label `app.kubernetes.io/version` (falls back to image tag). |
| `get_capacity` | Desired and ready replicas. Utilization is reported as **unavailable**; there is no metrics pipeline yet. |
| `query_logs` | Failed Deployment conditions, container waiting/terminated states (CrashLoopBackOff, ImagePullBackOff, OOMKilled, ...), Warning events for the Deployment, its ReplicaSets and pods, and recent pod log lines. |
| `get_deployment_history` | One entry per version from the Deployment's own ReplicaSets, ordered by revision. |
| `restart_service` | Sets `kubectl.kubernetes.io/restartedAt` on the pod template (`kubectl rollout restart`). |
| `rollback_deployment` | Restores the pod template of the ReplicaSet that ran the requested version. |
| `scale_service` | Patches the Deployment's `scale` subresource. |

## Safety restrictions

Enforced in code, in two independent layers (adapter and gateway), before any
API request is made:

- **Namespace:** only `incidentpilot`. Every gateway call re-checks it.
- **Resources:** one Deployment and one Service, each from an explicit
  allow-list and validated as an RFC 1123 name. Pods and ReplicaSets are only
  listed with the Deployment's own equality selector; ReplicaSets owned by
  anything else are ignored.
- **Opt-in label:** a Deployment without `incidentpilot.io/managed=true` can
  be observed but is never modified.
- **Fixed operations:** the gateway has no generic request, `kubectl`, exec,
  apply, delete or create method. The only writes are "patch this
  Deployment's pod template" and "set this Deployment's replica count".
  Template patches may only contain `metadata` and `spec`.
- **Replica bounds:** `1..5` by default, shared with the safety policy.
  Configuration may narrow but never widen them; the adapter and the gateway
  both check.
- **Rollback targets:** must be a well-formed version that exists in the
  Deployment's own revision history and is not already running.
- **Clusters:** connects only through allow-listed kubeconfig contexts, which
  are local development clusters by default. In-cluster configuration is not
  supported.
- The existing deterministic safety policy still approves every action before
  the adapter sees it.

## Tests

`pytest` needs neither a cluster nor the `kubernetes` package. The adapter
tests run the real gateway and adapter against an in-memory fake of the
Kubernetes API (`tests/k8s_fakes.py`).

Live tests are opt-in:

```bash
RUN_K8S_INTEGRATION=1 ./.venv/bin/python -m pytest -m kubernetes              # read-only
RUN_K8S_INTEGRATION=1 RUN_K8S_MUTATING=1 ./.venv/bin/python -m pytest -m kubernetes
```

The mutating test scales the demo Deployment and restores its replica count.

## Current limitations

- No Prometheus or metrics-server integration yet, so CPU/memory utilization
  is unavailable and scaling uses the decision engine's default step.
- Probe latency includes the hop through the Kubernetes API server.
- Rollback uses a strategic-merge patch of the pod template. Fields that exist
  only in the newer template are not removed, which suits the demo workload
  but is not a full `kubectl rollout undo`.
- No failure-injection scenarios exist for Kubernetes yet.
