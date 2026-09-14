import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from '../services/api';
import type {
  AgentRunState,
  Attempt,
  DecisionDetails,
  IncidentSummary,
  LogEntry,
  ResolutionBanner,
  RuntimeConfig,
  RuntimeEnvironment,
  SafetyAssessment,
  SafetyState,
  ScenarioId,
  ServiceState,
  TelemetryPoint,
  TimelineEvent,
  VerificationState,
} from '../types/incidentPilot';
import {
  buildIncidentView,
  EMPTY_DECISION,
  EMPTY_SAFETY,
  EMPTY_SUMMARY,
  EMPTY_VERIFICATION,
  FALLBACK_CONFIG,
  idleAgent,
  mapLogs,
  mapSafetyAssessment,
  phaseLabel,
  scenarioLabel,
} from '../viewModels/incidentPilot';

const MAX_SAMPLES = 40;
const POLL_INTERVAL_MS = 1_000;

function sameSnapshot(
  status: { revision: number; agent: AgentRunState },
  timeline: { revision: number; run_id: string | null },
): boolean {
  return status.revision === timeline.revision && status.agent.run_id === timeline.run_id;
}

export function useIncidentPilot(initialBaseUrl = api.DEFAULT_BASE_URL) {
  const [backendUrl, setBackendUrlState] = useState(() => api.normalizeBaseUrl(initialBaseUrl));
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'offline' | 'checking'>('checking');
  const [config, setConfig] = useState<RuntimeConfig>(FALLBACK_CONFIG);
  const [environment, setEnvironment] = useState<RuntimeEnvironment>(FALLBACK_CONFIG.environment);
  const [service, setService] = useState<ServiceState>({ status: 'unknown', error_rate: 0, latency_ms: 0, current_version: '—' });
  const [currentReplicas, setCurrentReplicas] = useState(0);
  const [lastSyncTime, setLastSyncTime] = useState('Connecting to live API…');
  const [activeScenario, setActiveScenario] = useState('None');
  const [agent, setAgent] = useState<AgentRunState>(() => idleAgent());
  const [pendingOperation, setPendingOperation] = useState(false);
  const [requestedRunId, setRequestedRunId] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [summary, setSummary] = useState<IncidentSummary>(EMPTY_SUMMARY);
  const [decision, setDecision] = useState<DecisionDetails>(EMPTY_DECISION);
  const [safety, setSafety] = useState<SafetyState>(EMPTY_SAFETY);
  const [verification, setVerification] = useState<VerificationState>(EMPTY_VERIFICATION);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [resolutionBanner, setResolutionBanner] = useState<ResolutionBanner>({ visible: false, text: '', isResolved: false });
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [telemetryBuffer, setTelemetryBuffer] = useState<TelemetryPoint[]>([]);
  const [safetyAssessment, setSafetyAssessment] = useState<SafetyAssessment | null>(null);
  const [safetyChallenge, setSafetyChallenge] = useState<SafetyState | null>(null);

  const lifetimeRef = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    lifetimeRef.current = controller;
    return () => controller.abort();
  }, []);

  const syncTokenRef = useRef(0);
  const requestedRunRef = useRef<string | null>(null);
  useEffect(() => { requestedRunRef.current = requestedRunId; }, [requestedRunId]);

  const setBackendUrl = useCallback((url: string) => {
    setBackendUrlState(api.normalizeBaseUrl(url));
    setRequestedRunId(null);
    setSafetyAssessment(null);
    setSafetyChallenge(null);
  }, []);

  const applyTimeline = useCallback((
    timeline: Awaited<ReturnType<typeof api.fetchTimeline>>,
    scenario: string,
    agentState: AgentRunState,
    runtimeConfig: RuntimeConfig,
  ) => {
    const view = buildIncidentView(
      timeline.attempts,
      timeline.status,
      timeline.reason,
      scenario,
      agentState,
      runtimeConfig,
    );
    setSummary(view.summary);
    setDecision(view.decision);
    setSafety(view.safety);
    setVerification(view.verification);
    setAttempts(view.attempts);
    setEvents(timeline.events);
    setResolutionBanner(view.resolutionBanner);

    if (
      requestedRunRef.current
      && requestedRunRef.current === timeline.run_id
      && timeline.status !== 'running'
    ) {
      requestedRunRef.current = null;
      setRequestedRunId(null);
    }
  }, []);

  const sync = useCallback(async (url = backendUrl, reportErrors = false) => {
    const token = ++syncTokenRef.current;
    const signal = lifetimeRef.current?.signal;

    try {
      const [status, timeline] = await Promise.all([
        api.fetchStatus(url, signal),
        api.fetchTimeline(url, signal),
      ]);
      if (token !== syncTokenRef.current || signal?.aborted) return null;

      setConnectionStatus('connected');
      setService(status.service);
      setCurrentReplicas(status.replicas ?? status.service.replicas ?? 0);
      setActiveScenario(scenarioLabel(status.scenario));
      setEnvironment(status.environment || config.environment);
      setAgent(status.agent);
      setLogs(mapLogs(status.diagnostics?.logs || []));
      setLastSyncTime(`Live API · revision ${status.revision} · ${new Date().toLocaleTimeString()}`);
      setOperationError(null);

      // Never combine an attempt list with a status snapshot from a different
      // runtime revision or incident. A subsequent one-second poll catches up.
      if (sameSnapshot(status, timeline)) {
        applyTimeline(timeline, status.scenario, status.agent, config);
      }
      return status;
    } catch (error) {
      if (token !== syncTokenRef.current || signal?.aborted) return null;
      setConnectionStatus('offline');
      setLastSyncTime('Stale · API unavailable');
      if (reportErrors) setOperationError(error instanceof Error ? error.message : 'Backend request failed.');
      return null;
    }
  }, [applyTimeline, backendUrl, config]);

  const checkConnection = useCallback(async (customUrl?: string) => {
    const url = api.normalizeBaseUrl(customUrl || backendUrl);
    setConnectionStatus('checking');
    setBackendUrlState(url);
    try {
      await api.fetchHealth(url, lifetimeRef.current?.signal);
      return Boolean(await sync(url, true));
    } catch (error) {
      if (!lifetimeRef.current?.signal.aborted) {
        setConnectionStatus('offline');
        setOperationError(error instanceof Error ? error.message : 'Backend request failed.');
      }
      return false;
    }
  }, [backendUrl, sync]);

  const runMutation = useCallback(async (
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
      if (!lifetimeRef.current?.signal.aborted) {
        setOperationError(error instanceof Error ? error.message : failureMessage);
        await sync(backendUrl);
      }
    } finally {
      setPendingOperation(false);
    }
  }, [backendUrl, pendingOperation, sync]);

  const triggerScenario = useCallback((scenario: ScenarioId) => {
    if (!environment.supports_scenario_injection) return Promise.resolve();
    setSafetyAssessment(null);
    setSafetyChallenge(null);
    return runMutation(async (signal) => {
      await api.resetIncident(backendUrl, signal);
      if (scenario === 'generic_outage') await api.simulateOutage(backendUrl, signal);
      else if (scenario === 'bad_deployment') await api.simulateBadDeployment(backendUrl, signal);
      else if (scenario === 'adaptive_incident') await api.simulateAdaptiveIncident(backendUrl, signal);
    }, 'Could not activate scenario.');
  }, [backendUrl, environment.supports_scenario_injection, runMutation]);

  const resetSystem = useCallback(() => {
    setSafetyAssessment(null);
    setSafetyChallenge(null);
    return runMutation((signal) => api.resetIncident(backendUrl, signal), 'Reset failed.');
  }, [backendUrl, runMutation]);

  const runIncident = useCallback(async () => {
    if (pendingOperation || agent.running || requestedRunRef.current) return;
    setPendingOperation(true);
    setOperationError(null);
    setSafetyAssessment(null);
    setSafetyChallenge(null);
    try {
      const started = await api.runIncident(backendUrl, lifetimeRef.current?.signal);
      requestedRunRef.current = started.run_id;
      setRequestedRunId(started.run_id);
      await sync(backendUrl, true);
    } catch (error) {
      if (!lifetimeRef.current?.signal.aborted) {
        setOperationError(error instanceof Error ? error.message : 'Incident run failed to start.');
      }
    } finally {
      setPendingOperation(false);
    }
  }, [agent.running, backendUrl, pendingOperation, sync]);

  const testSafetyGate = useCallback(async () => {
    if (pendingOperation) return;
    setPendingOperation(true);
    setOperationError(null);
    try {
      const assessment = await api.evaluateSafety(backendUrl, {
        action: 'scale_service',
        target: 20,
        namespace: config.safety?.allowed_namespace || environment.namespace || 'incidentpilot',
      }, lifetimeRef.current?.signal);
      setSafetyAssessment(assessment);
      setSafetyChallenge(mapSafetyAssessment(assessment, config));
    } catch (error) {
      if (!lifetimeRef.current?.signal.aborted) {
        setOperationError(error instanceof Error ? error.message : 'Safety challenge failed.');
      }
    } finally {
      setPendingOperation(false);
    }
  }, [backendUrl, config, environment.namespace, pendingOperation]);

  useEffect(() => {
    let active = true;
    api.fetchConfig(backendUrl, lifetimeRef.current?.signal)
      .then((next) => {
        if (!active) return;
        setConfig(next);
        setEnvironment(next.environment);
        setAgent((current) => current.run_id ? current : idleAgent(next));
      })
      .catch(() => { /* The status poll owns connection errors. */ });
    return () => { active = false; };
  }, [backendUrl]);

  useEffect(() => {
    void checkConnection(backendUrl);
    const poll = window.setInterval(() => { void sync(backendUrl); }, POLL_INTERVAL_MS);
    return () => window.clearInterval(poll);
    // The initial connectivity probe should run only when the target changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendUrl]);

  useEffect(() => {
    if (service.status === 'unknown') return;
    setTelemetryBuffer((previous) => {
      const last = previous[previous.length - 1];
      if (
        last
        && last.errorRate === service.error_rate
        && last.latency === service.latency_ms
        && last.status === service.status
      ) return previous;
      return [...previous.slice(-(MAX_SAMPLES - 1)), {
        errorRate: service.error_rate,
        latency: service.latency_ms,
        status: service.status,
      }];
    });
  }, [service.error_rate, service.latency_ms, service.status]);

  const isRunningAgent = pendingOperation || agent.running || requestedRunId !== null;
  const runLabel = useMemo(() => isRunningAgent ? 'Agent running…' : 'Run Incident', [isRunningAgent]);

  return {
    backendUrl,
    setBackendUrl,
    connectionStatus,
    checkConnection,
    config,
    environment,
    simState: service,
    currentReplicas,
    lastSyncTime,
    isLiveSync: connectionStatus === 'connected',
    activeScenario,
    triggerScenario,
    resetSystem,
    runIncident,
    testSafetyGate,
    safetyAssessment,
    safetyChallenge,
    agent,
    agentPhase: phaseLabel(agent),
    agentPhaseCode: agent.phase,
    isRunningAgent,
    runLabel,
    summary,
    decision,
    safety,
    verification,
    attempts,
    events,
    resolutionBanner,
    telemetryBuffer,
    maxSamples: MAX_SAMPLES,
    logs,
    operationError,
  };
}
