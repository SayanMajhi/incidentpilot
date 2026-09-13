import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from '../services/api';
import type {
  AgentRunState, Attempt, BackendAttempt, IncidentStatus, IncidentStatusResponse,
  IncidentSummary, DecisionDetails, LogEntry, ResolutionBanner, RuntimeConfig,
  SafetyState, ScenarioId, ServiceState, TelemetryPoint, TimelineResponse, VerificationState,
} from '../types/incidentPilot';
import { SCENARIO_LABELS } from '../types/incidentPilot';

const MAX_SAMPLES = 40;
const POLL_INTERVAL_MS = 2_000;

/** Used until `GET /config` answers, then replaced by the backend's own values.
 *  Never treated as authoritative: the backend owns these numbers. */
const FALLBACK_CONFIG: RuntimeConfig = {
  recovery: { max_error_rate: 0.05, max_latency_ms: 200 },
  elevated: { error_rate: 0.1, latency_ms: 300 },
  replicas: { min: 1, max: 3 },
  baseline: { error_rate: 0.01, latency_ms: 100, version: 'v41' },
  chart: { latency_ceiling_ms: 1200 },
  bad_deployment_version: 'v42',
};

/** Human-readable labels for the phases the controller emits via `/status`. */
const PHASE_LABELS: Record<string, string> = {
  idle: 'Idle',
  observing: 'Observing live state…',
  investigating: 'Investigating evidence…',
  diagnosing: 'Diagnosing probable cause…',
  deciding: 'Selecting a remediation…',
  checking_safety: 'Awaiting safety policy…',
  executing: 'Executing remediation…',
  remediating: 'Executing remediation…',
  verifying: 'Verifying recovery…',
  adapting: 'Adapting after failed verification…',
  complete: 'Complete',
  failed: 'Run failed',
};

const DEFAULT_GOAL = 'Restore the service to configured SLOs while respecting safety constraints.';
const emptySummary: IncidentSummary = { scenario: 'None', agentStatus: 'Idle', attempts: '0', finalAction: 'None', finalVerification: 'Pending', finalOutcome: 'None', diagnosis: 'None', evidence: 'None' };
const emptyDecision: DecisionDetails = { source: 'none', action: 'None', target: 'None', confidence: '0%', reason: 'None', aiSuggestion: 'Not used', validation: 'Deterministic mode', validationReason: 'No model proposal was requested.' };
const emptySafety: SafetyState = { status: 'UNCHECKED', action: 'None', verdict: 'Pending', reason: 'Awaiting check' };
const emptyVerification: VerificationState = { status: 'UNVERIFIED', recovered: 'Pending', isRecoveredBool: null, reason: 'Pending', errorRate: '-', latency: '-', serviceStatus: '-', metricsBefore: '-', metricsAfter: '-' };
const idleAgent: AgentRunState = { run_id: null, goal: DEFAULT_GOAL, started_at: null, running: false, status: 'idle', phase: 'idle', attempt: 0, max_attempts: 3, history: [], reason: null, updated_at: null, details: {} };

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

function scenarioLabel(scenario: string): string {
  return SCENARIO_LABELS[scenario as ScenarioId] || titleCase(scenario);
}

function phaseLabel(agent: AgentRunState): string {
  const label = PHASE_LABELS[agent.phase] || titleCase(agent.phase);
  return agent.running && agent.attempt > 0 ? `${label} (attempt ${agent.attempt})` : label;
}

function formatTarget(target: string | number | null): string {
  if (target === null || target === undefined) return 'None';
  return typeof target === 'number' ? `${target} replicas` : String(target);
}

function formatMetricPercent(value: number | null | undefined): string {
  return typeof value === 'number' ? `${value.toFixed(0)}%` : 'unavailable';
}

function actionLabel(action: string, target: string | number | null, currentReplicas: number): string {
  if (action === 'restart_service') return 'Restart deployment';
  if (action === 'rollback_deployment') return `Rollback deployment → ${formatTarget(target)}`;
  if (action === 'scale_service') return `Scale ${currentReplicas} → ${target}`;
  return titleCase(action);
}

function mapDecision(decision: BackendAttempt['decision']): DecisionDetails {
  const proposal = decision.llm_proposal;
  if (decision.source === 'llm') {
    return {
      source: 'Qwen-assisted',
      action: decision.action,
      target: formatTarget(decision.target),
      confidence: `${(decision.confidence * 100).toFixed(0)}%`,
      reason: decision.reason,
      aiSuggestion: `${actionLabel(decision.action, decision.target, 1)} (${(decision.confidence * 100).toFixed(0)}%)`,
      validation: 'ACCEPTED',
      validationReason: 'The proposal matched the deterministic evidence and passed schema validation.',
    };
  }
  return {
    source: decision.source || 'deterministic',
    action: decision.action,
    target: formatTarget(decision.target),
    confidence: `${(decision.confidence * 100).toFixed(0)}%`,
    reason: decision.reason,
    aiSuggestion: proposal ? `${actionLabel(proposal.action, proposal.target, 1)} (${(proposal.confidence * 100).toFixed(0)}%)` : 'Not used',
    validation: proposal ? 'REJECTED' : 'Deterministic mode',
    validationReason: decision.arbitration_reason || decision.fallback_reason || 'No model proposal was requested.',
  };
}

function mapAttempt(attempt: BackendAttempt, index: number, total: number, scenario: string): Attempt {
  const { observations, detection, diagnosis, decision, safety_result, action_result, verification } = attempt;
  const metrics = observations.metrics;
  const capacity = observations.capacity;
  const after = verification?.metrics_after || verification?.telemetry?.metrics;
  const afterCapacity = verification?.telemetry?.capacity;
  const signals = detection.signals.length ? detection.signals.map(titleCase).join(', ') : 'No SLO breaches';
  const evidence = attempt.evidence || observations.evidence || [];
  const evidenceSummary = evidence.length
    ? evidence.slice(0, 3).map((item) => item.detail).join(' ')
    : 'No causal evidence was found.';
  const selectedAction = actionLabel(decision.action, decision.target, capacity.replicas);
  const steps: Attempt['steps'] = [
    { type: 'obs', label: 'OBSERVE · SLO breach detected', details: `CPU ${formatMetricPercent(metrics.cpu_percent)} · Error rate ${(metrics.error_rate * 100).toFixed(1)}% · Latency ${metrics.latency_ms}ms · Replicas ${capacity.replicas}${capacity.ready_replicas != null ? ` (${capacity.ready_replicas} ready)` : ''}. Signals: ${signals}.` },
    { type: 'inv', label: 'INVESTIGATE · Evidence collected', details: `${evidenceSummary} Queried ${observations.logs.length} logs, current workload state, and deployment history.` },
    { type: 'diag', label: 'Diagnose', details: `${titleCase(diagnosis.probable_cause)} — ${diagnosis.summary}` },
    { type: 'dec', label: 'DECIDE', details: `${selectedAction} · ${(decision.confidence * 100).toFixed(0)}% confidence · ${decision.source || 'deterministic'}. ${decision.reason}` },
    { type: 'safe', label: `SAFETY · ${safety_result.checked ? (safety_result.allowed ? 'APPROVED' : 'BLOCKED') : 'NOT REQUIRED'}`, details: safety_result.checked ? `Deterministic policy checked ${decision.action}; allowed range is 1–3 replicas and only bounded remediations are permitted.` : 'No remediation was proposed, so no mutation was authorized.', customClass: safety_result.allowed === false ? 'verification-failure' : 'safety-approved' },
    { type: 'act', label: action_result.action === 'escalate' ? 'ESCALATED' : 'ACTION', details: `${action_result.success ? '✓ Command succeeded.' : '✗ Command failed.'} ${action_result.message}`, customClass: action_result.success ? 'execution-success' : 'verification-failure' },
  ];
  if (verification) {
    steps.push({ type: 'ver', label: 'VERIFY · Fresh telemetry', details: `CPU ${formatMetricPercent(after?.cpu_percent)} · Error rate ${after ? `${(after.error_rate * 100).toFixed(1)}%` : 'unavailable'} · Latency ${after ? `${after.latency_ms}ms` : 'unavailable'} · Replicas ${afterCapacity?.replicas ?? after?.replicas ?? capacity.replicas}${afterCapacity?.ready_replicas != null ? `/${afterCapacity.replicas} ready` : ''}.` });
    steps.push({ type: 'result', label: `RESULT · ${verification.recovered ? 'PASSED' : 'FAILED'}`, details: verification.recovered ? `✓ ${verification.reason}. Incident recovery is verified.` : `✗ ${verification.reason}. The command succeeded, but the SLO is still violated.`, customClass: verification.recovered ? 'verification-success' : 'verification-failure' });
    if (!verification.recovered && index < total - 1) {
      const freshEvidence = attempt.new_evidence_after_action?.map(titleCase).join(', ') || 'new post-action evidence';
      steps.push({ type: 'adapt', label: 'ADAPT · Re-investigate', details: `Verification rejected false success. The controller fetched fresh state and discovered ${freshEvidence}; the next action must follow that evidence.`, customClass: 'adapt-callout' });
    }
  }
  const succeeded = verification?.recovered === true;
  const statusText = succeeded ? 'RECOVERED' : verification ? 'VERIFICATION FAILED' : action_result.status.toUpperCase();
  const mappedDecision = mapDecision(decision);
  const mappedVerification: VerificationState = verification ? {
    status: verification.recovered ? 'VERIFIED' : 'FAILED',
    recovered: verification.recovered ? 'YES' : 'NO',
    isRecoveredBool: verification.recovered,
    reason: verification.reason,
    errorRate: after ? `${(after.error_rate * 100).toFixed(1)}%` : 'unavailable',
    latency: after ? `${after.latency_ms}ms` : 'unavailable',
    serviceStatus: after?.status?.toUpperCase() || 'UNKNOWN',
    metricsBefore: verification.metrics_before ? `${(verification.metrics_before.error_rate * 100).toFixed(1)}% errors · ${verification.metrics_before.latency_ms}ms · ${verification.metrics_before.status}` : 'unavailable',
    metricsAfter: after ? `${(after.error_rate * 100).toFixed(1)}% errors · ${after.latency_ms}ms · ${after.status}` : 'unavailable',
  } : { ...emptyVerification, status: 'NOT RUN', reason: action_result.message };
  const mappedSafety: SafetyState = {
    status: safety_result.checked ? (safety_result.allowed ? 'ALLOWED' : 'BLOCKED') : 'NOT REQUIRED',
    action: safety_result.action,
    verdict: safety_result.checked ? (safety_result.allowed ? 'ALLOWED' : 'BLOCKED') : 'SKIPPED',
    reason: action_result.message,
  };
  return {
    id: `attempt-${attempt.attempt}`, number: attempt.attempt, tag: `ATTEMPT ${attempt.attempt}`,
    statusText, statusClass: succeeded ? 'success' : 'retry', steps,
    inspector: {
      summary: {
        scenario: scenarioLabel(scenario), agentStatus: statusText, attempts: `${attempt.attempt} of ${total}`,
        finalAction: decision.action, finalVerification: verification ? (succeeded ? 'Recovered' : 'Failed') : 'Not run',
        finalOutcome: statusText, diagnosis: `${titleCase(diagnosis.probable_cause)} — ${diagnosis.summary}`,
        evidence: evidence.length ? evidence.map((item) => `${item.id}: ${item.detail}`).join(' ') : 'No causal evidence was found.',
      },
      decision: mappedDecision,
      safety: mappedSafety,
      verification: mappedVerification,
      logs: mapLogs(observations.logs),
    },
  };
}

function mapLogs(entries: IncidentStatusResponse['diagnostics']['logs']): LogEntry[] {
  return entries.map((entry, index) => ({
    id: `${entry.timestamp}-${index}`,
    time: entry.timestamp.includes('T') ? entry.timestamp.slice(11, 19) : entry.timestamp,
    level: entry.level === 'ERROR' ? 'ERROR' : entry.level === 'WARNING' ? 'WARNING' : 'INFO',
    message: entry.message,
  }));
}

export function useIncidentPilot(initialBaseUrl = api.DEFAULT_BASE_URL) {
  const [backendUrl, setBackendUrlState] = useState(() => api.normalizeBaseUrl(initialBaseUrl));
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'offline' | 'checking'>('checking');
  const [config, setConfig] = useState<RuntimeConfig>(FALLBACK_CONFIG);
  const [simState, setSimState] = useState<ServiceState>({ status: 'unknown', error_rate: 0, latency_ms: 0, current_version: '—' });
  const [currentReplicas, setCurrentReplicas] = useState(0);
  const [lastSyncTime, setLastSyncTime] = useState('Connecting to live API…');
  const [activeScenario, setActiveScenario] = useState('None');
  const [agent, setAgent] = useState<AgentRunState>(idleAgent);
  const [pendingOperation, setPendingOperation] = useState(false);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [summary, setSummary] = useState(emptySummary);
  const [decision, setDecision] = useState(emptyDecision);
  const [safety, setSafety] = useState(emptySafety);
  const [verification, setVerification] = useState(emptyVerification);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [resolutionBanner, setResolutionBanner] = useState<ResolutionBanner>({ visible: false, text: '', isResolved: false });
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [telemetryBuffer, setTelemetryBuffer] = useState<TelemetryPoint[]>([]);

  /** Aborts every in-flight request when the dashboard unmounts, so no
   *  response can resolve into setState on a torn-down tree. */
  const lifetimeRef = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    lifetimeRef.current = controller;
    return () => controller.abort();
  }, []);

  /** Monotonic token so a slow response can never overwrite a newer one. */
  const syncTokenRef = useRef(0);

  const setBackendUrl = useCallback((url: string) => {
    setBackendUrlState(api.normalizeBaseUrl(url));
  }, []);

  const applyIncident = useCallback((
    timeline: TimelineResponse,
    scenario: string,
    agentState: AgentRunState,
  ) => {
    const label = scenarioLabel(scenario);
    const backendAttempts = timeline.timeline;
    const finalAttempt = backendAttempts[backendAttempts.length - 1];

    if (!finalAttempt) {
      setSummary({ ...emptySummary, scenario: label, agentStatus: phaseLabel(agentState) });
      setDecision(emptyDecision);
      setSafety(emptySafety);
      setVerification(emptyVerification);
      setAttempts([]);
      setResolutionBanner({ visible: false, text: '', isResolved: false });
      return;
    }

    const status = timeline.status as IncidentStatus;
    const recovered = status === 'resolved';
    const finalVerification = finalAttempt.verification;
    const mappedAttempts = backendAttempts.map((attempt, index) => mapAttempt(attempt, index, backendAttempts.length, scenario));
    const finalInspector = mappedAttempts[mappedAttempts.length - 1].inspector;

    setSummary({
      scenario: label,
      // While a run is in flight the live phase is more informative than the
      // previous run's outcome, so the backend's phase wins.
      agentStatus: agentState.running ? phaseLabel(agentState) : titleCase(status),
      attempts: String(backendAttempts.length),
      finalAction: finalAttempt.decision.action,
      finalVerification: finalVerification ? (finalVerification.recovered ? 'Recovered' : 'Failed') : 'Not run',
      finalOutcome: agentState.running ? 'Running' : status.toUpperCase(),
      diagnosis: finalInspector.summary.diagnosis,
      evidence: finalInspector.summary.evidence,
    });

    setDecision(finalInspector.decision);
    setSafety(finalInspector.safety);
    setVerification(finalInspector.verification);
    setAttempts(mappedAttempts);
    setResolutionBanner({
      visible: !agentState.running,
      text: recovered ? 'INCIDENT RECOVERED — VERIFIED AGAINST LIVE TELEMETRY' : status === 'escalated' ? `INCIDENT ESCALATED — ${timeline.reason || 'Human investigation required'}` : `INCIDENT ${status.toUpperCase()}`,
      isResolved: recovered,
    });
  }, []);

  const sync = useCallback(async (url = backendUrl, reportErrors = false) => {
    const token = ++syncTokenRef.current;
    const signal = lifetimeRef.current?.signal;

    try {
      const [status, timeline] = await Promise.all([
        api.fetchStatus(url, signal),
        api.fetchTimeline(url, signal),
      ]);

      // A newer sync already landed, or we unmounted: drop this response.
      if (token !== syncTokenRef.current || signal?.aborted) return null;

      setConnectionStatus('connected');
      setSimState(status.service);
      setCurrentReplicas(status.replicas);
      setActiveScenario(scenarioLabel(status.scenario));
      setAgent(status.agent);
      setLogs(mapLogs(status.diagnostics.logs));
      setLastSyncTime(`Live API · ${new Date().toLocaleTimeString()}`);
      applyIncident(timeline, status.scenario, status.agent);
      setOperationError(null);
      return status;
    } catch (error) {
      if (token !== syncTokenRef.current || signal?.aborted) return null;
      setConnectionStatus('offline');
      setAgent(idleAgent);
      // The last real telemetry is deliberately kept on screen and marked
      // stale rather than replaced with invented values.
      setLastSyncTime('Stale · API unavailable');
      if (reportErrors) setOperationError(error instanceof Error ? error.message : 'Backend request failed.');
      return null;
    }
  }, [backendUrl, applyIncident]);

  const checkConnection = useCallback(async (customUrl?: string) => {
    const url = api.normalizeBaseUrl(customUrl || backendUrl);
    setConnectionStatus('checking');
    return Boolean(await sync(url, true));
  }, [backendUrl, sync]);

  /** Wraps a mutation so exactly one is ever in flight and the UI resyncs
   *  from the backend afterwards, success or failure. */
  const runOperation = useCallback(async (
    operation: (signal?: AbortSignal) => Promise<unknown>,
    failureMessage: string,
  ) => {
    if (pendingOperation) return;
    setPendingOperation(true);
    setOperationError(null);
    try {
      await operation(lifetimeRef.current?.signal);
      await sync(backendUrl, true);
    } catch (error) {
      if (lifetimeRef.current?.signal.aborted) return;
      setOperationError(error instanceof Error ? error.message : failureMessage);
      await sync(backendUrl);
    } finally {
      setPendingOperation(false);
    }
  }, [backendUrl, pendingOperation, sync]);

  const triggerScenario = useCallback((scenario: ScenarioId) => runOperation(async (signal) => {
    await api.resetIncident(backendUrl, signal);
    if (scenario === 'generic_outage') await api.simulateOutage(backendUrl, signal);
    else if (scenario === 'bad_deployment') await api.simulateBadDeployment(backendUrl, signal);
    else if (scenario === 'adaptive_incident') await api.simulateAdaptiveIncident(backendUrl, signal);
    // 'healthy' is the reset baseline, so no injection is required.
  }, 'Could not activate scenario.'), [backendUrl, runOperation]);

  const resetSystem = useCallback(
    () => runOperation((signal) => api.resetIncident(backendUrl, signal), 'Reset failed.'),
    [backendUrl, runOperation],
  );

  const runIncident = useCallback(
    () => runOperation((signal) => api.runIncident(backendUrl, signal), 'Incident run failed.'),
    [backendUrl, runOperation],
  );

  // Load the backend's thresholds once per target, so the dashboard shows the
  // numbers the agent and the safety policy actually enforce.
  useEffect(() => {
    let active = true;
    api.fetchConfig(backendUrl, lifetimeRef.current?.signal)
      .then((next) => { if (active) setConfig(next); })
      .catch(() => { /* Keep the fallback; `sync` surfaces connection errors. */ });
    return () => { active = false; };
  }, [backendUrl]);

  // Poll `/status` + `/timeline` so the dashboard reflects the backend even
  // when a run was started elsewhere or the page was reloaded mid-run.
  useEffect(() => {
    void checkConnection();
    const poll = window.setInterval(() => { void sync(backendUrl); }, POLL_INTERVAL_MS);
    return () => window.clearInterval(poll);
    // `checkConnection` is intentionally omitted: it changes whenever `sync`
    // does, and re-running the initial check on every poll is not wanted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendUrl, sync]);

  // Append a telemetry sample only when the values actually changed.
  useEffect(() => {
    if (simState.status === 'unknown') return;
    setTelemetryBuffer((previous) => {
      const last = previous[previous.length - 1];
      if (last && last.errorRate === simState.error_rate && last.latency === simState.latency_ms && last.status === simState.status) {
        return previous;
      }
      return [...previous.slice(-(MAX_SAMPLES - 1)), { errorRate: simState.error_rate, latency: simState.latency_ms, status: simState.status }];
    });
  }, [simState.status, simState.error_rate, simState.latency_ms]);

  // The agent is busy if this client started something OR the backend says a
  // run is in progress — the latter covers reloads and other clients.
  const isRunningAgent = pendingOperation || agent.running;
  const runLabel = useMemo(() => (isRunningAgent ? 'Agent running…' : 'Run Incident'), [isRunningAgent]);

  return {
    backendUrl, setBackendUrl, connectionStatus, checkConnection, config,
    simState, currentReplicas, lastSyncTime, isLiveSync: connectionStatus === 'connected',
    activeScenario, triggerScenario, resetSystem, runIncident,
    agent, agentPhase: phaseLabel(agent), isRunningAgent, runLabel,
    summary, decision, safety, verification, attempts, resolutionBanner,
    telemetryBuffer, maxSamples: MAX_SAMPLES, logs, operationError,
  };
}
