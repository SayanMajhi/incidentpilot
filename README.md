# IncidentPilot

IncidentPilot is a local, autonomous SRE incident-response prototype. It watches a deterministic production-service simulator, detects SLO violations, gathers real simulator evidence, diagnoses a likely cause, selects a bounded remediation, applies a deterministic safety policy, executes the action, and verifies recovery from fresh telemetry. If an action completes but the service remains unhealthy, the controller re-investigates and adapts instead of reporting a false recovery.

The project is deliberately self-contained: **there is no database, queue, cache, or external infrastructure requirement**. Service, incident, replica, and execution state live in memory and reset when the backend process exits.

## Architecture

```text
React dashboard
  GET /config    -> SLO thresholds and action bounds (read once)
  GET /status    -> live service telemetry + live agent phase (polled)
  GET /timeline  -> render-ready execution history      (polled)
  POST /simulate/*, /run-incident, /reset
             |
             v
FastAPI simulator/API (backend/simulator/service.py)
             |
             v
IncidentController
  Observe/Detect -> Investigate -> Diagnose -> Decide
                                         |
                deterministic policy gate
                                         |
            Infrastructure interface (backend/infrastructure)
                 /                                  \
      SimulatorInfrastructure              KubernetesInfrastructure
      tools -> simulator state             namespace "incidentpilot" only
                                         |
                         fresh telemetry verification
                                         |
                    recovered OR adapt/re-investigate
```

### Execution environments

`ENVIRONMENT` selects what the controller operates against:

- `simulator` (default): the deterministic in-memory service. Needs nothing else.
- `kubernetes`: a demo Deployment on a **local** cluster (kind, minikube or
  Docker Desktop), confined to the `incidentpilot` namespace, allow-listed
  resources, bounded replicas and allow-listed kubeconfig contexts.

The controller has no environment-specific code; both adapters implement the
same interface. Setup, configuration and safety restrictions for Kubernetes
mode are in [docs/kubernetes.md](docs/kubernetes.md).

Repository layout:

```text
backend/
  agent/         controller, deterministic decision engine, optional HF/Qwen proposal engine
  infrastructure/ environment interface, simulator adapter, Kubernetes adapter + gateway
  safety/        allow-list policy and action bounds
  shared/        SLO thresholds and action bounds shared by every layer
  simulator/     FastAPI app and deterministic in-memory service environment
  tools/         diagnostic reads and remediation mutations
  verification/  independent telemetry-based recovery verification
deploy/kubernetes/ kind cluster, namespace, demo workload and optional RBAC manifests
docs/            Kubernetes mode setup and safety
frontend/        React 19 + TypeScript + Vite dashboard and landing experience
tests/           unit, integration and controller-loop coverage
scripts/         optional model connectivity check
```

### One source of truth for thresholds

`backend/shared/slo.py` owns every SLO threshold and action bound, and two families are kept deliberately distinct:

| Family | Values | Meaning |
| --- | --- | --- |
| `RECOVERY_*` | error rate ≤ 5%, latency ≤ 200ms | The SLO. Recovery is verified against these; this is the authoritative definition of "recovered". |
| `ELEVATED_*` | error rate > 10%, latency > 300ms | The evidence bar used during diagnosis. Looser than the SLO on purpose, so real incidents clear it and healthy noise does not. |

The verifier, the decision engine, the safety policy and the remediation tools all read from that module, and the dashboard fetches the same numbers from `GET /config` instead of hardcoding them. Changing a value there changes the backend, the safety gate and the UI together.

## Agent workflow

Each bounded run executes up to three attempts:

1. **Observe and detect** — read health, error rate, latency, and version; identify actual SLO breaches.
2. **Investigate** — query simulator logs and deployment history through diagnostic tools.
3. **Diagnose and decide** — choose restart, rollback, scale, or escalation from supplied evidence.
4. **Safety check** — the deterministic policy gate validates the proposed action and target before any state mutation. Its verdict, not the action's outcome, is what the dashboard reports as allowed or blocked.
5. **Remediate** — invoke the simulator-backed remediation tool.
6. **Verify** — collect fresh metrics; action success never implies recovery.
7. **Adapt or recover** — retain failed-attempt evidence, re-observe, and choose a different action when supported.

The optional Hugging Face/Qwen engine may propose a decision. It never executes tools directly. A deterministic evidence layer arbitrates conflicts, and the deterministic policy gate remains authoritative. With no model credentials, IncidentPilot runs fully in deterministic mode.

## Tech stack

- Python 3.11+ (tested with 3.11 and 3.12)
- FastAPI, Uvicorn, Pydantic
- Optional `huggingface_hub` decision proposal
- React 19, TypeScript, Vite 6, React Router
- Pytest and FastAPI TestClient

## Local setup

From the repository root.

**Windows (PowerShell)**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location frontend; npm ci; Set-Location ..
```

**macOS / Linux**

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
(cd frontend && npm ci)
```

## Running locally

Two processes. Deterministic mode is the fastest and fully functional demo mode.

**Terminal 1 — API**

```powershell
# PowerShell
$env:LLM_ENABLED='false'
.\.venv\Scripts\python.exe -m uvicorn backend.simulator.service:app --host 127.0.0.1 --port 8000
```

```bash
# bash
LLM_ENABLED=false ./.venv/bin/python -m uvicorn backend.simulator.service:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — dashboard**

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The dashboard is at [http://127.0.0.1:3000/dashboard](http://127.0.0.1:3000/dashboard), and FastAPI's interactive docs at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

The uvicorn target is `backend.simulator.service:app` and must be run from the repository root, since `backend` is the importable package.

### Docker Compose

Runs the same two local services, still with no persistence:

```bash
docker compose up --build
```

## Environment variables

Copy `.env.example` to `.env` only if you want file-based configuration; every value has a working default.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `simulator` | `simulator` or `kubernetes` (see [docs/kubernetes.md](docs/kubernetes.md)). |
| `LLM_ENABLED` | `false` | Enable optional HF/Qwen proposals. Deterministic fallback remains available. |
| `HF_TOKEN` | unset | Hugging Face access token, used only when LLM mode is enabled. |
| `HF_MODEL` | unset | Hugging Face model identifier, used only when LLM mode is enabled. |
| `CORS_ORIGINS` | localhost and 127.0.0.1 on port 3000 | Comma-separated browser origins allowed by FastAPI. |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Frontend API target. Set in `frontend/.env.local`, or override live in the dashboard's API Target field. |

Neither `.env` nor `frontend/.env.local` is committed; both are ignored by Git.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health`, `/metrics`, `/version` | Read simulator health and telemetry. |
| GET | `/config` | SLO thresholds, diagnosis evidence bar, and replica bounds the backend enforces. |
| GET | `/status` | Unified live service, scenario, replicas, diagnostics, live agent phase, and latest run. |
| GET | `/timeline` | Render-ready per-attempt execution history plus the live agent phase. |
| POST | `/simulate/outage` | Inject a transient outage. |
| POST | `/simulate/bad-deployment` | Deploy v42 and inject a deployment regression. |
| POST | `/simulate/adaptive-incident` | Inject a failure where restart completes but verification fails, revealing resource pressure. |
| POST | `/simulate/recover` | Manually restore the healthy baseline and clear the active scenario. |
| POST | `/simulate/rollback?version=v41` | Manually change the deployed version. Heals the service only if that version was the tracked cause. |
| POST | `/run-incident` | Execute the bounded autonomous controller loop. Duplicate concurrent runs return HTTP 409. |
| POST | `/reset` | Restore health, v41, one replica, scenario flags, and agent history. |

The dashboard polls `/status` and `/timeline` every two seconds and uses the mutation endpoints directly. Because agent progress is read from the backend rather than tracked client-side, the timeline stays correct across a page reload mid-run and when a run was started by another client. Controls are disabled while disconnected or while an action is in flight, the last real telemetry is preserved and marked stale on connection loss, and there is no client-side substitute workflow.

## Demo walkthrough

1. Start both processes and confirm the header says **Connected** with healthy v41 telemetry.
2. Choose **Generic Outage**, then **Run Incident**. The agent detects the SLO breach, restarts, and verifies recovery.
3. Reset, choose **Bad Deployment**, and run. Logs correlate v42 with the incident; the policy approves rollback to v41 and telemetry verifies recovery.
4. Reset, choose **Adaptive Incident**, and run. Attempt 1 restarts successfully but verification rejects recovery. Attempt 2 sees new resource-exhaustion evidence, scales to three replicas, and verifies recovery.
5. Reset and repeat. All state and timeline cards return to the healthy baseline.

## Testing

```bash
./.venv/bin/python -m pytest -q      # no cluster needed; live Kubernetes tests are skipped
(cd frontend && npm run build)       # tsc --build + vite build
```

Tests cover simulator endpoints, diagnostics, policy boundaries and their agreement with the executor's bounds, remediation effects, verification, decision parsing and fallback, bounded retries, blocked actions, false-success rejection, the adaptive restart-to-scale recovery, and the dashboard-facing `/config`, `/status` and `/timeline` contracts.

Optionally, `scripts/check_qwen_connection.py` verifies Hugging Face connectivity when LLM mode is configured. It is a manual script, not part of the test suite.

## Supported failures and limitations

- Generic transient outages recover through restart.
- Bad deployments recover through a version rollback selected from deployment history. A restart cannot fix one: while the bad version is still deployed, the cause survives the restart and the service stays unhealthy.
- The adaptive scenario intentionally fails verification after restart and recovers by scaling after fresh evidence appears.
- Unknown or insufficient evidence escalates rather than inventing a remediation.
- Unsafe or unsupported actions are blocked before remediation. The policy gate and the remediation executor share one set of bounds, so the gate can never approve an action the executor would reject.
- The environment is deterministic and single-process. It is a safe simulator, not a connector to Kubernetes or a production control plane.
- State is process-local and is not durable across backend restarts. There is explicitly **no database**.
- Optional hosted-model latency and availability depend on the configured Hugging Face service; deterministic mode is recommended for repeatable local demos.
