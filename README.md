# IncidentPilot — FrontendV1

## 1. Project Overview

**IncidentPilot** is an autonomous SRE (Site Reliability Engineering) incident response demonstration. The frontend provides:

- A cinematic **landing page** with a scroll-driven hand-joining animation
- An interactive **dashboard** that simulates autonomous incident detection, remediation, and verification

### Main User Flows

1. **Landing → Dashboard**: User scrolls down (or clicks "Launch IncidentPilot") to transition into the dashboard page.
2. **Scenario Selection**: Choose from 4 incident scenarios — Normal/Healthy, Generic Outage, Bad Deployment, Adaptive Incident.
3. **Run Incident**: Click "Run Incident" to execute the autonomous remediation loop (Observe → Decide → Safety Check → Act → Verify → Adapt).
4. **Live Telemetry**: Real-time error rate and latency monitoring with a dual-trace oscilloscope chart.
5. **Inspection**: Deep-dive cards for Decision, Safety, Verification details, and diagnostic logs.
6. **Direct Dashboard**: "Launch Dashboard" button skips the hero animation and jumps straight to the dashboard section.

### Technologies

| Technology | Purpose |
|---|---|
| React 19 | UI framework |
| TypeScript 5.7 | Type safety |
| Vite 6 | Build tool and dev server |
| React Router 7 | Client-side routing |
| GSAP 3 | Scroll transitions and page animations |

---

## 2. Frontend Architecture

```
User
  ↓
BrowserRouter (App.tsx)
  ↓
┌─────────────────────────────────────────────┐
│  Route: "/"         │  Route: "/dashboard"  │
│  LandingPage        │  DashboardPage        │
│    ↓                │    ↓                  │
│  (scroll trigger)   │  HeroSection          │
│  (GSAP transition)  │  IncidentPilotDashboard│
│                     │    ↓                  │
│                     │  useIncidentPilot hook │
│                     │    ↓                  │
│                     │  incidentPilotApi.ts   │
│                     │    ↓                  │
│                     │  FastAPI Backend       │
│                     │  (or local mock)       │
└─────────────────────────────────────────────┘
```

**Key architectural pattern:** The `useIncidentPilot` hook contains all business logic. If the FastAPI backend is unreachable, the hook automatically falls back to local (in-memory) simulation — no backend is strictly required for the demo to work.

---

## 3. Project Structure

```
frontendV1/
├── index.html                     # HTML entry point
├── vite.config.ts                 # Vite configuration (port 3000, path alias @/)
├── tsconfig.json                  # TypeScript configuration
├── package.json                   # Dependencies and scripts
├── .env                           # Environment variables
├── vite-env.d.ts                  # Vite client type declarations
├── public/
│   ├── favicon.svg                # Browser tab icon
│   ├── left-hand.png              # Robotic hand image (HeroSection)
│   └── right-hand.png             # Human hand image (HeroSection)
└── src/
    ├── main.tsx                   # React entry — renders <App />
    ├── App.tsx                    # Router: "/" and "/dashboard" routes
    ├── index.css                  # Global CSS reset and design tokens
    ├── pages/
    │   ├── LandingPage.tsx        # Landing page with pipeline animation + scroll trigger
    │   └── DashboardPage.tsx      # Dashboard page with hero + incident pilot
    ├── components/
    │   ├── HeroSection.tsx        # Scroll-driven hand-joining animation
    │   └── IncidentPilot/
    │       ├── index.ts               # Barrel export
    │       ├── IncidentPilotDashboard.tsx  # Root dashboard layout
    │       ├── Header.tsx             # Brand header + API URL input + connection pill
    │       ├── BackendAlert.tsx        # Offline warning banner
    │       ├── TelemetryDashboard.tsx  # Live service state HUD (5 metric cards)
    │       ├── ScenarioSelector.tsx    # Scenario buttons + Run/Reset controls
    │       ├── CorePrincipleBanner.tsx # "Action ≠ Recovery" axiom banner
    │       ├── AgentExecutionTimeline.tsx  # Attempt cards with step-by-step timeline
    │       ├── TelemetryMonitor.tsx    # Canvas-based real-time graph
    │       ├── InspectionSidebar.tsx   # Summary/Decision/Safety/Verification/Logs cards
    │       └── Footer.tsx             # Simple footer
    ├── hooks/
    │   └── useIncidentPilot.ts    # Core business logic hook (API calls + mock fallback)
    ├── services/
    │   └── incidentPilotApi.ts    # HTTP API client (fetch wrapper with timeout)
    ├── types/
    │   └── incidentPilot.ts       # TypeScript interfaces for all data structures
    └── styles/
        ├── landing.css            # Landing page styles
        └── incidentPilot.css      # Dashboard/IncidentPilot styles
```

---

## 4. Directory & File Explanation

| Path | Purpose |
|------|---------|
| `src/pages/` | Application-level screens/routes (LandingPage, DashboardPage) |
| `src/components/HeroSection.tsx` | Scroll-driven animation with two hand images approaching each other |
| `src/components/IncidentPilot/` | All dashboard UI components (modular, each owns its own rendering logic) |
| `src/hooks/useIncidentPilot.ts` | **The brain** — all state management, API calls, mock simulation, and incident workflows |
| `src/services/incidentPilotApi.ts` | Low-level HTTP fetch wrapper — all API calls go through `apiFetch()` |
| `src/types/incidentPilot.ts` | Shared TypeScript interfaces used by hook, components, and API service |
| `src/styles/` | CSS files — `landing.css` for landing page, `incidentPilot.css` for dashboard |
| `src/index.css` | Global CSS reset, design tokens (colors, spacing, typography, shadows) |
| `public/` | Static assets served at root (hand images, favicon) |

---

## 5. Setup & Running

### Prerequisites
- Node.js (v18+ recommended)
- npm

### Installation
```bash
cd frontendV1
npm install
```

### Development
```bash
npm run dev
# Opens at http://localhost:3000
```

### Production Build
```bash
npm run build
```

### Preview Production Build
```bash
npm run preview
```

---

## 6. Environment Variables

```env
# FastAPI backend URL for live telemetry and simulation control
VITE_API_BASE_URL=http://localhost:8000
```

The frontend works **without the backend** by falling back to in-memory mock simulation. When the backend is running, it provides live telemetry sync and real simulation state control.

---

## 7. API Contract (Backend Integration Guide)

The frontend communicates with the backend through the following endpoints. All requests use `Content-Type: application/json` and `Accept: application/json` headers with a **4-second timeout**.

### Base URL

Configured via `VITE_API_BASE_URL` environment variable (default: `http://localhost:8000`). Also configurable at runtime via the API TARGET input field in the dashboard header.

---

### `GET /health`

| Field | Value |
|-------|-------|
| **Purpose** | Check if the backend is reachable |
| **Auth** | None |
| **Request Body** | None |
| **Response** | `{ "status": "healthy" \| "down" }` |
| **Success Code** | 200 |
| **Frontend Behavior** | Sets connection pill to CONNECTED/DISCONNECTED. If unreachable, falls back to local mock simulation |

---

### `GET /metrics`

| Field | Value |
|-------|-------|
| **Purpose** | Fetch current service telemetry |
| **Auth** | None |
| **Request Body** | None |
| **Response** | `{ "error_rate": number, "latency_ms": number, "status": "healthy" \| "down" }` |
| **Response Types** | `error_rate`: float 0.0–1.0, `latency_ms`: integer, `status`: string enum |
| **Success Code** | 200 |
| **Frontend Behavior** | Updates HUD cards (error rate %, latency ms, status badge) and telemetry buffer chart |

---

### `GET /version`

| Field | Value |
|-------|-------|
| **Purpose** | Fetch current deployed version |
| **Auth** | None |
| **Request Body** | None |
| **Response** | `{ "current_version": string }` |
| **Response Types** | `current_version`: string (e.g., "v41", "v42") |
| **Success Code** | 200 |
| **Frontend Behavior** | Updates version card; "v42" is treated as the incident-trigger deployment |

---

### `POST /simulate/outage`

| Field | Value |
|-------|-------|
| **Purpose** | Trigger a simulated service outage |
| **Auth** | None |
| **Request Body** | None |
| **Response** | `{ "message": string, "state": ServiceState }` |
| **ServiceState** | `{ "status": string, "error_rate": number, "latency_ms": number, "current_version": string }` |
| **Success Code** | 200 |
| **Frontend Behavior** | Sets service to DOWN state with ~70% error rate and ~1000ms latency |

---

### `POST /simulate/bad-deployment`

| Field | Value |
|-------|-------|
| **Purpose** | Trigger a simulated bad deployment (deploys v42) |
| **Auth** | None |
| **Request Body** | None |
| **Response** | `{ "message": string, "state": ServiceState }` |
| **Success Code** | 200 |
| **Frontend Behavior** | Sets service to DOWN with version v42 |

---

### `POST /simulate/recover`

| Field | Value |
|-------|-------|
| **Purpose** | Recover the service to healthy state |
| **Auth** | None |
| **Request Body** | None |
| **Response** | `{ "message": string, "state": ServiceState }` |
| **Success Code** | 200 |
| **Frontend Behavior** | Restores healthy baseline (error_rate ~1%, latency ~100ms) |

---

### `POST /simulate/rollback?version={version}`

| Field | Value |
|-------|-------|
| **Purpose** | Roll back deployment to a specific version |
| **Auth** | None |
| **Query Params** | `version` (string, default: "v41") |
| **Request Body** | None |
| **Response** | `{ "message": string, "state": ServiceState }` |
| **Success Code** | 200 |
| **Frontend Behavior** | Used during reset and remediation to revert to stable version |

---

### Error Handling

- All endpoints: if response is non-2xx, the frontend throws and logs a warning
- If the backend is unreachable (network error or timeout), the frontend sets `connectionStatus = 'offline'` and continues with **local mock simulation**
- The frontend never blocks on backend failures — it is resilient by design

### Mock Fallback Behavior

When the backend is offline, the `useIncidentPilot` hook:
- Simulates telemetry state changes in memory
- Runs full incident workflows (observe/decide/act/verify/adapt) with `setTimeout` delays
- Pushes telemetry samples to the chart buffer at 1000ms cadence
- Updates all dashboard panels identically to live mode

> **BACKEND DECISION REQUIRED:** The frontend currently uses no authentication, no cookies, no localStorage/sessionStorage for tokens. If auth is needed, the backend developer must define the auth strategy and the frontend `apiFetch()` function in `services/incidentPilotApi.ts` should be updated to include auth headers.
