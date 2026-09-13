# IncidentPilot Demo Runbook

This is the presentation path for the repository as it exists. Use the
simulator for the guaranteed three-minute demo. Use Kubernetes as the real
infrastructure extension when Docker Desktop and a local cluster are ready.

## 1. What IncidentPilot is

IncidentPilot is a bounded autonomous incident-response agent. Its explicit
goal is to restore a service to configured SLOs while respecting safety
constraints.

It observes the environment, investigates evidence, diagnoses a cause,
selects one bounded action, passes that action through a deterministic safety
gate, executes it, and independently verifies the resulting service state.
Command success is not treated as incident recovery.

## 2. Why it qualifies as agentic AI

| Capability | IncidentPilot behavior |
| --- | --- |
| Goal-driven execution | Every run exposes `run_id`, `goal`, `started_at`, status, phase and attempt. |
| Environment interaction | Infrastructure adapters read telemetry, health, logs, deployment history and capacity. |
| Persistent task state | Process-local run state and attempt history are available through `/status` and `/timeline`. |
| Action → observation | Every remediation is followed by fresh telemetry samples. |
| Replanning | Failed verification causes a new investigation; new evidence selects the next action. |
| Objective verification | Error rate must be at most 5%, latency at most 200 ms, and health must pass. |
| Failure recovery | The adaptive scenario rejects a successful restart, then recovers by scaling. |
| Safe termination | Unsafe actions are blocked; exhausted attempts become an explicit human escalation. |

## 3. Architecture

```text
React dashboard
      ↓
FastAPI status, timeline and demo API
      ↓
IncidentController
      ↓
Observe → Investigate → Diagnose → Decide → Safety → Execute → Verify
      ↑                                                        ↓
      └──────────── fresh evidence ← Adapt ──────────── failed SLO
                                                               ↓
                                      Recover / Block / Escalate

Infrastructure implementations:
  SimulatorInfrastructure
  KubernetesInfrastructure → restricted KubernetesGateway

Optional Qwen proposal → deterministic arbitration → safety gate
```

## 4. Prerequisites

For the simulator:

- Python 3.11 or 3.12
- Node.js 20 or newer (Node 22 is used by Docker Compose)

For the real Kubernetes demo, also install and start:

- Docker Desktop
- `kubectl`
- `kind`

Install the project once from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location frontend
npm ci
Set-Location ..
```

## 5. Fastest demo setup

Terminal 1, from the repository root:

```powershell
$env:ENVIRONMENT='simulator'
$env:LLM_ENABLED='false'
.\.venv\Scripts\python.exe -m uvicorn backend.simulator.service:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1
```

Open [http://127.0.0.1:3000/dashboard](http://127.0.0.1:3000/dashboard).
The API documentation is at
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## 6. Main three-minute demo

1. Click **Reset System**. Expect a healthy v41 service with one replica and
   no run ID.
2. Select **Adaptive Incident**. Expect a down service, 60% errors, 750 ms
   latency, 94% CPU and one replica.
3. Click **Run Incident**. Point out the new `inc-…` Run ID and explicit goal.
4. Open Attempt 1. The expected trace is:

   ```text
   evidence: transient service failure
   diagnosis: transient_service_failure
   action: restart_service
   command success: true
   verification: failed
   after restart: 60% errors, 750 ms latency, 91% CPU, one replica
   ```

5. Explain that the restart command succeeded but recovery was rejected by
   fresh SLO telemetry.
6. Open Attempt 2. The expected trace is:

   ```text
   new evidence: capacity:over_utilized, logs:resource_pressure
   diagnosis: resource_exhaustion
   action: scale_service → 3
   command success: true
   verification: passed
   after scale: 1% errors, 100 ms latency, 48% CPU, three replicas
   final status: RESOLVED
   ```

Select Attempt 1 and Attempt 2 in turn. Every Inspector tab now follows the
selected attempt: evidence, diagnosis, decision, safety, logs and verification
metrics do not get mixed with the final global state.

The same flow can be triggered without the UI:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/reset
Invoke-RestMethod -Method Post http://127.0.0.1:8000/simulate/adaptive-incident
Invoke-RestMethod -Method Post http://127.0.0.1:8000/run-incident | ConvertTo-Json -Depth 30
```

## 7. What to say to judges

> IncidentPilot is not a one-shot LLM. Every incident has an explicit recovery
> goal, unique run state and bounded history. The agent observes the
> environment, gathers evidence, chooses a restricted action, and then
> independently verifies the actual service SLO. Here the restart command
> succeeds, but the service remains unhealthy, so IncidentPilot rejects false
> success. It gathers new evidence, identifies persistent resource pressure,
> scales to three replicas and verifies recovery again. Qwen can advise the
> decision, while deterministic validation and safety always control execution.

## 8. Safety demo

The policy maximum is three replicas. This command proposes 20 and prints a
blocked result without changing the simulator:

```powershell
.\.venv\Scripts\python.exe -c "from backend.agent.controller import controller; print(controller.execute({'action':'scale_service','target':20,'reason':'safety demo','confidence':1.0}))"
```

Expected fields:

```text
success: false
status: blocked
policy_allowed: false
```

## 9. Escalation demo

IncidentPilot never adds a fourth automatic remediation. This focused test
drives three actions whose verification continues to fail:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_controller.py -k stops_after_max_attempts
```

The resulting controller contract is covered directly:

```json
{
  "status": "escalated",
  "reason": "Maximum remediation attempts exhausted",
  "attempt": 3
}
```

Its `trace_events` contains an `escalated` event stating that maximum automatic
remediation attempts were reached and human investigation is required.

## 10. Real Kubernetes demo

Install Kubernetes dependencies once:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-kubernetes.txt
```

Then run:

```powershell
.\scripts\check-k8s-demo.ps1
.\scripts\setup-k8s-demo.ps1
.\scripts\run-k8s-demo.ps1
```

`run-k8s-demo.ps1` defaults to the adaptive resource-pressure story. It
applies the real failure, runs the controller with `ENVIRONMENT=kubernetes`,
and saves `.incidentpilot-kubernetes-run.json`. Watch changes in another
terminal:

```powershell
kubectl -n incidentpilot get deployment,pods -w
```

Expected real mutations are a pod-template restart, failed application-level
verification, then Deployment scale from one to three replicas and passing
verification. To use the dashboard instead of the terminal runner:

```powershell
.\scripts\run-k8s-demo.ps1 -Scenario adaptive-resource-pressure -ScenarioOnly
$env:ENVIRONMENT='kubernetes'
$env:LLM_ENABLED='false'
.\.venv\Scripts\python.exe -m uvicorn backend.simulator.service:app --host 127.0.0.1 --port 8000
```

The simulator remains fully functional when Kubernetes is unavailable.

## 11. Optional Qwen-assisted mode

Deterministic mode is the recommended judging path. To show optional Qwen
proposals through Hugging Face, set the existing provider configuration:

```powershell
$env:LLM_ENABLED='true'
$env:HF_TOKEN='hf_your_token'
$env:HF_MODEL='your-qwen-model-id'
.\.venv\Scripts\python.exe scripts\check_qwen_connection.py
```

Restart the backend after changing the environment. The Decision Inspector
separates the AI suggestion and confidence from deterministic validation. A
matching suggestion is shown as **ACCEPTED**; a conflicting suggestion is
shown as **REJECTED** with the arbitration reason. Qwen never executes tools.

## 12. Reset the demo

Simulator:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/reset
```

Kubernetes:

```powershell
.\scripts\reset-k8s-demo.ps1
```

Both reset paths return to healthy v41 and one replica. The Kubernetes API
`POST /reset` clears only IncidentPilot run history; the script resets real
cluster resources.

## 13. Expected output summary

```text
Run inc-...
Goal: Restore the service to configured SLOs while respecting safety constraints.

Attempt 1
restart_service
command success = true
verification recovered = false

Fresh evidence
capacity:over_utilized
logs:resource_pressure

Attempt 2
scale_service → 3
command success = true
verification recovered = true

Final status: RESOLVED
```

## 14. Troubleshooting

- Port 8000 busy: `Get-NetTCPConnection -LocalPort 8000` and stop the process
  you intentionally started, or choose another backend port and update the
  dashboard API Target.
- Frontend cannot reach API: confirm
  [http://127.0.0.1:8000/status](http://127.0.0.1:8000/status) opens and the
  frontend API Target is `http://127.0.0.1:8000`.
- Docker unavailable: start Docker Desktop, then rerun
  `scripts/check-k8s-demo.ps1`.
- `kind` or `kubectl` missing: run `winget install Kubernetes.kind` and
  `winget install Kubernetes.kubectl`, then open a new terminal.
- Wrong context: `kubectl config use-context kind-incidentpilot`.
- Existing kind cluster unreachable: start Docker Desktop. If the container
  no longer exists, inspect `kind get clusters` before recreating it.
- Qwen missing credentials: leave `LLM_ENABLED=false`; deterministic mode is
  complete and is the recommended demo.
