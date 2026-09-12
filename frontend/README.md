# IncidentPilot frontend

This package contains the React 19 + TypeScript + Vite interface for IncidentPilot. It preserves the cinematic landing page and provides a live operational dashboard backed entirely by the FastAPI simulator.

The dashboard polls `GET /status` for service telemetry, scenario state, diagnostics, replicas, agent phase, and the latest incident record. Scenario, reset, and agent-run controls call the backend directly. There is no client-side mock workflow; if the backend is unavailable, the last real values are marked stale and mutating controls are disabled.

Run from this directory after starting the API:

```powershell
npm ci
npm run dev -- --host 127.0.0.1
```

The default API URL is `http://127.0.0.1:8000`. Override it with `VITE_API_BASE_URL` or the dashboard's API target field. See the repository root [`README.md`](../README.md) for full setup, architecture, APIs, demo flow, and tests.
