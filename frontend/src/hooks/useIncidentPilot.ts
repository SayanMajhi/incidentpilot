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
  replicas: { min: 1, max: 5 },
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

const emptySummary: IncidentSummary = { scenario: 'None', agentStatus: 'Idle', attempts: '0', finalAction: 'None', finalVerification: 'Pending', finalOutcome: 'None' };
const emptyDecision: DecisionDetails = { source: 'none', action: 'None', target: 'None', confidence: '0%', reason: 'None' };
const emptySafety: SafetyState = { status: 'UNCHECKED', action: 'None', verdict: 'Pending', reason: 'Awaiting check' };
const emptyVerification: VerificationState = { status: 'UNVERIFIED', recovered: 'Pending', isRecoveredBool: null, reason: 'Pending', errorRate: '-', latency: '-', serviceStatus: '-' };
const idleAgent: AgentRunState = { running: false, phase: 'idle', attempt: 0, updated_at: null, details: {} };

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

function mapAttempt(attempt: BackendAttempt, index: number, total: number): Attempt {
  const { observations, detection, diagnosis, decision, safety_result, action_result, verification } = attempt;
  const metrics = observations.metrics;
  const signals = detection.signals.length ? detection.signals.map(titleCase).join(', ') : 'No SLO breaches';
  const steps: Attempt['steps'] = [
    { type: 'obs', label: 'Observe & Detect', details: `Fresh telemetry: ${metrics.status.toUpperCase()}, ${(metrics.error_rate * 100).toFixed(1)}% errors, ${metrics.latency_ms}ms latency. Signals: ${signals}.` },
    { type: 'inv', label: 'Investigate', details: `Queried ${observations.logs.length} diagnostic log entries, deployment history, service health, and current version ${observations.current_version}.` },
    { type: 'diag', label: 'Diagnose', details: `${titleCase(diagnosis.probable_cause)} — ${diagnosis.summary}` },
    { type: 'dec', label: 'Decide', details: `Selected ${decision.action}${decision.target != null ? ` → ${formatTarget(decision.target)}` : ''} at ${(decision.confidence * 100).toFixed(0)}% confidence (${decision.source || 'deterministic'}).` },
    { type: 'safe', label: 'Safety Check', details: safety_result.checked ? `Policy ${safety_result.allowed ? 'allowed' : 'blocked'} ${safety_result.action}.` : 'No remediation was proposed; a policy check was not required.', customClass: safety_result.allowed === false ? 'verification-failure' : undefined },
    { type: 'act', label: action_result.action === 'escalate' ? 'Escalate' : 'Remediate', details: action_result.message, customClass: action_result.success ? undefined : 'verification-failure' },
  ];
  if (verification) {
    steps.push({ type: 'ver', label: 'Verify Recovery', details: `${verification.reason}. Fresh telemetry confirms recovered=${verification.recovered ? 'true' : 'false'}.`, customClass: verification.recovered ? 'verification-success' : 'verification-failure' });
    if (!verification.recovered && index < total - 1) {
      steps.push({ type: 'adapt', label: 'Adapt & Re-investigate', details: 'Verification rejected the remediation outcome. The controller retained the failure evidence and began a fresh attempt.', customClass: 'adapt-callout' });
    }
  }
  const succeeded = verification?.recovered === true;
  return {
    id: `attempt-${attempt.attempt}`, number: attempt.attempt, tag: `ATTEMPT ${attempt.attempt}`,
    statusText: succeeded ? 'RECOVERED' : verification ? 'VERIFICATION FAILED' : action_result.status.toUpperCase(),
    statusClass: succeeded ? 'success' : 'retry', steps,
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
    service: ServiceState,
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

    setSummary({
      scenario: label,
      // While a run is in flight the live phase is more informative than the
      // previous run's outcome, so the backend's phase wins.
      agentStatus: agentState.running ? phaseLabel(agentState) : titleCase(status),
      attempts: String(backendAttempts.length),
      finalAction: finalAttempt.decision.action,
      finalVerification: finalVerification ? (finalVerification.recovered ? 'Recovered' : 'Failed') : 'Not run',
      finalOutcome: agentState.running ? 'Running' : status.toUpperCase(),
    });

    setDecision({
      source: finalAttempt.decision.source || 'deterministic',
      action: finalAttempt.decision.action,
      target: formatTarget(finalAttempt.decision.target),
      confidence: `${(finalAttempt.decision.confidence * 100).toFixed(0)}%`,
      reason: finalAttempt.decision.reason,
    });

    setSafety({
      status: finalAttempt.safety_result.checked ? (finalAttempt.safety_result.allowed ? 'ALLOWED' : 'BLOCKED') : 'NOT REQUIRED',
      action: finalAttempt.safety_result.action,
      verdict: finalAttempt.safety_result.checked ? (finalAttempt.safety_result.allowed ? 'ALLOWED' : 'BLOCKED') : 'SKIPPED',
      reason: finalAttempt.action_result.message,
    });

    setVerification(finalVerification ? {
      status: finalVerification.recovered ? 'VERIFIED' : 'FAILED',
      recovered: finalVerification.recovered ? 'YES' : 'NO',
      isRecoveredBool: finalVerification.recovered,
      reason: finalVerification.reason,
      errorRate: `${(service.error_rate * 100).toFixed(1)}%`,
      latency: `${service.latency_ms}ms`,
      serviceStatus: service.status.toUpperCase(),
    } : { ...emptyVerification, status: 'NOT RUN', reason: finalAttempt.action_result.message });

    setAttempts(backendAttempts.map((attempt, index) => mapAttempt(attempt, index, backendAttempts.length)));
    setResolutionBanner({
      visible: !agentState.running,
      text: recovered ? 'INCIDENT RECOVERED — VERIFIED AGAINST LIVE TELEMETRY' : `INCIDENT ${status.toUpperCase()}`,
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
      applyIncident(timeline, status.service, status.scenario, status.agent);
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
