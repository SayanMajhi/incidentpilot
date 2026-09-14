# IncidentPilot architecture

## System boundary

IncidentPilot has four layers with deliberately narrow responsibilities:

```text
Dashboard
  └─ reads public API state and submits commands
       └─ FastAPI routes
            └─ RuntimeManager
                 ├─ owns the active/latest run, scenario mutations, lock, and revision
                 └─ starts one IncidentController worker
                      ├─ DecisionEngine (optional LLM proposal is advisory)
                      ├─ SafetyPolicy (deterministic enforcement)
                      ├─ Verifier (fresh, named recovery checks)
                      └─ Infrastructure
                           ├─ SimulatorInfrastructure → SimulatorEnvironment
                           └─ KubernetesInfrastructure → restricted KubernetesGateway
```

Routes translate HTTP requests and responses; they do not contain incident
reasoning. The controller depends on the `Infrastructure` interface and never
mutates simulator or Kubernetes state directly.

## Execution lifecycle

Every incident run has an explicit goal: restore the target service to the
configured SLO without crossing the safety boundary. The real control loop is:

```text
OBSERVING
    │
    ├─ no SLO breach ──────────────────────────────► NO_INCIDENT
    ▼
INCIDENT_DETECTED → INVESTIGATING → DIAGNOSING → PLANNING
                                                    │
                                                    ▼
                                              SAFETY_CHECK
                                             /            \
                                      rejected              allowed
                                         │                    │
                                      BLOCKED             EXECUTING
                                                              │
                                                        fresh reads
                                                              │
                                                         VERIFYING
                                                      /       |       \
                                              recovered    partial    failed
                                                  │           └──┬──────┘
                                               RESOLVED       REPLANNING
                                                                 │
                                                attempts remain? ├─ yes → investigate
                                                                 └─ no  → ESCALATED
```

The adaptive simulator case is causally modeled. Initially, hung workers hide
capacity evidence, so a restart is a reasonable first action. The restart
clears only that transient condition. Verification then reads an unhealthy
60% error rate, 750 ms latency, 91% CPU, and one replica. A new investigation
reveals resource pressure, leading the decision engine to scale to three.
Fresh telemetry reaches 1% errors, 100 ms latency, and 48% CPU, so verification
resolves the run. No controller or decision code reads the scenario name.

## Run state and audit events

Production state uses validated domain models. A run retains its ID, goal,
phase, status, observations, evidence and hypotheses, proposed and attempted
actions, safety decisions, action results, verification results, failed
actions, attempt count, outcome, and timestamps.

The controller appends an immutable, timestamped event for meaningful
transitions such as observation, detection, evidence collection, diagnosis,
proposal, policy verdict, execution, verification, replanning, recovery,
blocking, escalation, and tool errors. Events are stored whether or not a UI
callback is attached. `/status` and `/timeline` expose snapshots from the same
runtime revision, so browser reloads do not invent or lose progress.

## Runtime and concurrency

`RuntimeManager` serializes run lifecycle and simulator mutations with one
lock. Starting a run reserves the sole worker and returns HTTP 202 immediately.
While it is active, another run, scenario injection, or reset receives HTTP
409. Reads remain available. This prevents a second client from changing the
environment between an observation and its corresponding action or
verification.

State is intentionally process-local. Multiple Uvicorn workers would each
have independent state, so the demo must run with the default single worker.

## Decision and adaptation

The deterministic engine derives ranked hypotheses and one proposal from
current evidence plus prior failed attempts. Failed verification is retained
before the next observation. The decision engine avoids blindly repeating a
failed action while allowing a materially different target when new evidence
supports it.

When enabled, Qwen/Hugging Face supplies only a proposal. Its output must match
a strict schema, has no tool handle, and is overruled when inconsistent with
deterministic evidence. Execution authority always remains with the
deterministic policy.

## Safety model

The top-level policy denies unknown actions, wrong namespaces, invalid
targets, replica counts outside 1–3, and requests beyond the three-attempt
budget. It returns a structured verdict containing the rule and explanation.
Rejected proposals never reach an infrastructure adapter.

Kubernetes adds independent defense in depth:

- the namespace is fixed to `incidentpilot`;
- Deployment, Service, and kubeconfig context must be explicitly allow-listed;
- writes require `incidentpilot.io/managed=true`;
- rollback is limited to a known prior revision;
- scale bounds are checked again by the adapter and gateway;
- the gateway exposes no shell, pod exec, arbitrary request, apply, create, or
  delete operation.

## Verification model

Execution records whether infrastructure accepted an action. Verification is
a separate phase that obtains fresh telemetry and readiness state after any
reconciliation wait. It records all sample summaries, before/after deltas,
and named checks for error rate, latency, health, readiness, and sustained
samples. The result distinguishes `recovered`, `partial`, and `failed`.

Expected infrastructure exceptions are converted to timeline events and
attempt outcomes. The controller may re-observe within its remaining budget;
exhaustion produces an explicit escalation. Only unexpected internal defects
use the terminal `failed` status.

## Configuration

`backend/config.py` owns validated SLOs, retry/verification behavior, CORS,
environment choice, simulator defaults, and public capability settings.
`.env.example` documents supported overrides. Kubernetes target validation is
also enforced by its adapter settings. `/config` serializes only non-secret
effective values.

## Deployment shape

- Local development: Uvicorn on port 8000 and Vite on port 3000.
- Docker Compose: production Uvicorn image plus an Nginx-built frontend; Nginx
  proxies `/api` to the backend.
- Kubernetes mode: the API remains local and connects through an allow-listed
  kubeconfig context to the demo workload. IncidentPilot itself is not
  deployed into the cluster by the supplied manifests.

## Known limitations

There is no durable database, distributed lock, queue, multi-tenant isolation,
or Prometheus integration. Kubernetes probing includes API-server proxy
latency. The rollback implementation is sufficient for the controlled demo
workload but is not a general replacement for a production rollout system.
