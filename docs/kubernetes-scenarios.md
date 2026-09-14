# Real Kubernetes failure scenarios

These scenarios exercise the existing IncidentPilot controller against a
local kind cluster using one managed Deployment, `incidentpilot-demo`.  They
are deliberately deterministic: the workload is a tiny local Python HTTP
server, not a third-party test image, and it emits the evidence the agent
needs through real pod logs and HTTP responses.

## Recommended automated run

From the repository root in PowerShell:

```powershell
.\scripts\check-k8s-demo.ps1
.\scripts\setup-k8s-demo.ps1
.\scripts\run-k8s-demo.ps1
```

The final command defaults to `adaptive-resource-pressure`, runs the real
controller, and writes `.incidentpilot-kubernetes-run.json`. Use
`-Scenario restart` or `-Scenario bad-deployment` for the other stories. Add
`-ScenarioOnly` when the backend/dashboard is already running and you want to
click **Run Incident** there.

## Build the workload image manually

From the repository root, with Docker Desktop and the `incidentpilot` kind
cluster running:

```powershell
.\scripts\run_kubernetes_scenario.ps1 -Scenario restart -BuildImage
```

The script builds `incidentpilot-scenarios:local`, loads it into kind, applies
the v41 baseline, and then applies the requested scenario. Later runs do not
need `-BuildImage` unless `scenario_server.py` or the Dockerfile changed.

Start IncidentPilot in a separate PowerShell window:

```powershell
$env:ENVIRONMENT = 'kubernetes'
$env:LLM_ENABLED = 'false'
.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Run a scenario, then start the controller. The POST returns HTTP 202 with the
run ID; retrieve the live/final result through `/status` and `/timeline`:

```powershell
.\scripts\run_kubernetes_scenario.ps1 -Scenario restart
Invoke-RestMethod -Method Post http://127.0.0.1:8000/run-incident | ConvertTo-Json -Depth 20
Invoke-RestMethod http://127.0.0.1:8000/status | ConvertTo-Json -Depth 30
Invoke-RestMethod http://127.0.0.1:8000/timeline | ConvertTo-Json -Depth 30
```

For a terminal-only run that writes a compact audit file, use:

```powershell
$env:ENVIRONMENT = 'kubernetes'
$env:LLM_ENABLED = 'false'
.\.venv\Scripts\python.exe scripts\run_kubernetes_agent.py
```

The script writes `.incidentpilot-kubernetes-run.json` at the repository root.

Watch the real workload while it runs:

```powershell
kubectl -n incidentpilot get deployment,pods -w
```

## Scenarios

| Scenario | Initial evidence | Expected attempts | Real mutation | Recovery condition |
| --- | --- | --- | --- | --- |
| `restart` | HTTP 503 timeout and transient-worker log | `restart_service` | Pod-template restart annotation, then a new Pod | The restarted Pod sees the annotation and serves HTTP 200. |
| `bad-deployment` | v42 application-failure log and HTTP 503 | `rollback_deployment` to v41 | The Deployment template is restored from the v41 ReplicaSet | The v41 workload serves HTTP 200. |
| `adaptive-resource-pressure` | First: transient timeout. After restart: connection-pool/resource-pressure logs. | `restart_service`, then `scale_service` to 3 | Restart replaces the first Pod; scale creates two more | The workload discovers three peers through its headless Service and serves HTTP 200. |

The app's `/ready` endpoint is independent of its workload endpoint. This is
intentional: Kubernetes can mark the pod ready and route real HTTP probes
while IncidentPilot observes the application-level 503 response.

## Why verification waits for Kubernetes

A Deployment patch returns when the API accepts it, not when replacement Pods
are ready. `KubernetesInfrastructure.wait_for_reconciliation()` now performs
a bounded wait after restart, rollback, and scale before the controller takes
its fresh verification samples. Its default deadline is 90 seconds and can be
set with `K8S_ROLLOUT_TIMEOUT_SECONDS` (1-180).

The reconciliation result is retained inside an action result, for example:

```json
{
  "action": "scale_service",
  "success": true,
  "reconciliation": {
    "waited": true,
    "converged": true,
    "ready_replicas": 3,
    "desired_replicas": 3
  }
}
```

## Reset

The repeatable reset is:

```powershell
.\scripts\reset-k8s-demo.ps1
```

Manual alternatives follow.

Return to the original nginx demo workload:

```powershell
kubectl apply -f deploy/kubernetes/demo-workload.yaml
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo
kubectl -n incidentpilot delete service incidentpilot-demo-peers --ignore-not-found
```

Or keep the scenario workload and return to its healthy v41 baseline:

```powershell
kubectl apply -f deploy/kubernetes/scenarios/base.yaml
kubectl -n incidentpilot rollout status deployment/incidentpilot-demo
```
