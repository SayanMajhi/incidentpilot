# IncidentPilot hackathon demo video script

## Recommended format

- Target length: 3 minutes 45 seconds to 4 minutes 15 seconds.
- Record the browser at 1080p with page zoom around 80–90%.
- Keep the mouse still unless the script says to click or point.
- Use simulator mode with the optional LLM disabled. This is the reliable,
  credential-free path and still exercises the real controller, decision
  engine, safety policy, infrastructure adapter, and verifier.
- Do one silent rehearsal before recording. The adaptive run normally needs a
  few seconds because recovery is verified with three fresh telemetry samples.

## Before recording

Start the API from the repository root:

```powershell
$env:ENVIRONMENT='simulator'
$env:LLM_ENABLED='false'
.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Start the dashboard in a second terminal:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:3000`, confirm that the API indicator is connected, and
click **Reset** once. Return to the landing page before beginning the recording.
Turn off notifications and hide personal browser tabs, bookmarks, and terminal
history.

## Narration pattern for every explanation

Use this three-step pattern whenever you explain the project:

```text
What it does -> layman analogy -> technical detail
```

Example opening:

> IncidentPilot is an autonomous incident-response assistant for software
> services. In simple terms, it is like a careful doctor for an application:
> it checks symptoms, chooses a safe treatment, watches whether the patient
> improves, and changes treatment if the first one fails. Technically, it is a
> bounded agent loop built with FastAPI, a deterministic decision engine, a
> safety policy, an infrastructure adapter, and a verifier that reads fresh
> telemetry before declaring recovery.

Use the notes below while recording or presenting live. They are not extra
screen actions; they are short mental cues for explaining each script section.

| Section | What to explain | Layman note | Technical note |
| --- | --- | --- | --- |
| Hook | The project does verified incident recovery, not blind automation. | A mechanic does not say the car is fixed just because one part was replaced; they test-drive it. | Action success and incident recovery are separate states in the backend. |
| Key difference | The system loops when evidence changes. | If medicine does not work, the doctor checks the patient again and changes treatment. | The controller records failed attempts, re-observes, re-investigates, and replans. |
| Dashboard | The UI is only the control panel. | The dashboard is the car dashboard; the engine is the backend. | React polls FastAPI for status, timeline, config, and command results. |
| Healthy run | The agent knows when not to act. | A good doctor does not prescribe medicine to a healthy patient. | No SLO breach means no remediation phase and no infrastructure mutation. |
| Adaptive incident | The scenario hides the full cause at first. | At first it looks like a simple restart problem, but the deeper issue is capacity. | Initial evidence supports restart; fresh post-action telemetry reveals resource pressure. |
| Attempt 1 | Restart succeeds technically but does not recover the service. | The light switch worked, but the room is still dark because the real problem is elsewhere. | Verification fails on fresh samples, so the run is not marked resolved. |
| Attempt 2 | The agent changes strategy based on new evidence. | It learns from the failed treatment and chooses a stronger, still safe treatment. | Failed-attempt history plus new capacity evidence leads to `scale_service` with target 3. |
| Safety test | Unsafe actions are blocked before execution. | The assistant can suggest a strong medicine, but the pharmacist rejects an unsafe dose. | The policy denies scale-to-20 because allowed replicas are 1 through 3, and `executed=false`. |
| Architecture | The system is modular and bounded. | The doctor, safety supervisor, tool operator, and lab tester are separate roles. | Controller, decision engine, safety policy, infrastructure adapter, and verifier are independent modules. |
| Close | The value is safe, auditable recovery. | It gives a clear incident story, not just a magic fix button. | Timeline events, attempts, evidence, policy verdicts, and verification checks create an audit trail. |

## Full shot-by-shot script

### 0:00–0:18 — Hook

**Show:** The landing-page hero. Pause on the animated response lifecycle.

**Say:**

> A remediation command can succeed while the service is still broken. That is
> the gap IncidentPilot solves. It is a bounded autonomous SRE agent that
> investigates an incident, chooses a safe action, executes it, and then checks
> fresh telemetry before it ever claims recovery.

**Layman cue:** "It does not just press a fix button; it checks whether the fix
actually worked."

**Technical cue:** "Bounded agent loop with observe, diagnose, policy-check,
execute, verify, and replan phases."

### 0:18–0:38 — The key difference

**Show:** Slowly scroll to the problem comparison or keep the lifecycle preview
in view as it reaches **Verify**, **Adapt**, and **Recovered**.

**Say:**

> Traditional automation usually ends at “action succeeded.” IncidentPilot is
> a feedback loop: observe, diagnose, plan, pass a policy gate, execute, verify,
> and, when the evidence says the fix failed, replan. Let me show that loop
> rather than just describe it.

**Layman cue:** "Like a doctor checking if the patient improved after medicine."

**Technical cue:** "The backend stores attempt history and reruns diagnosis
after failed verification."

### 0:38–0:52 — Enter the dashboard

**Show:** Click **Launch IncidentPilot**. Briefly point to the connected API,
the `SIMULATOR` environment badge, live service telemetry, and the lifecycle.

**Say:**

> This React dashboard is reading backend-owned state from a FastAPI service.
> For a repeatable demo I am using the deterministic simulator, but the same
> controller also works through a restricted Kubernetes adapter.

**Layman cue:** "The dashboard is the screen; the backend is the brain."

**Technical cue:** "React calls FastAPI endpoints for config, status, timeline,
scenario mutation, safety evaluation, and incident execution."

### 0:52–1:12 — Prove that healthy systems are left alone

**Show:** Click **Reset** and then **Run Incident** while the service is healthy.
Wait for `NO INCIDENT`. Point to the healthy telemetry and lifecycle result.

**Say:**

> First, the safe baseline. The service is healthy: one percent errors, one
> hundred millisecond latency, version forty-one, and one replica. When I run
> the agent, it detects no SLO breach and exits as “no incident.” It performs no
> safety check and no mutation. Autonomy also means knowing when not to act.

**Layman cue:** "A good assistant does not touch a healthy system."

**Technical cue:** "Detection checks health, error rate, and latency against
configured SLO thresholds before planning any remediation."

### 1:12–1:32 — Inject the adaptive incident

**Show:** Click **Adaptive Incident**. Point to the red service state and the
metric cards: 70% error rate, 1000 ms latency, 94% CPU, version v41, one replica.

**Say:**

> Now I will inject the adaptive incident. Error rate jumps to seventy percent,
> p-ninety-nine latency reaches one second, CPU is at ninety-four percent, and
> only one replica is serving traffic. This scenario is designed so the first
> reasonable fix will not be enough.

**Layman cue:** "The system looks sick, but the first symptom does not reveal
the whole disease."

**Technical cue:** "The simulator starts with evidence that supports restart,
then exposes capacity pressure only after fresh post-restart observation."

### 1:32–1:58 — Run the autonomous loop

**Show:** Click **Run Incident**. Move the pointer away. Let the lifecycle and
agent state update. As soon as the run finishes, point to **Recovery verified**
and the `↻ Replanning confirmed by the backend event stream` message.

**Say:**

> One click starts a goal-driven run, and the API returns immediately with a
> run ID. The controller gathers health, metrics, logs, deployment history, and
> capacity evidence. It initially sees a transient service failure, proposes a
> bounded restart, passes the deterministic safety gate, and executes it.
>
> But command success is not recovery. Fresh verification still sees sixty
> percent errors, seven hundred and fifty millisecond latency, and ninety-one
> percent CPU. So the agent records the failed attempt and loops back with new
> evidence.

**Layman cue:** "The first treatment was allowed and performed, but the patient
did not recover, so the doctor checks again."

**Technical cue:** "`restart_service` returns success, but the verifier returns
a non-recovered verdict from fresh telemetry samples."

### 1:58–2:35 — Show the evidence-driven change of strategy

**Show:** Scroll to **Agent Execution Timeline** and **Attempt records**. Open
**Attempt 1**, then click the Inspector's **Decision** tab and **Verify** tab.
Next open **Attempt 2**, click **Decision**, and then **Verify**.

**Say:**

> Attempt one shows the restart was evidence-based and allowed, but verification
> failed. After the restart clears the masked worker failure, the next
> investigation exposes resource pressure. The previous failed action is kept
> in run history, so it is not blindly repeated.
>
> On attempt two, the diagnosis changes to resource exhaustion. The agent
> proposes scaling to three replicas. That target is inside the permitted
> one-to-three range, so the policy allows it. Three fresh samples now pass the
> health, SLO, and readiness checks: one percent errors, one hundred millisecond
> latency, forty-eight percent CPU, and three replicas. Only then is the run
> marked resolved.

**Layman cue:** "Now it changes treatment because it learned the real issue was
not just a stuck process, but too little capacity."

**Technical cue:** "The second decision is driven by evidence IDs such as
resource pressure and previous failed verification, not by the scenario name."

### 2:35–3:00 — Demonstrate the safety boundary

**Show:** Scroll back to **Demo scenarios** and click
**Test Safety Gate: scale to 20**. Point to `BLOCKED`, the rule ID, the allowed
bounds, and `Infrastructure executed: NO`.

**Say:**

> Autonomy is bounded, not unlimited. This challenge asks for twenty replicas.
> The policy rejects it because the maximum is three, records the exact rule and
> reason, and reports that infrastructure execution is false. The agent has no
> arbitrary shell, apply, create, delete, or database tool. Only allow-listed
> restart, rollback, and scale operations can cross this boundary.

**Layman cue:** "The system can help, but it cannot do anything outside the
rules."

**Technical cue:** "Safety is deny-by-default, checks replica bounds and
targets, and blocks before the infrastructure adapter is called."

### 3:00–3:27 — Explain the architecture

**Show:** Keep the dashboard visible. Point in order to live telemetry, the
lifecycle, the backend audit trail, and the Inspector tabs.

**Say:**

> Under the hood, FastAPI owns one revisioned incident run and an immutable,
> timestamped audit trail. The controller separates diagnosis, policy,
> execution, and verification. An infrastructure interface connects either the
> simulator or a narrowly scoped Kubernetes gateway. If a model is enabled, it
> may propose a structured action, but it cannot execute tools; its proposal is
> schema-validated, checked against deterministic evidence, and still passes
> through the same policy gate.

**Layman cue:** "Different people have different jobs: one diagnoses, one
checks safety, one performs the action, one confirms recovery."

**Technical cue:** "The controller depends on an infrastructure interface, so
the same loop can run against simulator or Kubernetes."

### 3:27–3:52 — Close with the value

**Show:** Finish on the resolved state, the green telemetry, or the landing
page's final call to action.

**Say:**

> IncidentPilot turns incident response from a one-shot runbook into a safe,
> observable recovery loop. It acts only within explicit limits, learns from a
> failed attempt, proves recovery with fresh evidence, and escalates to a human
> after three unsuccessful remediations. The result is not just automation that
> ran. It is recovery we can verify.

**Layman cue:** "The final output is a trustworthy recovery story."

**Technical cue:** "The audit trail contains timeline events, attempts,
evidence, policy decisions, action results, and verification checks."

## Ninety-second backup version

Use this if the submission platform has a strict short-video limit.

### 0:00–0:12

**Show:** Landing hero.

> A successful remediation command does not prove a service recovered.
> IncidentPilot is a bounded autonomous SRE agent that acts, verifies fresh
> telemetry, and replans when the first fix fails.

### 0:12–0:25

**Show:** Launch the dashboard and click **Adaptive Incident**.

> This deterministic scenario starts at seventy percent errors, one-second
> latency, ninety-four percent CPU, and one replica.

### 0:25–0:48

**Show:** Click **Run Incident** and let it finish.

> The agent diagnoses a transient failure, safely restarts the service, but
> verification still fails. New resource-pressure evidence appears, so the
> controller retains the failed attempt and changes strategy instead of
> repeating it.

### 0:48–1:05

**Show:** Open attempt 1 and attempt 2; show **Decision** and **Verify**.

> Attempt two safely scales to three replicas. Three fresh telemetry samples
> pass, and only then does the agent declare the run resolved.

### 1:05–1:20

**Show:** Click **Test Safety Gate: scale to 20**.

> A request for twenty replicas is denied by policy and never reaches
> infrastructure. Models may propose actions, but deterministic policy controls
> execution.

### 1:20–1:30

**Show:** Resolved state.

> IncidentPilot does not merely automate a command. It delivers bounded,
> auditable, verified recovery.

## Recording and delivery notes

- Begin with the problem, not team introductions. Put names and the hackathon
  logo on a two-second title card if the rules require them.
- Do not narrate every dashboard card. Focus on the failed verification,
  replanning event, changed action, safety rejection, and verified outcome.
- Pause after important clicks. Judges need enough time to read `FAILED`,
  `BLOCKED`, and `RESOLVED`.
- Avoid claiming that the LLM controls infrastructure. It is optional and
  advisory; the policy and adapter enforce the real execution boundary.
- Avoid calling the simulator “fake.” Call it a deterministic infrastructure
  adapter built for a repeatable, credential-free demonstration. Mention the
  Kubernetes adapter when discussing production direction.
- If a live click fails, do not troubleshoot on camera. Cut, reset, and record
  that section again.
- Add captions. Highlight the exact values with a subtle zoom or cursor circle,
  not large animated overlays.
- End on the product value, not on implementation details.

## Technical judge-question monologues

Use these when a judge asks a deeper question, or weave one or two into the
presentation if you have extra time. Each answer follows the same pattern:
direct answer, layman explanation, then technical detail.

### 1. What exactly does this project do?

**Narrate:**

> IncidentPilot is an autonomous incident-response agent for software services.
> In simple terms, when an app is unhealthy, it behaves like a careful on-call
> engineer: it checks symptoms, finds evidence, chooses a safe fix, performs
> only approved actions, and then verifies that the service actually recovered.
> Technically, it is a FastAPI-backed agent loop with deterministic diagnosis,
> a safety policy, simulator and Kubernetes infrastructure adapters, and a
> verification engine that uses fresh telemetry before marking the incident
> resolved.

**Layman note:** "It is an on-call helper that fixes only within rules and then
checks its own work."

**Technical note:** "Mention FastAPI, controller loop, policy gate, adapter,
and verifier."

### 2. How is this different from a normal automation script?

**Narrate:**

> A script usually follows a fixed sequence: if X happens, run Y. IncidentPilot
> is different because it keeps state, records attempts, verifies outcomes, and
> changes strategy when the first action does not recover the service. The
> adaptive demo proves this: restart succeeds, but verification fails, so the
> agent does not claim success. It collects fresh evidence and then scales the
> service safely.

**Layman note:** "A script is a checklist; this is closer to a junior SRE who
checks whether the checklist actually solved the problem."

**Technical note:** "Mention attempt history, fresh observations, failed
verification, and replanning."

### 3. Is the adaptive demo hard-coded?

**Narrate:**

> The simulator is deterministic so the demo is repeatable, but the controller
> does not inspect the scenario name. It reads metrics, health, logs, deployment
> history, capacity, and previous attempt results. The first evidence supports
> restart. After restart, the environment changes and new evidence reveals
> resource pressure. That new evidence drives the second decision.

**Layman note:** "The test environment is controlled, but the agent still has
to read clues and respond to what it sees."

**Technical note:** "Mention that decisions are based on evidence IDs and
telemetry, not `adaptive_incident` string checks."

### 4. Where is the AI or agentic behavior?

**Narrate:**

> The agentic part is the closed feedback loop: it has a goal, observes the
> environment, selects tools, receives results, verifies outcomes, and replans
> within an attempt budget. There is also optional LLM support, but I made it
> advisory on purpose. A model may propose an action, but deterministic
> validation and safety policy decide whether anything can execute.

**Layman note:** "The AI can suggest, but it cannot grab the steering wheel
without passing the safety checks."

**Technical note:** "Mention bounded loop, tool use, persistent run state,
schema validation, deterministic arbitration, and policy enforcement."

### 5. What prevents this from doing something dangerous?

**Narrate:**

> The project is built around bounded autonomy. It has a deny-by-default safety
> policy. Only three remediation actions are allowed: restart, rollback to a
> known version, and scale within a safe range. The dashboard safety test asks
> for twenty replicas, and the policy blocks it before infrastructure execution.
> In Kubernetes mode, the gateway also restricts namespace, workload, and write
> operations.

**Layman note:** "It has a rulebook and a locked toolbox."

**Technical note:** "Mention allow-listed actions, namespace/workload checks,
replica bounds 1 through 3, max attempts, and no shell/apply/delete tool."

### 6. How do you know the fix really worked?

**Narrate:**

> IncidentPilot separates command success from service recovery. A restart or
> scale operation can succeed mechanically, but the service might still be
> unhealthy. After every action, the verifier collects fresh samples and checks
> health, error rate, latency, and readiness. Only if those checks pass does the
> run become resolved.

**Layman note:** "Replacing a part is not the same as proving the machine runs."

**Technical note:** "Mention verification samples, SLO checks, readiness, and
the `recovered`, `partial`, or `failed` verdict."

### 7. Why did you include both simulator and Kubernetes modes?

**Narrate:**

> The simulator makes the hackathon demo reliable and credential-free, while
> the Kubernetes adapter shows the same architecture can talk to real
> infrastructure. Both implement the same infrastructure interface, so the
> controller logic does not need to change. That separation makes the system
> easier to test, safer to demo, and more realistic for future deployment.

**Layman note:** "The same driver can practice in a simulator and then drive on
a closed test track."

**Technical note:** "Mention infrastructure abstraction, simulator adapter,
restricted Kubernetes adapter, and local-cluster demo mode."

### 8. What happens if the agent cannot fix the problem?

**Narrate:**

> It does not loop forever. Automatic remediation is capped by an attempt
> budget. If actions fail, verification is inconclusive, or no safe action is
> supported by evidence, the agent records the evidence and escalates. That is
> important because safe autonomy should know when to stop and hand off to a
> human.

**Layman note:** "It tries a few safe treatments, then calls a senior doctor."

**Technical note:** "Mention max remediation attempts, terminal statuses like
`ESCALATED` or `BLOCKED`, and audit trail preservation."

### 9. How is the system observable for debugging or audit?

**Narrate:**

> Every meaningful backend transition becomes a timeline event: observation,
> detection, investigation, diagnosis, planning, safety check, execution,
> verification, replanning, and final status. The dashboard displays those
> events along with attempt records, decisions, policy verdicts, action results,
> verification checks, logs, and metrics. So the demo is not a black box.

**Layman note:** "It writes a clear incident diary."

**Technical note:** "Mention revisioned runtime state, immutable timeline
events, attempt records, and Inspector tabs."

### 10. Why is the LLM optional instead of required?

**Narrate:**

> For this project, reliability and safety matter more than making the model
> look magical. Deterministic mode is complete and reproducible. If the LLM is
> enabled, it can propose a structured decision, but the system validates the
> schema, compares it against deterministic evidence, corrects unsafe targets,
> and still routes it through the same policy gate.

**Layman note:** "The model is an advisor, not the final authority."

**Technical note:** "Mention deterministic fallback, arbitration, schema
validation, and policy-controlled execution."

### 11. How would you extend this for production?

**Narrate:**

> The next production steps would be durable storage for incident state,
> multi-service support, stronger observability integrations like Prometheus,
> approval workflows for higher-risk actions, and richer Kubernetes telemetry.
> The core design already prepares for that because the controller is separated
> from infrastructure, and actions are already bounded by policy.

**Layman note:** "The prototype is a safe training version; production would
add memory, more sensors, and approval controls."

**Technical note:** "Mention durable persistence, Prometheus, multi-workload
configuration, human approval, and expanded adapters."

### 12. What is the strongest technical part of this project?

**Narrate:**

> The strongest part is that it proves recovery through feedback, not through
> wishful execution. The adaptive scenario forces the agent to experience a
> successful command that still fails verification. That is where the project
> becomes more than a dashboard: it demonstrates evidence-driven replanning
> under safety constraints.

**Layman note:** "It learns from a failed fix instead of pretending the first
button solved everything."

**Technical note:** "Mention successful action with failed verification,
re-observation, new evidence, changed diagnosis, safe scaling, and verified
resolution."

## Optional 60-second real Kubernetes proof

Use this after the reliable simulator demo. Do not install a large third-party
demo application: the repository already contains a small deterministic HTTP
workload that represents a real service such as a checkout, payment, or order
API. It runs as a genuine Kubernetes Deployment and Service, so the restart,
new Pods, replica scaling, and recovery are real Kubernetes operations.

### Prepare before recording

Start Docker Desktop, then run these commands once from the repository root:

```powershell
.\scripts\check-k8s-demo.ps1
.\scripts\setup-k8s-demo.ps1
```

Open four terminals for the presentation:

```powershell
# Terminal 1 - backend connected to Kubernetes
$env:ENVIRONMENT = 'kubernetes'
$env:LLM_ENABLED = 'false'
.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2 - dashboard
cd frontend
npm run dev
```

```powershell
# Terminal 3 - visible proof of real cluster changes
kubectl -n incidentpilot get deployment,pods -w
```

```powershell
# Terminal 4 - inject only the failure; use the dashboard to run the agent
.\scripts\run-k8s-demo.ps1 -Scenario adaptive-resource-pressure -ScenarioOnly
```

Then open `http://localhost:3000` and click **Run Incident**.

### What to show and say

**0:00-0:12 - Establish that this is real Kubernetes**

**Show:** The dashboard reports `environment: kubernetes`. Briefly show the
terminal running `kubectl get deployment,pods -w` with one Pod.

**Say:**

> The first demo proved the agent's logic reliably in a simulator. Now the
> same controller is connected through its infrastructure interface to a real
> local Kubernetes cluster. This small service represents a production API
> such as checkout or payments.

**Layman cue:** "I have moved the same driver from the simulator onto a closed
test track."

**Technical cue:** "FastAPI is local, but the workload is a real Deployment
and Service inside kind; the adapter communicates through the Kubernetes API."

**0:12-0:42 - Run the adaptive recovery**

**Show:** Click **Run Incident**. Keep the dashboard and `kubectl` terminal
visible. Point out the replacement Pod after restart, failed verification,
then the Deployment growing from one replica to three.

**Say:**

> The workload returns application-level 503 errors. IncidentPilot first
> performs a bounded rollout restart. Kubernetes accepts the command and
> creates a replacement Pod, but fresh verification still fails. New logs show
> resource pressure, so the agent replans and scales the Deployment to three
> replicas. Kubernetes creates two additional Pods, and only after fresh HTTP
> probes pass does IncidentPilot mark the incident resolved.

**Layman cue:** "Replacing one worker did not fix the queue, so the system
verified the result and safely added more workers."

**Technical cue:** "Point to action success versus verification failure,
rollout reconciliation, evidence-driven replanning, the scale subresource, and
three ready replicas."

**0:42-1:00 - Explain the production safety story**

**Show:** The resolved timeline, three ready Pods, and—if time permits—the
safety-gate result that rejects scaling to 20.

**Say:**

> This is how the idea maps to a real-world service, but with strict blast-
> radius controls. IncidentPilot can touch only the `incidentpilot` namespace,
> one allow-listed and explicitly managed Deployment, and three fixed action
> types. Scaling is capped at three replicas, Kubernetes RBAC adds another
> permission boundary, and there is no shell, delete, create, or arbitrary
> apply capability.

**Layman cue:** "The responder receives a key to one room and only three safe
buttons, not the master key to the building."

**Technical cue:** "Mention namespace and workload allow-lists, the managed
label, least-privilege RBAC, replica bounds, and defense in depth."

### Honest production framing

Say **"real Kubernetes integration"**, not **"production-ready platform."**
The current implementation proves real observation, restart, rollback, scale,
reconciliation, and verification on a local cluster. A production version
would add durable state, authentication, multi-service configuration,
Prometheus or OpenTelemetry, alert-manager integration, distributed locking,
and human approval for higher-risk actions.

If Docker or the cluster is unreliable on presentation day, show a prerecorded
clip of this Kubernetes segment and run the main simulator demo live. The
technical claim remains accurate while the critical presentation path stays
deterministic.

## Likely judge questions

**Is this a hard-coded script?**

No. The simulator makes the environment deterministic, but the controller does
not inspect the scenario name. The first decision follows the initially visible
evidence. After verification fails, fresh diagnostics expose resource pressure,
and failed-attempt history prevents the same ineffective action from being
repeated.

**Where is the AI?**

IncidentPilot is an agentic control loop with a goal, persistent state, tools,
feedback, bounded attempts, and replanning. It also supports an optional Qwen
proposal engine. Model output is advisory: it is schema-validated, compared
with deterministic evidence, and must pass the same safety policy before any
tool can execute. The recommended demo keeps the model off so network and
provider availability cannot affect judging.

**What prevents dangerous actions?**

The deny-by-default policy permits only restart, rollback to a known version,
and scaling from one to three replicas, all for an allow-listed namespace and
workload. The Kubernetes gateway independently exposes only those narrow
operations and has no generic shell or resource deletion method.

**How do you know the incident recovered?**

Action results and recovery results are separate. After every mutation, the
verifier collects fresh samples and evaluates named health, SLO, and readiness
checks. A successful command with failing telemetry causes replanning, not a
resolved status.

**What happens if nothing works?**

Automatic remediation is capped at three attempts. If recovery is still not
verified, IncidentPilot records the final evidence and escalates for human
handoff instead of looping forever.

**Can it work outside the simulator?**

Yes. The controller depends on an infrastructure interface. The repository
includes a restricted Kubernetes adapter and repeatable local-cluster
scenarios; simulator mode is used in the video because it is faster and fully
reproducible.
