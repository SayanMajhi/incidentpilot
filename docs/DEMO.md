# IncidentPilot judge demo

Use simulator mode for the guaranteed, credential-free walkthrough. The whole
story is deterministic and exercises the real controller, safety policy,
infrastructure adapter, and verifier.

## Start

Terminal 1, from the repository root:

```powershell
$env:ENVIRONMENT='simulator'
$env:LLM_ENABLED='false'
.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1
```

Open [http://127.0.0.1:3000/dashboard](http://127.0.0.1:3000/dashboard).

## Three-minute adaptive recovery

1. Click **Reset System**. The service is healthy on v41 with one replica:
   1% error rate, 100 ms latency, and 36% CPU.
2. Click **Run Incident** while healthy. The run must end as `NO INCIDENT`.
   Point out the observation and no-incident events and the absence of safety,
   execution, and verification events.
3. Select **Adaptive Incident**. Before the run, the simulator reports:
   70% error rate, 1000 ms latency, 94% CPU, and one replica.
4. Click **Run Incident**. The start request returns a run ID immediately; the
   backend timeline continues updating while the controller runs.
5. Open attempt 1 and show:

   ```text
   initial evidence: transient service failure
   diagnosis: transient_service_failure
   proposed action: restart_service
   safety: allowed with a recorded rule and reason
   command: succeeded
   fresh verification: failed
   post-restart: 60% errors, 750 ms latency, 91% CPU, one replica
   ```

6. Emphasize that command success was not treated as recovery. Open the
   `replanning` event and the new evidence:

   ```text
   capacity:over_utilized
   logs:resource_pressure
   diagnosis: resource_exhaustion
   ```

7. Open attempt 2 and show:

   ```text
   proposed action: scale_service → 3
   safety: allowed
   command: succeeded
   fresh verification: recovered
   final: 1% errors, 100 ms latency, 48% CPU, three replicas
   run status: RESOLVED
   ```

This is not a hidden scenario script: the first action follows the evidence
available before restart; the second follows new state and failed-attempt
history. Agent/decision code never reads the scenario name.

## Safety rejection

Click **Test Safety Gate**. It deliberately challenges the policy with a scale
target of 20. Show the structured rejection (rule ID, reason, allowed bounds)
and `executed=false`. The service replica count does not change.

The same isolated assessment can be called from PowerShell:

```powershell
$body = @{ action='scale_service'; target=20; namespace='incidentpilot' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/safety/evaluate -ContentType application/json -Body $body | ConvertTo-Json -Depth 20
```

The safety challenge is an explicit policy test, not a naturally diagnosed
incident.

## Other deterministic scenarios

After **Reset System**:

- **Generic Outage**: transient failure evidence selects `restart_service`;
  fresh verification recovers on the first attempt.
- **Bad Deployment**: logs and deployment history correlate v42 with the
  failure; the agent selects `rollback_deployment` to v41 and verifies health.
- **Adaptive Incident**: restart succeeds but verification fails, so fresh
  resource-pressure evidence selects scale to three on attempt 2.

## API-only walkthrough

These commands reset and start the adaptive run:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/reset
Invoke-RestMethod -Method Post http://127.0.0.1:8000/simulate/adaptive-incident
$started = Invoke-RestMethod -Method Post http://127.0.0.1:8000/run-incident
$started | ConvertTo-Json -Depth 10
```

Poll the backend-owned state and event log while the run is active:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/status | ConvertTo-Json -Depth 30
Invoke-RestMethod http://127.0.0.1:8000/timeline | ConvertTo-Json -Depth 30
```

`POST /run-incident` returns HTTP 202; the terminal result is retrieved through
`/status`, not from the start response.

## Retry exhaustion

The controller never performs a fourth automatic remediation. The regression
test drives repeated failed verification and asserts explicit escalation:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_controller.py -k "max_attempt or exhaustion"
```

The final run stores attempt 3, status `escalated`, a reason that the automatic
budget was exhausted, and a timestamped escalation event for human handoff.

## Optional local Kubernetes demo

Only use this path when Docker, kind, and kubectl are available:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-kubernetes.txt
.\scripts\check-k8s-demo.ps1
.\scripts\setup-k8s-demo.ps1
.\scripts\run-k8s-demo.ps1
```

The last script defaults to the real adaptive resource-pressure scenario and
writes `.incidentpilot-kubernetes-run.json`. Watch the Deployment and pods:

```powershell
kubectl -n incidentpilot get deployment,pods -w
```

To use the dashboard, inject only the external scenario, then start the API:

```powershell
.\scripts\run-k8s-demo.ps1 -Scenario adaptive-resource-pressure -ScenarioOnly
$env:ENVIRONMENT='kubernetes'
$env:LLM_ENABLED='false'
.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Simulator controls are disabled in Kubernetes mode. The API cannot inject a
cluster failure, delete resources, or change namespace. Use
`scripts/reset-k8s-demo.ps1` afterward.

## Presenter summary

> IncidentPilot has a goal, persistent run state, real tool interactions, a
> deterministic safety boundary, and an action-observation feedback loop. The
> restart command succeeds but fresh telemetry disproves recovery. The agent
> retains that failure, gathers new evidence, selects a different bounded
> action, and verifies the service again. Unsafe actions never reach the
> infrastructure adapter, and exhausted retries end in human escalation.
