import { useCallback, useEffect, useState } from 'react';
import * as api from '../services/incidentPilotApi';
import type {
  Attempt, BackendAttempt, IncidentResult, IncidentStatusResponse, IncidentSummary,
  DecisionDetails, LogEntry, ResolutionBanner, SafetyState, ServiceState,
  TelemetryPoint, VerificationState,
} from '../types/incidentPilot';

const MAX_SAMPLES = 40;
const SCENARIO_LABELS: Record<string, string> = {
  healthy: 'Normal / Healthy', generic_outage: 'Generic Outage',
  bad_deployment: 'Bad Deployment', adaptive_incident: 'Adaptive Incident',
};
const emptySummary: IncidentSummary = { scenario: 'None', agentStatus: 'Idle', attempts: '0', finalAction: 'None', finalVerification: 'Pending', finalOutcome: 'None' };
const emptyDecision: DecisionDetails = { source: 'none', action: 'None', target: 'None', confidence: '0%', reason: 'None' };
const emptySafety: SafetyState = { status: 'UNCHECKED', action: 'None', verdict: 'Pending', reason: 'Awaiting check' };
const emptyVerification: VerificationState = { status: 'UNVERIFIED', recovered: 'Pending', isRecoveredBool: null, reason: 'Pending', errorRate: '-', latency: '-', serviceStatus: '-' };

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter: string) => letter.toUpperCase());
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

function mapLogs(status: IncidentStatusResponse): LogEntry[] {
  return status.diagnostics.logs.map((entry, index) => ({
    id: `${entry.timestamp}-${index}`,
    time: entry.timestamp.includes('T') ? entry.timestamp.slice(11, 19) : entry.timestamp,
    level: entry.level === 'ERROR' ? 'ERROR' : entry.level === 'WARNING' ? 'WARNING' : 'INFO',
    message: entry.message,
  }));
}

export function useIncidentPilot(initialBaseUrl = api.DEFAULT_BASE_URL) {
  const [backendUrl, setBackendUrl] = useState(api.normalizeBaseUrl(initialBaseUrl));
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'offline' | 'checking'>('checking');
  const [simState, setSimState] = useState<ServiceState>({ status: 'unknown', error_rate: 0, latency_ms: 0, current_version: '—' });
  const [currentReplicas, setCurrentReplicas] = useState(0);
  const [lastSyncTime, setLastSyncTime] = useState('Connecting to live API…');
  const [activeScenario, setActiveScenario] = useState('None');
  const [isRunningAgent, setIsRunningAgent] = useState(false);
  const [runLabel, setRunLabel] = useState('Run Incident');
  const [operationError, setOperationError] = useState<string | null>(null);
  const [summary, setSummary] = useState(emptySummary);
  const [decision, setDecision] = useState(emptyDecision);
  const [safety, setSafety] = useState(emptySafety);
  const [verification, setVerification] = useState(emptyVerification);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [resolutionBanner, setResolutionBanner] = useState<ResolutionBanner>({ visible: false, text: '', isResolved: false });
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [telemetryBuffer, setTelemetryBuffer] = useState<TelemetryPoint[]>([]);

  const applyIncident = useCallback((result: IncidentResult | null, service: ServiceState, scenario: string) => {
    if (!result) {
      setSummary({ ...emptySummary, scenario: SCENARIO_LABELS[scenario] || titleCase(scenario) });
      setDecision(emptyDecision); setSafety(emptySafety); setVerification(emptyVerification);
      setAttempts([]); setResolutionBanner({ visible: false, text: '', isResolved: false });
      return;
    }
    const finalAttempt = result.attempts.at(-1);
    if (!finalAttempt) return;
    const recovered = result.status === 'resolved';
    setSummary({
      scenario: SCENARIO_LABELS[scenario] || titleCase(scenario), agentStatus: titleCase(result.status),
      attempts: String(result.attempts.length), finalAction: result.decision.action,
      finalVerification: result.verification ? (result.verification.recovered ? 'Recovered' : 'Failed') : 'Not run',
      finalOutcome: result.status.toUpperCase(),
    });
    setDecision({ source: result.decision.source || 'deterministic', action: result.decision.action, target: formatTarget(result.decision.target), confidence: `${(result.decision.confidence * 100).toFixed(0)}%`, reason: result.decision.reason });
    setSafety({
      status: finalAttempt.safety_result.checked ? (finalAttempt.safety_result.allowed ? 'ALLOWED' : 'BLOCKED') : 'NOT REQUIRED',
      action: finalAttempt.safety_result.action,
      verdict: finalAttempt.safety_result.checked ? (finalAttempt.safety_result.allowed ? 'ALLOWED' : 'BLOCKED') : 'SKIPPED',
      reason: finalAttempt.safety_result.checked ? 'Deterministic policy gate evaluated the proposed action before execution.' : 'The agent escalated without executing remediation.',
    });
    setVerification(result.verification ? {
      status: result.verification.recovered ? 'VERIFIED' : 'FAILED', recovered: result.verification.recovered ? 'YES' : 'NO',
      isRecoveredBool: result.verification.recovered, reason: result.verification.reason,
      errorRate: `${(service.error_rate * 100).toFixed(1)}%`, latency: `${service.latency_ms}ms`, serviceStatus: service.status.toUpperCase(),
    } : { ...emptyVerification, status: 'NOT RUN', reason: 'No remediation required or execution was blocked.' });
    setAttempts(result.attempts.map((attempt, index) => mapAttempt(attempt, index, result.attempts.length)));
    setResolutionBanner({ visible: true, text: recovered ? 'INCIDENT RECOVERED — VERIFIED AGAINST LIVE TELEMETRY' : `INCIDENT ${result.status.toUpperCase()}`, isResolved: recovered });
  }, []);

  const applyStatus = useCallback((status: IncidentStatusResponse) => {
    setSimState(status.service); setCurrentReplicas(status.replicas);
    setActiveScenario(SCENARIO_LABELS[status.scenario] || titleCase(status.scenario));
    setLogs(mapLogs(status)); setLastSyncTime(`Live API · ${new Date().toLocaleTimeString()}`);
    applyIncident(status.incident, status.service, status.scenario);
  }, [applyIncident]);

  const fetchLiveStatus = useCallback(async (url = backendUrl, quiet = true) => {
    try {
      const status = await api.fetchStatus(url);
      setConnectionStatus('connected'); applyStatus(status); setOperationError(null);
      return status;
    } catch (error) {
      setConnectionStatus('offline'); setLastSyncTime('Stale · API unavailable');
      if (!quiet) setOperationError(error instanceof Error ? error.message : 'Backend request failed.');
      return null;
    }
  }, [backendUrl, applyStatus]);

  const checkConnection = useCallback(async (_silent = false, customUrl?: string) => {
    const url = api.normalizeBaseUrl(customUrl || backendUrl);
    setConnectionStatus('checking');
    return Boolean(await fetchLiveStatus(url, false));
  }, [backendUrl, fetchLiveStatus]);

  const triggerScenario = useCallback(async (type: string) => {
    if (isRunningAgent) return;
    setIsRunningAgent(true); setOperationError(null);
    try {
      await api.resetIncident(backendUrl);
      if (type === 'Generic Outage') await api.simulateOutage(backendUrl);
      else if (type === 'Bad Deployment') await api.simulateBadDeployment(backendUrl);
      else if (type === 'Adaptive Incident') await api.simulateAdaptiveIncident(backendUrl);
      await fetchLiveStatus(backendUrl, false);
    } catch (error) {
      setOperationError(error instanceof Error ? error.message : 'Could not activate scenario.');
      await fetchLiveStatus(backendUrl);
    } finally { setIsRunningAgent(false); }
  }, [backendUrl, fetchLiveStatus, isRunningAgent]);

  const resetSystem = useCallback(async () => {
    if (isRunningAgent) return;
    setIsRunningAgent(true); setOperationError(null);
    try { await api.resetIncident(backendUrl); await fetchLiveStatus(backendUrl, false); }
    catch (error) { setOperationError(error instanceof Error ? error.message : 'Reset failed.'); }
    finally { setIsRunningAgent(false); }
  }, [backendUrl, fetchLiveStatus, isRunningAgent]);

  const runIncident = useCallback(async () => {
    if (isRunningAgent) return;
    setIsRunningAgent(true); setRunLabel('Agent running…'); setOperationError(null);
    setSummary((current) => ({ ...current, agentStatus: 'Observing live state…', finalOutcome: 'Running' }));
    try { await api.runIncident(backendUrl); await fetchLiveStatus(backendUrl, false); }
    catch (error) { setOperationError(error instanceof Error ? error.message : 'Incident run failed.'); await fetchLiveStatus(backendUrl); }
    finally { setIsRunningAgent(false); setRunLabel('Run Incident'); }
  }, [backendUrl, fetchLiveStatus, isRunningAgent]);

  useEffect(() => {
    void checkConnection(false);
    const poll = window.setInterval(() => void fetchLiveStatus(backendUrl), 2000);
    return () => window.clearInterval(poll);
  }, [backendUrl, checkConnection, fetchLiveStatus]);

  useEffect(() => {
    if (simState.status === 'unknown') return;
    setTelemetryBuffer((previous) => [...previous.slice(-(MAX_SAMPLES - 1)), { errorRate: simState.error_rate, latency: simState.latency_ms, status: simState.status }]);
  }, [simState]);

  return {
    backendUrl, setBackendUrl, connectionStatus, checkConnection, simState, currentReplicas,
    lastSyncTime, isLiveSync: connectionStatus === 'connected', activeScenario, triggerScenario,
    resetSystem, runIncident, isRunningAgent, runLabel, summary, decision, safety, verification,
    attempts, resolutionBanner, telemetryBuffer, logs, operationError,
  };
}
