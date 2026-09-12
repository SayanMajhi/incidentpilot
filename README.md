# IncidentPilot

IncidentPilot is a local, autonomous SRE incident-response prototype. It watches a deterministic production-service simulator, detects SLO violations, gathers real simulator evidence, diagnoses a likely cause, selects a bounded remediation, applies a deterministic safety policy, executes the action, and verifies recovery from fresh telemetry. If an action completes but the service remains unhealthy, the controller re-investigates and adapts instead of reporting a false recovery.

The project is deliberately self-contained: **there is no database, queue, cache, or external infrastructure requirement**. Service, incident, replica, and execution state live in memory and reset when the backend process exits.

## Architecture

```text
React dashboard (polls /status)
             |
             v
FastAPI simulator/API (simulator/service.py)
             |
             v
IncidentController
  Observe/Detect -> Investigate -> Diagnose -> Decide
                                         |
                deterministic policy gate
                                         |
                    remediation tools -> simulator state
                                         |
                         fresh telemetry verification
                                         |
                    recovered OR adapt/re-investigate
```

Repository layout:

```text
agent/         controller, deterministic decision engine, optional HF/Qwen proposal engine
frontend/      React 19 + TypeScript + Vite dashboard and landing experience
safety/        allow-list policy and action bounds
simulator/     FastAPI app and deterministic in-memory service environment
tools/         diagnostic reads and remediation mutations
verification/ independent telemetry-based recovery verification
tests/         unit, integration, controller-loop, and evaluation scenarios
scripts/       optional model connectivity check
```

## Agent workflow

Each bounded run executes up to three attempts:

1. **Observe and detect** — read health, error rate, latency, and version; identify actual SLO breaches.
2. **Investigate** — query simulator logs and deployment history through diagnostic tools.
3. **Diagnose and decide** — choose restart, rollback, scale, or escalation from supplied evidence.
4. **Safety check** — validate the proposed action and target before any state mutation.
5. **Remediate** — invoke the simulator-backed remediation tool.
6. **Verify** — collect fresh metrics; action success never implies recovery.
7. **Adapt or recover** — retain failed-attempt evidence, re-observe, and choose a different action when supported.

The optional Hugging Face/Qwen engine may propose a decision. It never executes tools directly. A deterministic evidence layer arbitrates conflicts, and a deterministic policy gate remains authoritative. With no model credentials, IncidentPilot runs fully in deterministic mode.

## Tech stack

- Python 3.11+ (tested locally with Python 3.12)
- FastAPI, Uvicorn, Pydantic
- Optional `huggingface_hub` decision proposal
- React 19, TypeScript, Vite 6, React Router, GSAP
- Pytest and FastAPI TestClient

## Local setup

PowerShell, from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location frontend
npm ci
Set-Location ..
```

Start the API in terminal 1. Deterministic mode is the fastest and fully functional demo mode:

```powershell
$env:LLM_ENABLED='false'
.\.venv\Scripts\python.exe -m uvicorn simulator.service:app --host 127.0.0.1 --port 8000
```

Start the frontend in terminal 2:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The direct dashboard URL is [http://127.0.0.1:3000/dashboard#dashboard](http://127.0.0.1:3000/dashboard#dashboard). FastAPI docs are available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### Docker Compose

The existing Compose file runs the same two local services and does not add persistence:

```powershell
docker compose up --build
```

## Environment variables

Copy `.env.example` to `.env` only if you want file-based configuration.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_ENABLED` | `false` | Enable optional HF/Qwen proposals. Deterministic fallback remains available. |
| `HF_TOKEN` | unset | Hugging Face access token used only when LLM mode is enabled. |
| `HF_MODEL` | unset | Hugging Face model identifier used only when LLM mode is enabled. |
| `CORS_ORIGINS` | localhost and 127.0.0.1 on port 3000 | Comma-separated browser origins allowed by FastAPI. |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Frontend API target, set when starting/building Vite. |

Do not commit `.env`; it is ignored by Git.

## Important APIs

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health`, `/metrics`, `/version` | Read simulator health and telemetry. |
| GET | `/status` | Unified live service, scenario, replicas, diagnostics, agent phase, and latest run. |
| GET | `/timeline` | Compact latest-attempt timeline. |
| POST | `/simulate/outage` | Inject a transient outage. |
| POST | `/simulate/bad-deployment` | Deploy v42 and inject a deployment regression. |
| POST | `/simulate/adaptive-incident` | Inject a failure where restart completes but verification fails, revealing resource pressure. |
| POST | `/run-incident` | Execute the bounded autonomous controller loop. Duplicate concurrent runs return HTTP 409. |
| POST | `/reset` | Restore health, v41, one replica, scenario flags, and agent history. |

The dashboard uses `/status` polling and mutation endpoints directly. It disables controls while disconnected or while an action is in flight, preserves the last real telemetry as stale data on connection loss, and never runs a client-side substitute workflow.

## Demo walkthrough

1. Start both processes and confirm the header says **Connected** with healthy v41 telemetry.
2. Choose **Generic Outage**, then **Run Incident**. The agent detects the SLO breach, restarts, and verifies recovery.
3. Reset, choose **Bad Deployment**, and run. Logs correlate v42 with the incident; policy approves rollback to v41 and telemetry verifies recovery.
4. Reset, choose **Adaptive Incident**, and run. Attempt 1 restarts successfully but verification rejects recovery. Attempt 2 sees new resource-exhaustion evidence, scales to three replicas, and verifies recovery.
5. Reset and repeat. All state and timeline cards return to the healthy baseline.

## Testing

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Set-Location frontend
npm run build
```

Tests cover simulator endpoints, diagnostics, policy boundaries, remediation effects, verification, decision parsing/fallback, bounded retries, blocked actions, false-success rejection, and the adaptive restart-to-scale recovery.

## Supported failures and limitations

- Generic transient outages recover through restart.
- Bad deployments recover through a version rollback selected from deployment history.
- The adaptive scenario intentionally fails verification after restart and recovers by scaling after fresh evidence appears.
- Unknown or insufficient evidence escalates rather than inventing a remediation.
- Unsafe or unsupported actions are blocked before remediation.
- The environment is deterministic and single-process. It is a safe simulator, not a connector to Kubernetes or a production control plane.
- State is process-local and is not durable across backend restarts. There is explicitly **no database**.
- Optional hosted-model latency and availability depend on the configured Hugging Face service; deterministic mode is recommended for repeatable local demos.
