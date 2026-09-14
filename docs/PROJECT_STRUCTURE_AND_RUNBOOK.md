# IncidentPilot Project Structure and Runbook

This guide explains the project in plain language: what each important file or directory does, the intuition behind the system, a real-life analogy, and the commands needed to run it locally.

## Big Picture

IncidentPilot is a bounded autonomous incident-response agent. It watches a service, detects when the service is unhealthy, gathers evidence, chooses a safe remediation, executes only allow-listed actions, and then verifies from fresh telemetry whether the service really recovered.

Intuition: it is not just a button that runs a command. It is a feedback loop: observe, diagnose, act, verify, and replan if the first action did not actually fix the incident.

Real-life analogy: imagine a hospital emergency team. A patient arrives with symptoms, the doctor checks vitals, orders tests, chooses a safe treatment, watches whether the patient improves, and changes treatment if the first attempt does not work. IncidentPilot does the same thing for a software service.

## Main Architecture Story

The project has three major parts:

| Part | What it does | Intuition | Real-life analogy |
| --- | --- | --- | --- |
| Backend | Runs the agent brain, simulator, safety policy, API, and infrastructure adapters. | This is the decision-making engine. | The control room where the incident commander works. |
| Frontend | Shows the dashboard, buttons, telemetry, timeline, and inspection panels. | This is the visual cockpit for the demo. | The large operations screen in a command center. |
| Tests and deployment files | Prove behavior and support Docker/Kubernetes demos. | This is the confidence layer. | Fire drills and runbooks before the real emergency. |

## Runtime Flow

```text
React dashboard
  -> FastAPI routes
  -> IncidentRuntime
  -> IncidentController
  -> Decision engine
  -> Safety policy
  -> Infrastructure adapter
  -> Verifier
  -> Timeline and dashboard update
```

Intuition: every user click on the dashboard becomes an API call, every API call updates backend state, and every backend transition is shown back to the user as telemetry, attempts, and timeline events.

## Top-Level Files and Directories

| Path | What it does |
| --- | --- |
| `.git/` | Stores Git history and version-control metadata for the repository. |
| `.github/` | Contains GitHub automation files, mainly test workflows. |
| `.github/workflows/tests.yml` | Runs backend and frontend checks in CI. |
| `.idea/` | Local JetBrains IDE settings; useful for your machine, not part of app logic. |
| `.pytest_cache/` | Generated pytest cache; safe to ignore. |
| `.venv/` | Local Python virtual environment where backend dependencies are installed. |
| `backend/` | Python backend containing the agent, API, simulator, safety policy, and adapters. |
| `deploy/` | Kubernetes manifests and demo workload files. |
| `docs/` | Human-facing documentation, demo scripts, setup, architecture, and this guide. |
| `frontend/` | React and Vite dashboard application. |
| `scripts/` | Helper scripts for Kubernetes, Qwen connection checks, and demo automation. |
| `tests/` | Backend test suite plus Kubernetes fakes and integration tests. |
| `.dockerignore` | Tells Docker which local files to exclude from image builds. |
| `.env` | Local environment overrides; may contain machine-specific settings. |
| `.env.example` | Safe example environment variables to copy from. |
| `.gitignore` | Tells Git which generated/local files not to commit. |
| `.incidentpilot-kubernetes-run.json` | Local record from a Kubernetes demo run. |
| `docker-compose.yml` | Starts backend and frontend together with Docker Compose. |
| `Dockerfile` | Builds the backend API container image. |
| `pytest.ini` | Configures pytest test discovery and Python path behavior. |
| `README.md` | Main project overview, quick start, API list, demo flow, and limitations. |
| `requirements.txt` | Minimal backend runtime dependencies. |
| `requirements-dev.txt` | Development and test dependencies. |
| `requirements-kubernetes.txt` | Optional dependencies for Kubernetes mode. |
| `requirements-llm.txt` | Optional dependencies for LLM/Qwen decision proposals. |
| `system-architecture.svg` | Architecture diagram used by the README. |

Intuition: the root folder is like the project lobby. It points you to the backend brain, frontend dashboard, docs, tests, and deployment options.

Real-life analogy: the root is a building directory board: "Engineering is on floor backend, showroom is frontend, manuals are docs, drills are tests."

## Backend Structure

| Path | What it does |
| --- | --- |
| `backend/__init__.py` | Marks `backend` as a Python package. |
| `backend/config.py` | Reads and validates settings such as environment mode, SLO thresholds, safety bounds, CORS origins, and optional LLM configuration. |
| `backend/models.py` | Defines the validated domain objects: incident runs, phases, actions, evidence, safety decisions, verification results, and timeline events. |
| `backend/agent/` | Contains the autonomous incident-response logic. |
| `backend/agent/__init__.py` | Marks the agent folder as a package. |
| `backend/agent/controller.py` | Orchestrates observe, detect, investigate, diagnose, plan, safety, execute, verify, and replan. |
| `backend/agent/decision.py` | Converts logs, metrics, history, and previous attempts into evidence-backed deterministic decisions. |
| `backend/agent/llm_decision.py` | Optional LLM proposal engine; its output is advisory and still checked against deterministic evidence and safety policy. |
| `backend/api/` | Contains FastAPI app setup, routes, runtime state, and response schemas. |
| `backend/api/__init__.py` | Marks the API folder as a package. |
| `backend/api/app.py` | Creates the FastAPI app, loads `.env`, adds CORS, and attaches routes. |
| `backend/api/routes.py` | Exposes endpoints like `/health`, `/status`, `/run-incident`, simulator scenario endpoints, and safety evaluation. |
| `backend/api/runtime.py` | Manages one active incident run, revisioned state, timeline events, and background execution. |
| `backend/api/schemas.py` | Defines typed API request and response models for the dashboard and clients. |
| `backend/infrastructure/` | Defines the interface between the agent and the world it controls. |
| `backend/infrastructure/__init__.py` | Re-exports infrastructure helpers for simpler imports. |
| `backend/infrastructure/base.py` | Defines the abstract infrastructure contract and shared errors. |
| `backend/infrastructure/factory.py` | Selects simulator or Kubernetes infrastructure from configuration. |
| `backend/infrastructure/simulator.py` | Implements the infrastructure contract using the deterministic local simulator. |
| `backend/infrastructure/kubernetes/` | Implements a restricted Kubernetes adapter for a local demo cluster. |
| `backend/infrastructure/kubernetes/__init__.py` | Marks the Kubernetes adapter folder as a package. |
| `backend/infrastructure/kubernetes/adapter.py` | Converts Kubernetes Deployment, Service, Pod, logs, probes, and scale operations into the common infrastructure contract. |
| `backend/infrastructure/kubernetes/config.py` | Validates Kubernetes namespace, deployment, service, context, replica bounds, and probe settings. |
| `backend/infrastructure/kubernetes/gateway.py` | Restricts Kubernetes reads/writes so only the allow-listed workload can be observed or changed. |
| `backend/safety/` | Contains the deterministic safety gate. |
| `backend/safety/__init__.py` | Marks the safety folder as a package. |
| `backend/safety/policy.py` | Approves or blocks proposed actions based on action type, target, namespace, replica bounds, rollout history, and attempt budget. |
| `backend/shared/` | Shared backend utilities. |
| `backend/shared/__init__.py` | Marks shared utilities as a package. |
| `backend/shared/slo.py` | Provides SLO threshold compatibility helpers. |
| `backend/simulator/` | Contains the deterministic incident simulator. |
| `backend/simulator/__init__.py` | Marks simulator code as a package. |
| `backend/simulator/environment.py` | Models service health, scenarios, versions, replica count, logs, metrics, and recovery behavior. |
| `backend/tools/` | Simulator tool functions used by the simulator infrastructure. |
| `backend/tools/__init__.py` | Marks tool functions as a package. |
| `backend/tools/diagnostics.py` | Reads simulator metrics, health, version, logs, capacity, and deployment history. |
| `backend/tools/remediation.py` | Performs simulator remediation actions: restart, rollback, scale, and reset replicas. |
| `backend/verification/` | Contains recovery verification logic. |
| `backend/verification/__init__.py` | Marks verification code as a package. |
| `backend/verification/verifier.py` | Checks whether fresh samples, health, SLOs, and readiness prove recovered, partial, or failed recovery. |

Backend intuition: the backend is built around a strict separation of concerns. The controller thinks, the policy says what is safe, the infrastructure adapter touches the environment, and the verifier decides whether the action actually worked.

Backend analogy: a train station. The controller is the dispatcher, the policy is the safety inspector, the adapter is the track switch operator, and the verifier is the person confirming the train actually reached the right platform.

## Frontend Structure

| Path | What it does |
| --- | --- |
| `frontend/.env.example` | Example frontend environment variable for API base URL overrides. |
| `frontend/Dockerfile` | Builds the production frontend container. |
| `frontend/index.html` | HTML shell where React mounts the app. |
| `frontend/nginx.conf` | Production Nginx config that serves the app and proxies API requests. |
| `frontend/package.json` | Defines Node scripts and frontend dependencies. |
| `frontend/package-lock.json` | Locks exact npm dependency versions. |
| `frontend/tsconfig.json` | TypeScript compiler settings. |
| `frontend/tsconfig.tsbuildinfo` | Generated TypeScript build cache; ignored by Git and created during builds. |
| `frontend/vite-env.d.ts` | Vite TypeScript environment declarations. |
| `frontend/vite.config.ts` | Vite development/build configuration. |
| `frontend/dist/` | Generated production frontend build output; ignored by Git. |
| `frontend/node_modules/` | Installed npm dependencies; generated by `npm ci` and ignored by Git. |
| `frontend/public/` | Static assets copied directly into the frontend app. |
| `frontend/public/favicon.svg` | Browser tab icon. |
| `frontend/public/logo.gif` | Animated/project logo asset. |
| `frontend/src/` | React source code. |
| `frontend/src/main.tsx` | React entry point that mounts the app into the HTML page. |
| `frontend/src/App.tsx` | Defines app routes for landing page and dashboard. |
| `frontend/src/index.css` | Global CSS baseline. |
| `frontend/src/pages/` | Page-level React views. |
| `frontend/src/pages/LandingPage.tsx` | Marketing/demo landing page explaining the concept visually. |
| `frontend/src/pages/DashboardPage.tsx` | Dashboard route that renders the live IncidentPilot UI. |
| `frontend/src/services/` | API client functions. |
| `frontend/src/services/api.ts` | Fetches backend config, health, status, timeline, simulator actions, safety evaluation, reset, and run commands. |
| `frontend/src/hooks/` | React stateful logic. |
| `frontend/src/hooks/useIncidentPilot.ts` | Polls the backend, stores dashboard state, triggers scenarios, starts runs, resets state, and evaluates safety. |
| `frontend/src/types/` | Frontend TypeScript data contracts. |
| `frontend/src/types/incidentPilot.ts` | Types for service state, agent state, timeline events, attempts, diagnostics, safety, and verification. |
| `frontend/src/viewModels/` | Converts backend data into display-ready frontend objects. |
| `frontend/src/viewModels/incidentPilot.ts` | Maps raw API responses into labels, summaries, attempts, checks, decisions, and dashboard-friendly text. |
| `frontend/src/viewModels/incidentPilot.test.ts` | Tests frontend mapping behavior. |
| `frontend/src/styles/` | CSS for frontend pages and dashboard. |
| `frontend/src/styles/landing.css` | Styling for the landing page. |
| `frontend/src/styles/incidentPilot.css` | Styling for the dashboard and incident panels. |
| `frontend/src/components/IncidentPilot/` | Reusable dashboard components. |
| `frontend/src/components/IncidentPilot/AgentExecutionTimeline.tsx` | Shows chronological backend timeline events for the current/latest run. |
| `frontend/src/components/IncidentPilot/BackendAlert.tsx` | Shows backend connectivity or API error messages. |
| `frontend/src/components/IncidentPilot/CommandBar.tsx` | Contains main action buttons like run, reset, and safety test. |
| `frontend/src/components/IncidentPilot/CorePrincipleBanner.tsx` | Highlights the core bounded-agent principle. |
| `frontend/src/components/IncidentPilot/Footer.tsx` | Dashboard footer. |
| `frontend/src/components/IncidentPilot/Header.tsx` | Dashboard header and environment/status summary. |
| `frontend/src/components/IncidentPilot/IncidentFocus.tsx` | Summarizes the current incident, status, and key outcome. |
| `frontend/src/components/IncidentPilot/IncidentPilotDashboard.tsx` | Composes the full dashboard layout from smaller components. |
| `frontend/src/components/IncidentPilot/index.ts` | Barrel export for dashboard components. |
| `frontend/src/components/IncidentPilot/InspectorTabs.tsx` | Shows Summary, Decision, Safety, Verification, and Logs tabs. |
| `frontend/src/components/IncidentPilot/LifecycleStrip.tsx` | Visualizes the agent phase progression. |
| `frontend/src/components/IncidentPilot/RunContext.tsx` | Displays run metadata and contextual details. |
| `frontend/src/components/IncidentPilot/ScenarioSelector.tsx` | Lets the user choose Healthy, Generic Outage, Bad Deployment, or Adaptive Incident. |
| `frontend/src/components/IncidentPilot/TelemetryDashboard.tsx` | Shows live service metrics and state. |
| `frontend/src/components/IncidentPilot/TelemetryMonitor.tsx` | Shows rolling telemetry samples over time. |

Frontend intuition: the frontend does not make decisions itself. It is a cockpit that calls the backend and renders what the backend proves.

Frontend analogy: a car dashboard. The dashboard shows speed, warnings, and buttons, but the engine and brakes live underneath.

## Deployment and Kubernetes Files

| Path | What it does |
| --- | --- |
| `deploy/kubernetes/` | Kubernetes demo manifests and scenario workload configuration. |
| `deploy/kubernetes/namespace.yaml` | Creates the `incidentpilot` namespace. |
| `deploy/kubernetes/rbac.yaml` | Gives the demo identity limited permissions. |
| `deploy/kubernetes/kind-cluster.yaml` | Defines a local Kind cluster setup. |
| `deploy/kubernetes/demo-workload.yaml` | Defines the allow-listed demo service/deployment. |
| `deploy/kubernetes/scenarios/` | Files used to create repeatable Kubernetes failure scenarios. |
| `deploy/kubernetes/scenarios/Dockerfile` | Builds the scenario server image. |
| `deploy/kubernetes/scenarios/scenario_server.py` | Tiny workload server that exposes behavior used by Kubernetes scenarios. |
| `deploy/kubernetes/scenarios/base.yaml` | Base Kubernetes scenario manifest. |
| `deploy/kubernetes/scenarios/restart.patch.yaml` | Patch used to simulate/recover restart-related state. |
| `deploy/kubernetes/scenarios/clear-restart.patch.yaml` | Patch that clears restart markers. |
| `deploy/kubernetes/scenarios/bad-deployment.patch.yaml` | Patch that simulates a bad deployment. |
| `deploy/kubernetes/scenarios/adaptive-resource-pressure.patch.yaml` | Patch that simulates adaptive resource pressure. |

Intuition: Kubernetes mode uses the same agent loop, but points the infrastructure adapter at a real local cluster instead of the in-memory simulator.

Analogy: the simulator is a driving simulator; Kubernetes mode is the same driver on a closed test track.

## Scripts

| Path | What it does |
| --- | --- |
| `scripts/check_kubernetes_connection.py` | Checks that the Kubernetes adapter can safely reach the configured workload. |
| `scripts/check_qwen_connection.py` | Checks optional Qwen/Hugging Face LLM connectivity. |
| `scripts/check-k8s-demo.ps1` | PowerShell preflight checks for the Kubernetes demo. |
| `scripts/reset-k8s-demo.ps1` | Resets the Kubernetes demo workload. |
| `scripts/run_kubernetes_agent.py` | Runs the agent against Kubernetes from the command line. |
| `scripts/run_kubernetes_scenario.ps1` | Applies Kubernetes scenario changes. |
| `scripts/run-k8s-demo.ps1` | Starts a Kubernetes demo run. |
| `scripts/setup-k8s-demo.ps1` | Creates/prepares the local Kubernetes demo environment. |

Intuition: scripts are shortcuts for repeatable setup and demo steps.

Analogy: they are the labeled switches in a lab so you do not have to wire everything by hand every time.

## Documentation Files

| Path | What it does |
| --- | --- |
| `docs/ARCHITECTURE.md` | Detailed architecture explanation. |
| `docs/ARCHITECTURE_VISUALS_TEXT.md` | Plain-text architecture diagrams and speaker notes for presentations. |
| `docs/DEMO.md` | Judge-focused demo runbook with expected scenario behavior. |
| `docs/DEMO_VIDEO_SCRIPT.md` | Full spoken demo video script and shot list. |
| `docs/kubernetes.md` | Kubernetes setup and adapter documentation. |
| `docs/kubernetes-scenarios.md` | Kubernetes scenario guide. |
| `docs/SETUP.md` | Local setup instructions. |
| `docs/PROJECT_STRUCTURE_AND_RUNBOOK.md` | This plain-English project structure and run command guide. |

Intuition: docs are the map you use when presenting, debugging, or onboarding someone new.

Analogy: the code is the machine; the docs are the operator manual.

## Tests

| Path | What it does |
| --- | --- |
| `tests/__init__.py` | Marks tests as a Python package. |
| `tests/conftest.py` | Shared pytest setup. |
| `tests/helpers.py` | Helper functions for running incidents and waiting for runtime state. |
| `tests/k8s_fakes.py` | Fake Kubernetes cluster objects for safe adapter tests without a real cluster. |
| `tests/test_adaptive_loop.py` | Tests adaptive replanning after failed verification. |
| `tests/test_agent.py` | Tests evidence collection and deterministic decision behavior. |
| `tests/test_api_integration.py` | Tests full API behavior and dashboard-facing contracts. |
| `tests/test_configuration.py` | Tests safe defaults and environment override validation. |
| `tests/test_controller.py` | Tests the controller's observe, decide, execute, verify, and run loop behavior. |
| `tests/test_diagnostics.py` | Tests simulator diagnostic tools. |
| `tests/test_infrastructure.py` | Tests infrastructure abstraction and simulator/Kubernetes mode boundaries. |
| `tests/test_kubernetes_adapter.py` | Tests Kubernetes safety restrictions and adapter behavior with fakes. |
| `tests/test_llm_decision.py` | Tests optional LLM output validation and fallback behavior. |
| `tests/test_models.py` | Tests Pydantic domain model validation and serialization. |
| `tests/test_remediation.py` | Tests simulator remediation tools. |
| `tests/test_runtime.py` | Tests background runtime state, locking, events, and failure surfacing. |
| `tests/test_safety.py` | Tests the deterministic safety policy. |
| `tests/test_simulator_api.py` | Tests simulator API endpoints. |
| `tests/test_timeline.py` | Tests timeline event ordering and content. |
| `tests/test_verification.py` | Tests recovery verification verdicts. |
| `tests/integration/` | Optional integration tests. |
| `tests/integration/__init__.py` | Marks integration tests as a package. |
| `tests/integration/test_kubernetes_live.py` | Optional live Kubernetes tests, gated by `RUN_K8S_INTEGRATION=1`. |

Intuition: tests prove that the demo is not only a UI animation. They verify the agent loop, safety gate, API, and adapters.

Analogy: tests are rehearsal runs before the hackathon stage.


## Commands to Run the Project

Run these from PowerShell on Windows unless stated otherwise.

### 1. Clone the project

```powershell
git clone <your-repository-url>
Set-Location incidentpilot
```

Meaning:

| Command | Meaning |
| --- | --- |
| `git clone <url>` | Downloads the repository from GitHub or another Git server. |
| `Set-Location incidentpilot` | Enters the project folder. Same idea as `cd incidentpilot`. |

### 2. Create a Python virtual environment

```powershell
py -3.12 -m venv .venv
```

Meaning:

| Part | Meaning |
| --- | --- |
| `py -3.12` | Runs Python 3.12 through the Windows Python launcher. Python 3.11 also works. |
| `-m venv` | Uses Python's built-in virtual environment module. |
| `.venv` | Creates an isolated local Python environment inside the project. |

Intuition: `.venv` keeps this project's Python packages separate from the rest of your computer.

Analogy: it is a dedicated toolbox for this project, so tools from another project do not get mixed in.

### 3. Install backend dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Meaning:

| Part | Meaning |
| --- | --- |
| `.\.venv\Scripts\python.exe` | Uses the Python executable inside this project's virtual environment. |
| `-m pip install` | Runs Python's package installer. |
| `-r requirements-dev.txt` | Installs every package listed in the development requirements file. |

### 4. Install frontend dependencies

```powershell
Set-Location frontend
npm ci
Set-Location ..
```

Meaning:

| Command | Meaning |
| --- | --- |
| `Set-Location frontend` | Moves into the frontend folder. |
| `npm ci` | Installs exact Node dependencies from `package-lock.json`. Best for reproducible setup. |
| `Set-Location ..` | Moves back to the repository root. |

### 5. Start the backend API

Run this from the repository root:

```powershell
$env:ENVIRONMENT='simulator'
$env:LLM_ENABLED='false'
.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Meaning:

| Part | Meaning |
| --- | --- |
| `$env:ENVIRONMENT='simulator'` | Tells the backend to use the local deterministic simulator instead of Kubernetes. |
| `$env:LLM_ENABLED='false'` | Keeps the demo deterministic and avoids needing LLM credentials. |
| `uvicorn` | The ASGI server that runs the FastAPI app. |
| `backend.api.app:app` | Means: import `app` from `backend/api/app.py`. |
| `--host 127.0.0.1` | Binds the server to your own computer only. |
| `--port 8000` | Makes the API available on port 8000. |

What is `localhost` / `127.0.0.1`?

`127.0.0.1` means "this same computer." `localhost` is a friendly name for the same idea. When you open `http://127.0.0.1:8000`, your browser is talking to a server running on your own machine, not the public internet.

Backend URLs:

| URL | Meaning |
| --- | --- |
| `http://127.0.0.1:8000/health` | Checks whether the API is alive. |
| `http://127.0.0.1:8000/docs` | Opens FastAPI's interactive API documentation. |
| `http://127.0.0.1:8000/status` | Shows the current service and agent state as JSON. |

### 6. Start the frontend dashboard

Open a second PowerShell terminal:

```powershell
Set-Location C:\Users\sayan\IdeaProjects\incidentpilot\frontend
npm run dev -- --host 127.0.0.1
```

Meaning:

| Part | Meaning |
| --- | --- |
| `npm run dev` | Starts the Vite development server. |
| `-- --host 127.0.0.1` | Passes the host setting through to Vite. |

Open:

```text
http://127.0.0.1:3000/dashboard
```

Meaning: the React dashboard is running locally on port 3000 and calling the backend API on port 8000.

### 7. Demo flow

Use this for the hackathon:

1. Open `http://127.0.0.1:3000/dashboard`.
2. Click `Reset`.
3. Select `Healthy`.
4. Click `Run Incident` and show it ends as `NO INCIDENT`.
5. Select `Adaptive Incident`.
6. Click `Run Incident`.
7. Show attempt 1: restart is allowed and executed, but verification fails.
8. Show the agent replans from fresh evidence.
9. Show attempt 2: scale to 3 replicas and verify recovery.
10. Click `Test Safety Gate: scale to 20` and show it is blocked without execution.

### 8. Run tests

Backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Frontend tests:

```powershell
Set-Location frontend
npm test
```

Frontend production build:

```powershell
npm run build
```

Meaning:

| Command | Meaning |
| --- | --- |
| `pytest -q` | Runs Python tests quietly. |
| `npm test` | Runs frontend unit tests with Vitest. |
| `npm run build` | Compiles TypeScript and creates the production frontend bundle. |

### 9. Run with Docker

```powershell
docker compose up --build
```

Meaning:

| Part | Meaning |
| --- | --- |
| `docker compose` | Runs multiple containers defined in `docker-compose.yml`. |
| `up` | Starts the containers. |
| `--build` | Rebuilds images before starting. |

Open:

```text
http://localhost:3000
```

Intuition: Docker packages backend and frontend into containers so the app runs the same way on another machine.

Analogy: instead of telling someone how to rebuild your kitchen, Docker gives them a portable kitchen-in-a-box.

### 10. Optional Kubernetes demo commands

These are only needed if you want to demo the restricted Kubernetes adapter.

```powershell
.\scripts\check-k8s-demo.ps1
.\scripts\setup-k8s-demo.ps1
.\scripts\run-k8s-demo.ps1
.\scripts\reset-k8s-demo.ps1
```

Meaning:

| Command | Meaning |
| --- | --- |
| `check-k8s-demo.ps1` | Confirms required tools/config are available. |
| `setup-k8s-demo.ps1` | Creates or prepares the local Kubernetes demo environment. |
| `run-k8s-demo.ps1` | Runs the Kubernetes demo. |
| `reset-k8s-demo.ps1` | Restores the Kubernetes demo state. |

Optional direct checks:

```powershell
.\.venv\Scripts\python.exe scripts\check_kubernetes_connection.py
.\.venv\Scripts\python.exe scripts\check_qwen_connection.py
```

Meaning:

| Command | Meaning |
| --- | --- |
| `check_kubernetes_connection.py` | Tests whether the backend can safely reach the configured Kubernetes workload. |
| `check_qwen_connection.py` | Tests optional LLM provider connectivity. |

## Common Terms

| Term | Meaning in this project |
| --- | --- |
| API | The backend HTTP interface that the frontend calls. |
| FastAPI | Python web framework used for backend routes. |
| Uvicorn | Server that runs the FastAPI app. |
| React | Frontend UI library. |
| Vite | Frontend dev server and build tool. |
| npm | Node package manager. |
| venv | Isolated Python environment for project dependencies. |
| SLO | Service Level Objective, such as max error rate or max latency. |
| Telemetry | Metrics, health checks, logs, version, and capacity readings. |
| Remediation | A controlled fix action like restart, rollback, or scale. |
| Safety gate | Policy check that blocks unsafe actions before execution. |
| Verification | Fresh checks after an action to prove recovery. |
| Simulator | Local fake service environment used for reliable demos. |
| Adapter | Code that lets the same agent talk to simulator or Kubernetes. |
| Replica | A running copy of the service. Scaling to 3 replicas means running 3 copies. |
| Port | A numbered door where a local server listens, like 8000 for API and 3000 for UI. |

## How to Explain the Main Objects

| Object | One-liner | Intuition | Real-life story |
| --- | --- | --- | --- |
| `IncidentController` | The main agent loop that observes, diagnoses, acts, verifies, and replans. | The brain of the incident response. | A doctor treating a patient and checking if the medicine worked. |
| `IncidentRuntime` | Holds the current run, prevents duplicate runs, and publishes timeline state. | The run manager. | A race official who starts one race at a time and records every lap. |
| `DecisionEngine` | Chooses the likely cause and safest supported action from evidence. | The reasoning layer. | A mechanic listening to engine sounds and choosing what to inspect first. |
| `SafetyPolicy` | Blocks anything outside allowed action, namespace, target, replica, or attempt bounds. | The guardrail. | A lab supervisor who only permits approved experiments. |
| `Verifier` | Checks fresh telemetry after an action before calling the incident resolved. | The proof layer. | A nurse rechecking vitals after treatment. |
| `SimulatorEnvironment` | Creates deterministic healthy and failure scenarios. | The demo world. | A flight simulator for practicing emergencies. |
| `Infrastructure` | Abstract interface for reading and changing a service environment. | A plug shape for different worlds. | A universal remote that can control either a demo TV or a real test TV. |
| `SimulatorInfrastructure` | Implements the infrastructure interface using local simulator functions. | Local safe mode. | Practicing repairs on a model engine. |
| `KubernetesInfrastructure` | Implements the infrastructure interface against a restricted local Kubernetes workload. | Real cluster demo mode. | Doing the same drill on a closed training field. |
| `KubernetesGateway` | Enforces low-level Kubernetes access restrictions. | The locked door to the cluster. | A security guard checking every badge before anyone touches equipment. |
| `IncidentPilotDashboard` | Composes the visible dashboard panels. | The cockpit. | A control-room wall display. |
| `useIncidentPilot` | Polls the backend and exposes commands to React components. | The dashboard's live data wire. | A radio operator continuously relaying field updates. |
| `api.ts` | Wraps backend HTTP calls for the frontend. | The frontend's phone book. | A receptionist who knows which extension to call. |
| `viewModels/incidentPilot.ts` | Converts raw backend JSON into readable UI labels and panels. | The translator. | Turning technical logs into a judge-friendly briefing. |

## Best Hackathon Explanation

Say this:

```text
IncidentPilot is a bounded autonomous incident-response agent. It detects a service incident, gathers evidence, proposes only restricted remediations, checks every action through a deterministic safety policy, executes through a simulator or Kubernetes adapter, and verifies recovery from fresh telemetry. The adaptive incident proves it is not a fixed script: the first successful restart does not recover the service, so the agent replans from new evidence and scales safely.
```

Then show this:

1. Healthy run does nothing.
2. Adaptive incident starts unhealthy.
3. Attempt 1 restarts and fails verification.
4. Fresh evidence reveals capacity pressure.
5. Attempt 2 scales to 3 replicas and verifies recovery.
6. Safety gate blocks scale to 20.

