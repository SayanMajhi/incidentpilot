# IncidentPilot architecture visuals

These diagrams are designed for PowerPoint, speaker notes, README files, or a
terminal-based explanation. Use a monospace font such as Consolas so the
alignment remains intact.

## 1. Verified recovery loop

```text
OBSERVE  >  DETECT  >  INVESTIGATE  >  DIAGNOSE
                                      |
                                      v
VERIFY  <  EXECUTE  <  SAFETY GATE  <  PLAN
  |
  +-- checks pass ........................ RESOLVED
  |
  +-- checks fail .... fresh evidence .... REPLAN
  |
  +-- attempt limit reached .............. ESCALATE
```

### What to say

IncidentPilot follows a closed feedback loop. It collects new telemetry after
every action. Passing checks resolve the run. Failed checks create new evidence
for another investigation. The controller escalates after its bounded attempt
budget.

### Layman explanation

A doctor checks the patient after treatment. If the patient remains sick, the
doctor studies the new symptoms and changes the treatment.

## 2. System architecture

```text
React dashboard
      |  REST + polling
      v
FastAPI routes  >  IncidentRuntime  >  IncidentController
                                         |
                  +----------------------+------------------+
                  |                      |                  |
           Decision engine         Safety policy        Verifier
                  |                      |                  |
                  +----------------------+------------------+
                                         |
                              Infrastructure interface
                                   /             \
                         Simulator adapter   Kubernetes adapter
                                                   |
                                         Restricted gateway
                                                   |
                                           Kubernetes API
```

### What to say

The React dashboard displays backend-owned state. FastAPI exposes commands and
read endpoints. IncidentRuntime owns the active run and timeline. The
controller coordinates reasoning, policy, execution, and verification through
an infrastructure interface. That interface allows the same control loop to
use either a deterministic simulator or a real Kubernetes cluster.

### Layman explanation

The dashboard is the cockpit. The controller is the pilot. The infrastructure
adapter is the set of controls that connects the same pilot to a simulator or
to a real aircraft.

## 3. Kubernetes safety boundary

```text
Structured action proposal
          |
          v
Deterministic safety policy
          |  approved actions only
          v
Restricted Kubernetes adapter
          |  fixed namespace + workload + replica bounds
          v
Namespace-scoped RBAC
          |
          v
Allow-listed managed Deployment

Allowed: restart | known-version rollback | scale from 1 to 3
Denied:  shell | exec | create | delete | arbitrary apply | scale to 20
```

### What to say

Each layer narrows authority. The policy approves only evidence-supported
actions. The adapter validates the namespace, workload, managed label, action,
and replica range. Kubernetes RBAC independently limits cluster permissions.
Blocked actions never reach the infrastructure.

### Layman explanation

The responder receives a key to one room and a few approved controls rather
than the master key to the building.

## 4. Adaptive incident timeline

```text
INITIAL INCIDENT
70% errors | 1000 ms latency | one replica
        |
        v
ATTEMPT 1: RESTART
Kubernetes accepts the command and creates a replacement Pod
        |
        v
FRESH VERIFICATION FAILS
60% errors | 750 ms latency | resource-pressure evidence
        |
        v
ATTEMPT 2: SCALE TO 3
Kubernetes creates two additional Pods
        |
        v
FRESH VERIFICATION PASSES
1% errors | 100 ms latency | incident resolved
```

### What to say

The restart succeeds mechanically, but the service remains unhealthy.
IncidentPilot keeps that failure in its attempt history, observes the changed
state, and chooses a different action. The run ends only after fresh service
checks pass.

### Layman explanation

Replacing one worker does not clear the queue, so the system safely adds more
workers and checks the customer experience again.

## 5. Current demo and production extension

```text
CURRENT DEMO

Dashboard + FastAPI
        |
        v
IncidentPilot controller
        |
        v
Local kind cluster
        |
        v
Managed Deployment + Service


POSSIBLE PRODUCTION EXTENSION

Prometheus / Alertmanager / service telemetry
        |
        v
Authenticated IncidentPilot service
        |
        +---- durable incident store and audit history
        |
        +---- human approval for higher-risk actions
        |
        v
Restricted Kubernetes API access
        |
        v
Allow-listed production workloads
```

### What to say

The current implementation proves real Kubernetes observation and bounded
remediation on a local cluster. The production extension is a roadmap, not a
current feature claim. It would add durable storage, authentication, richer
telemetry, multi-service support, distributed coordination, and approval
workflows.

