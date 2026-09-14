# IncidentPilot setup

## Prerequisites

- Python 3.11 or 3.12
- Node.js 22 or newer and npm
- Optional: Docker for the containerized simulator
- Optional: Docker, kind, and kubectl for the local Kubernetes demo

Run commands from the repository root unless a step says otherwise.

## Install for development

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Set-Location frontend
npm ci
Set-Location ..
```

macOS/Linux:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-dev.txt
(cd frontend && npm ci)
```

For an API/simulator runtime without test packages, install
`requirements.txt` instead.

Optional dependency groups:

```powershell
# Hosted Qwen/Hugging Face proposals
.\.venv\Scripts\python.exe -m pip install -r requirements-llm.txt

# Local Kubernetes adapter
.\.venv\Scripts\python.exe -m pip install -r requirements-kubernetes.txt
```

Install both optional groups if both features are needed.

## Configure

No `.env` file is required. Deterministic simulator defaults work as-is. To
override them, copy `.env.example` to `.env` and edit only the needed values.
Never commit `.env` or a provider token.

The frontend defaults to `http://127.0.0.1:8000`. To change it:

```powershell
Copy-Item frontend/.env.example frontend/.env.local
```

Then edit `VITE_API_BASE_URL`. Restart Vite after changing frontend
environment variables.

## Run locally

Terminal 1, Windows PowerShell:

```powershell
$env:ENVIRONMENT='simulator'
$env:LLM_ENABLED='false'
.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Terminal 1, macOS/Linux:

```bash
ENVIRONMENT=simulator LLM_ENABLED=false \
  ./.venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Open:

- dashboard: [http://127.0.0.1:3000/dashboard](http://127.0.0.1:3000/dashboard)
- API health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- observed service: [http://127.0.0.1:8000/service/health](http://127.0.0.1:8000/service/health)
- API schema: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

The documented Uvicorn target is `backend.api.app:app`. Use a single Uvicorn
worker because demo runtime state is in memory.

## Verify the installation

Windows:

```powershell
.\.venv\Scripts\python.exe -c "from backend.api.app import app; print(app.title)"
.\.venv\Scripts\python.exe -m pytest -q
Set-Location frontend
npm test
npm run build
```

macOS/Linux:

```bash
./.venv/bin/python -c "from backend.api.app import app; print(app.title)"
./.venv/bin/python -m pytest -q
(cd frontend && npm test && npm run build)
```

The normal backend suite uses fakes for Kubernetes and does not need a
cluster. Live tests are opt-in as described in [kubernetes.md](kubernetes.md).

## Run with Docker Compose

Start Docker, then run:

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). The browser uses the
Nginx `/api` proxy, while port 8000 remains published for direct API access.
The frontend image is the unprivileged Nginx build and listens on 8080 inside
the container; Compose publishes it as 3000.

Stop the services with `docker compose down`. Simulator state disappears when
the backend container stops; there is no volume because state is deliberately
ephemeral.

## Optional hosted-model proposal

Install `requirements-llm.txt`, then set values without printing or committing
the token:

```powershell
$env:LLM_ENABLED='true'
$env:HF_TOKEN='your-token'
$env:HF_MODEL='your-model-id'
.\.venv\Scripts\python.exe scripts/check_qwen_connection.py
```

Restart the API after configuration changes. The deterministic engine remains
the fallback and the safety policy remains authoritative.

## Kubernetes mode

Kubernetes mode requires an allow-listed local cluster and the optional client
dependency. Follow [kubernetes.md](kubernetes.md), or use the checked-in
PowerShell helpers:

```powershell
.\scripts\check-k8s-demo.ps1
.\scripts\setup-k8s-demo.ps1
.\scripts\run-k8s-demo.ps1
```

Do not enable Kubernetes mode against an unreviewed or production context.

## Troubleshooting

- If port 8000 is busy, stop the process you started there or use another port
  and update the dashboard API target.
- If the dashboard is disconnected, open `/health` and `/status` directly and
  confirm `VITE_API_BASE_URL` points to that API origin. `/health` reports the
  API itself; `/service/health` reports the service it is watching.
- If settings validation fails, compare `.env` with `.env.example`; replica
  bounds may narrow but never exceed 1–3.
- If Docker commands cannot connect, start Docker Desktop/Engine before
  retrying.
- If Qwen is unavailable, leave `LLM_ENABLED=false`; it is optional.
