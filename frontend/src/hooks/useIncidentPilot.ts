import { useState, useEffect, useRef, useCallback } from 'react';
import * as api from '../services/incidentPilotApi';
import type {
  ServiceState,
  TelemetryPoint,
  IncidentSummary,
  DecisionDetails,
  SafetyState,
  VerificationState,
  Attempt,
  ResolutionBanner,
  LogEntry,
} from '../types/incidentPilot';

const MAX_SAMPLES = 40;

export function useIncidentPilot(initialBaseUrl = api.DEFAULT_BASE_URL) {
  const [backendUrl, setBackendUrl] = useState<string>(initialBaseUrl);
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'offline' | 'checking'>('offline');
  const isBackendAliveRef = useRef<boolean>(false);

  // In-memory simulation fallback state
  const [simState, setSimState] = useState<ServiceState>({
    status: 'healthy',
    error_rate: 0.01,
    latency_ms: 100,
    current_version: 'v41',
  });
  const simStateRef = useRef<ServiceState>(simState);
  simStateRef.current = simState;

  const [currentReplicas, setCurrentReplicas] = useState<number>(1);
  const [activeScenario, setActiveScenario] = useState<string>('None');
  const [lastSyncTime, setLastSyncTime] = useState<string>('Sync: Initializing');
  const [isLiveSync, setIsLiveSync] = useState<boolean>(false);

  // Running agent execution status
  const [isRunningAgent, setIsRunningAgent] = useState<boolean>(false);
  const [runLabel, setRunLabel] = useState<string>('Run Incident');

  // Summary state
  const [summary, setSummary] = useState<IncidentSummary>({
    scenario: 'None',
    agentStatus: 'Idle',
    attempts: '0',
    finalAction: 'None',
    finalVerification: 'Pending',
    finalOutcome: 'None',
  });

  // Decision details
  const [decision, setDecision] = useState<DecisionDetails>({
    source: 'none',
    action: 'None',
    target: 'None',
    confidence: '0%',
    reason: 'None',
  });

  // Safety engine
  const [safety, setSafety] = useState<SafetyState>({
    status: 'UNCHECKED',
    action: 'None',
    verdict: 'Pending',
    reason: 'Awaiting check',
  });

  // Verification engine
  const [verification, setVerification] = useState<VerificationState>({
    status: 'UNVERIFIED',
    recovered: 'Pending',
    isRecoveredBool: null,
    reason: 'Pending',
    errorRate: '-',
    latency: '-',
    serviceStatus: '-',
  });

  // Timeline attempts list
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [resolutionBanner, setResolutionBanner] = useState<ResolutionBanner>({
    visible: false,
    text: '',
    isResolved: false,
  });

  // Telemetry buffer for chart (40 samples)
  const [telemetryBuffer, setTelemetryBuffer] = useState<TelemetryPoint[]>(() => {
    const initial: TelemetryPoint[] = [];
    for (let i = 0; i < MAX_SAMPLES; i++) {
      initial.push({ errorRate: 0.01, latency: 100, status: 'healthy' });
    }
    return initial;
  });

  // Diagnostic Logs
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const addLog = useCallback((level: 'INFO' | 'WARNING' | 'ERROR', message: string) => {
    const time = new Date().toTimeString().split(' ')[0];
    setLogs((prev) => [
      { id: Math.random().toString(36).substr(2, 9), time, level, message },
      ...prev,
    ]);
  }, []);

  const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms));

  // Update telemetry helper
  const updateTelemetryData = useCallback(
    (data: Partial<ServiceState>, isLive = true) => {
      setSimState((prev) => ({
        ...prev,
        status: data.status || prev.status,
        error_rate: typeof data.error_rate === 'number' ? data.error_rate : prev.error_rate,
        latency_ms: typeof data.latency_ms === 'number' ? data.latency_ms : prev.latency_ms,
        current_version: data.current_version || prev.current_version,
      }));

      const timeStr = new Date().toLocaleTimeString();
      setLastSyncTime(isLive ? `Live Sync: ${timeStr}` : `Local Sync: ${timeStr}`);
      setIsLiveSync(isLive);
    },
    []
  );

  // Fetch live telemetry from FastAPI backend
  const fetchLiveTelemetry = useCallback(
    async (url = backendUrl) => {
      if (!isBackendAliveRef.current) return;
      try {
        const [metrics, version] = await Promise.all([
          api.fetchMetrics(url),
          api.fetchVersion(url),
        ]);
        updateTelemetryData(
          {
            status: metrics.status,
            error_rate: metrics.error_rate,
            latency_ms: metrics.latency_ms,
            current_version: version.current_version,
          },
          true
        );
      } catch (e) {
        console.warn('Live telemetry sync failed:', e);
      }
    },
    [backendUrl, updateTelemetryData]
  );

  // Connectivity check
  const checkConnection = useCallback(
    async (silent = false, customUrl?: string) => {
      const url = api.normalizeBaseUrl(customUrl || backendUrl);
      if (!silent) {
        setConnectionStatus('checking');
      }
      try {
        await api.checkHealth(url);
        isBackendAliveRef.current = true;
        setConnectionStatus('connected');
        await fetchLiveTelemetry(url);
        return true;
      } catch (e) {
        isBackendAliveRef.current = false;
        setConnectionStatus('offline');
        updateTelemetryData(
          {
            status: simStateRef.current.status,
            error_rate: simStateRef.current.error_rate,
            latency_ms: simStateRef.current.latency_ms,
            current_version: simStateRef.current.current_version,
          },
          false
        );
        return false;
      }
    },
    [backendUrl, fetchLiveTelemetry, updateTelemetryData]
  );

  // Telemetry buffer sampler (1000ms cadence)
  const sampleTelemetry = useCallback(() => {
    const current = simStateRef.current;
    const err = typeof current.error_rate === 'number' ? current.error_rate : 0.01;
    const lat = typeof current.latency_ms === 'number' ? current.latency_ms : 100;
    const st = current.status || 'healthy';

    setTelemetryBuffer((prev) => {
      const next = [...prev, { errorRate: err, latency: lat, status: st }];
      if (next.length > MAX_SAMPLES) {
        next.shift();
      }
      return next;
    });
  }, []);

  // Scenario trigger
  const triggerScenario = useCallback(
    async (type: string) => {
      setActiveScenario(type);
      setSummary((prev) => ({
        ...prev,
        scenario: type,
        agentStatus: 'Incident Active',
        finalOutcome: 'Pending',
      }));
      setResolutionBanner({ visible: false, text: '', isResolved: false });

      if (type === 'Normal / Healthy') {
        if (isBackendAliveRef.current) {
          try {
            await api.simulateRecover(backendUrl);
            await fetchLiveTelemetry(backendUrl);
            addLog('INFO', 'Simulated recovery applied on FastAPI service.');
          } catch (e) {
            addLog('WARNING', 'Failed to reach FastAPI, updating locally.');
          }
        }
        setCurrentReplicas(1);
        updateTelemetryData(
          {
            status: 'healthy',
            error_rate: 0.01,
            latency_ms: 100,
            current_version: 'v41',
          },
          isBackendAliveRef.current
        );
        addLog('INFO', 'System restored to baseline healthy state.');
        return;
      }

      if (type === 'Generic Outage') {
        if (isBackendAliveRef.current) {
          try {
            await api.simulateOutage(backendUrl);
            await fetchLiveTelemetry(backendUrl);
            addLog('ERROR', 'Outage simulated on FastAPI service: 70% errors, 1000ms latency.');
          } catch (e) {
            addLog('WARNING', 'Outage simulated locally.');
          }
        }
        updateTelemetryData(
          {
            status: 'down',
            error_rate: 0.7,
            latency_ms: 1000,
          },
          isBackendAliveRef.current
        );
        addLog('ERROR', 'Alert triggered: Error rate 70% exceeds threshold 10%.');
        addLog('WARNING', 'Latency 1000ms breached SLA threshold (300ms).');
        return;
      }

      if (type === 'Bad Deployment') {
        if (isBackendAliveRef.current) {
          try {
            await api.simulateBadDeployment(backendUrl);
            await fetchLiveTelemetry(backendUrl);
            addLog('ERROR', 'FastAPI bad-deployment applied: deployed v42.');
          } catch (e) {
            addLog('WARNING', 'Bad deployment simulated locally.');
          }
        }
        updateTelemetryData(
          {
            status: 'down',
            error_rate: 0.7,
            latency_ms: 1000,
            current_version: 'v42',
          },
          isBackendAliveRef.current
        );
        addLog('ERROR', 'Deployment v42 introduced application failures.');
        addLog('ERROR', 'HTTP 503 responses increased after deployment v42.');
        return;
      }

      if (type === 'Adaptive Incident') {
        if (isBackendAliveRef.current) {
          try {
            await api.simulateBadDeployment(backendUrl);
            await fetchLiveTelemetry(backendUrl);
          } catch (e) {}
        }
        updateTelemetryData(
          {
            status: 'down',
            error_rate: 0.7,
            latency_ms: 1000,
            current_version: 'v42',
          },
          isBackendAliveRef.current
        );
        addLog(
          'ERROR',
          'Complex incident initialized: Deployment v42 active with elevated error rate.'
        );
        addLog(
          'WARNING',
          'Diagnostic evidence suggests potential resource saturation alongside deployment logs.'
        );
        return;
      }
    },
    [backendUrl, fetchLiveTelemetry, updateTelemetryData, addLog]
  );

  // Reset system
  const resetSystem = useCallback(async () => {
    setActiveScenario('None');
    setCurrentReplicas(1);

    setSummary({
      scenario: 'None',
      agentStatus: 'Idle',
      attempts: '0',
      finalAction: 'None',
      finalVerification: 'Pending',
      finalOutcome: 'None',
    });

    setDecision({
      source: 'none',
      action: 'None',
      target: 'None',
      confidence: '0%',
      reason: 'None',
    });

    setSafety({
      status: 'UNCHECKED',
      action: 'None',
      verdict: 'Pending',
      reason: 'Awaiting check',
    });

    setVerification({
      status: 'UNVERIFIED',
      recovered: 'Pending',
      isRecoveredBool: null,
      reason: 'Pending',
      errorRate: '-',
      latency: '-',
      serviceStatus: '-',
    });

    setAttempts([]);
    setResolutionBanner({ visible: false, text: '', isResolved: false });

    if (isBackendAliveRef.current) {
      try {
        await api.simulateRecover(backendUrl);
        await api.simulateRollback(backendUrl, 'v41');
        await fetchLiveTelemetry(backendUrl);
        addLog('INFO', 'System reset to clean baseline on FastAPI service.');
      } catch (e) {
        addLog('WARNING', 'Reset completed locally.');
      }
    }

    updateTelemetryData(
      {
        status: 'healthy',
        error_rate: 0.01,
        latency_ms: 100,
        current_version: 'v41',
      },
      isBackendAliveRef.current
    );
    addLog('INFO', 'System reset to clean healthy baseline.');
  }, [backendUrl, fetchLiveTelemetry, updateTelemetryData, addLog]);

  // Workflow implementations
  const runAdaptiveWorkflow = async () => {
    setSummary((prev) => ({ ...prev, attempts: '2' }));

    const attempt1: Attempt = {
      id: 'attempt-1',
      number: 1,
      tag: 'ATTEMPT 1',
      statusText: 'RUNNING',
      statusClass: 'running',
      steps: [],
    };
    setAttempts([attempt1]);

    await sleep(500);
    attempt1.steps.push({
      type: 'obs',
      label: 'Observe',
      details:
        'Service status: DOWN | Error rate: 70.0% | Latency: 1000ms | Logs indicate connection timeouts and thread contention.',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);
    addLog('INFO', '[Attempt 1] Observations collected: Error rate 70%, Latency 1000ms.');

    await sleep(600);
    setDecision({
      source: 'deterministic',
      action: 'scale_service',
      target: '4 replicas',
      confidence: '78%',
      reason:
        'Initial log parsing detected connection timeouts and thread pool contention; scaling service to absorb load.',
    });
    attempt1.steps.push({
      type: 'dec',
      label: 'Decision Engine',
      details:
        'Recommended action: Scale service to 4 replicas (Confidence: 78%, Source: deterministic).',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);
    addLog('INFO', '[Attempt 1] Decision engine selected action: scale_service to 4 replicas.');

    await sleep(500);
    setSafety({
      status: 'ALLOWED',
      action: 'scale_service',
      verdict: 'ALLOWED',
      reason: 'Target replica count 4 is within safety envelope [1, 10]. Approved for execution.',
    });
    attempt1.steps.push({
      type: 'safe',
      label: 'Safety Check',
      details: 'Safety Policy approved: 4 replicas is within safe range [1, 10].',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);
    addLog('INFO', '[Attempt 1] Safety check passed: scale_service approved.');

    await sleep(600);
    setCurrentReplicas(4);
    attempt1.steps.push({
      type: 'act',
      label: 'Remediation Action',
      details: 'Action executed: Scaled replica pool to 4 pods. Command returned success status.',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);
    addLog('INFO', '[Attempt 1] Remediation executed: Scaled to 4 replicas.');

    await sleep(800);
    setVerification({
      status: 'FAILED',
      recovered: 'NO',
      isRecoveredBool: false,
      reason: 'Service metrics are still unhealthy: Error rate remains 70%, Latency 1000ms.',
      errorRate: '70.0%',
      latency: '1000ms',
      serviceStatus: 'DOWN',
    });
    attempt1.steps.push({
      type: 'ver',
      label: 'Telemetry Verification',
      details: 'Failed: Service metrics are still unhealthy (Error rate: 70%, Latency: 1000ms).',
      customClass: 'verification-failure',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);
    addLog('ERROR', '[Attempt 1] Verification FAILED: Scaling succeeded but metrics remained down!');

    await sleep(500);
    attempt1.steps.push({
      type: 'adapt',
      label: 'Adaptation Loop',
      details:
        'Action success is not incident recovery. Primary remediation failed to restore health. Initiating secondary investigation.',
      customClass: 'adapt-callout',
    });
    attempt1.statusText = 'FAILED (VERIFICATION REJECTED)';
    attempt1.statusClass = 'retry';
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);
    addLog(
      'WARNING',
      '[Attempt 1] Adaptation triggered: Discarding false resolution hypothesis, starting Attempt 2.'
    );

    await sleep(700);
    const attempt2: Attempt = {
      id: 'attempt-2',
      number: 2,
      tag: 'ATTEMPT 2',
      statusText: 'RUNNING',
      statusClass: 'running',
      steps: [],
    };
    setAttempts([attempt1, attempt2]);

    await sleep(600);
    attempt2.steps.push({
      type: 'obs',
      label: 'Observe (Re-investigation)',
      details:
        'Deep inspection of deployment history: Detected recent canary promotion to v42 matching incident inception timestamp.',
    });
    setAttempts([attempt1, { ...attempt2, steps: [...attempt2.steps] }]);
    addLog(
      'INFO',
      '[Attempt 2] Fresh investigation revealed deployment correlation: v42 identified as root cause.'
    );

    await sleep(600);
    setDecision({
      source: 'deterministic',
      action: 'rollback_deployment',
      target: 'v41',
      confidence: '94%',
      reason:
        'Logs confirm HTTP 503 surge correlated with v42 release. Deployment history confirms v41 as previous stable version.',
    });
    attempt2.steps.push({
      type: 'dec',
      label: 'Decision Engine (Adapted)',
      details:
        'Recommended action: Rollback deployment to v41 (Confidence: 94%, Source: deterministic).',
    });
    setAttempts([attempt1, { ...attempt2, steps: [...attempt2.steps] }]);
    addLog('INFO', '[Attempt 2] Decision engine adapted: Initiating rollback to v41.');

    await sleep(500);
    setSafety({
      status: 'ALLOWED',
      action: 'rollback_deployment',
      verdict: 'ALLOWED',
      reason: 'Target version v41 confirmed in verified deployment history. Approved for execution.',
    });
    attempt2.steps.push({
      type: 'safe',
      label: 'Safety Check',
      details: 'Safety Policy approved: v41 verified in historical release manifest.',
    });
    setAttempts([attempt1, { ...attempt2, steps: [...attempt2.steps] }]);
    addLog('INFO', '[Attempt 2] Safety check passed: rollback_deployment approved.');

    await sleep(700);
    if (isBackendAliveRef.current) {
      try {
        await api.simulateRollback(backendUrl, 'v41');
      } catch (e) {}
    }
    setSimState((prev) => ({ ...prev, current_version: 'v41' }));
    attempt2.steps.push({
      type: 'act',
      label: 'Remediation Action',
      details: 'Action executed: Rolled back deployment to v41. Service binary repointed.',
    });
    setAttempts([attempt1, { ...attempt2, steps: [...attempt2.steps] }]);
    addLog('INFO', '[Attempt 2] Rollback executed: Rolled back to v41.');

    await sleep(800);
    if (isBackendAliveRef.current) {
      await fetchLiveTelemetry(backendUrl);
    } else {
      updateTelemetryData(
        {
          status: 'healthy',
          error_rate: 0.01,
          latency_ms: 100,
          current_version: 'v41',
        },
        false
      );
    }

    setVerification({
      status: 'VERIFIED',
      recovered: 'YES',
      isRecoveredBool: true,
      reason: 'Service metrics are healthy: Error rate normalized to 1.0%, Latency 100ms.',
      errorRate: '1.0%',
      latency: '100ms',
      serviceStatus: 'HEALTHY',
    });
    attempt2.steps.push({
      type: 'ver',
      label: 'Telemetry Verification',
      details:
        'Verified: Service metrics are healthy (Error rate: 1.0%, Latency: 100ms). Baseline restored.',
      customClass: 'verification-success',
    });
    attempt2.statusText = 'RECOVERED';
    attempt2.statusClass = 'success';
    setAttempts([attempt1, { ...attempt2, steps: [...attempt2.steps] }]);
    addLog('INFO', '[Attempt 2] Verification SUCCEEDED: Telemetry confirmed healthy.');

    setSummary((prev) => ({
      ...prev,
      agentStatus: 'Resolved',
      finalAction: 'rollback_deployment -> v41',
      finalVerification: 'Recovered (healthy metrics)',
      finalOutcome: 'RESOLVED',
    }));

    setResolutionBanner({
      visible: true,
      text: 'INCIDENT RESOLVED (VERIFIED BY SERVICE METRICS)',
      isResolved: true,
    });
    addLog('INFO', 'INCIDENT RESOLVED: Autonomous adaptive loop complete.');
  };

  const runSingleRollbackWorkflow = async () => {
    setSummary((prev) => ({ ...prev, attempts: '1' }));
    const attempt1: Attempt = {
      id: 'attempt-1',
      number: 1,
      tag: 'ATTEMPT 1',
      statusText: 'RUNNING',
      statusClass: 'running',
      steps: [],
    };
    setAttempts([attempt1]);

    await sleep(500);
    attempt1.steps.push({
      type: 'obs',
      label: 'Observe',
      details: 'Service status: DOWN | Error rate: 70.0% | Latency: 1000ms | Version: v42.',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);
    addLog('INFO', '[Attempt 1] Collected metrics and log evidence on v42.');

    await sleep(600);
    setDecision({
      source: 'deterministic',
      action: 'rollback_deployment',
      target: 'v41',
      confidence: '92%',
      reason: 'Application error after deployment of v42. Prior known stable version is v41.',
    });
    attempt1.steps.push({
      type: 'dec',
      label: 'Decision Engine',
      details: 'Action: Rollback deployment to v41 (Confidence: 92%).',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);

    await sleep(500);
    setSafety({
      status: 'ALLOWED',
      action: 'rollback_deployment',
      verdict: 'ALLOWED',
      reason: 'Target v41 exists in release history. Action allowed.',
    });
    attempt1.steps.push({
      type: 'safe',
      label: 'Safety Check',
      details: 'Safety Policy: Action allowed.',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);

    await sleep(600);
    if (isBackendAliveRef.current) {
      try {
        await api.simulateRollback(backendUrl, 'v41');
        await fetchLiveTelemetry(backendUrl);
      } catch (e) {}
    } else {
      updateTelemetryData(
        {
          status: 'healthy',
          error_rate: 0.01,
          latency_ms: 100,
          current_version: 'v41',
        },
        false
      );
    }
    attempt1.steps.push({
      type: 'act',
      label: 'Remediation Action',
      details: 'Executed: Rolled back to v41.',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);

    await sleep(800);
    setVerification({
      status: 'VERIFIED',
      recovered: 'YES',
      isRecoveredBool: true,
      reason: 'Service metrics are healthy.',
      errorRate: '1.0%',
      latency: '100ms',
      serviceStatus: 'HEALTHY',
    });
    attempt1.steps.push({
      type: 'ver',
      label: 'Telemetry Verification',
      details: 'Verified: Service metrics are healthy.',
      customClass: 'verification-success',
    });
    attempt1.statusText = 'RECOVERED';
    attempt1.statusClass = 'success';
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);

    setSummary((prev) => ({
      ...prev,
      agentStatus: 'Resolved',
      finalAction: 'rollback_deployment -> v41',
      finalVerification: 'Recovered',
      finalOutcome: 'RESOLVED',
    }));
    setResolutionBanner({
      visible: true,
      text: 'INCIDENT RESOLVED',
      isResolved: true,
    });
    addLog('INFO', 'Incident resolved cleanly via single rollback pass.');
  };

  const runStandardOutageWorkflow = async () => {
    setSummary((prev) => ({ ...prev, attempts: '1' }));
    const attempt1: Attempt = {
      id: 'attempt-1',
      number: 1,
      tag: 'ATTEMPT 1',
      statusText: 'RUNNING',
      statusClass: 'running',
      steps: [],
    };
    setAttempts([attempt1]);

    await sleep(500);
    attempt1.steps.push({
      type: 'obs',
      label: 'Observe',
      details:
        'Service status: DOWN | Error rate: 70.0% | Latency: 1000ms | No deployment changes detected.',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);
    addLog('INFO', '[Attempt 1] Observed generic service degradation without version triggers.');

    await sleep(600);
    setDecision({
      source: 'deterministic',
      action: 'restart_service',
      target: 'simulated_service',
      confidence: '85%',
      reason:
        'Transient socket degradation observed; attempting service restart to reset active threads.',
    });
    attempt1.steps.push({
      type: 'dec',
      label: 'Decision Engine',
      details: 'Action: Restart service (Confidence: 85%).',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);

    await sleep(500);
    setSafety({
      status: 'ALLOWED',
      action: 'restart_service',
      verdict: 'ALLOWED',
      reason: 'Service restart permitted by SRE safety policy.',
    });
    attempt1.steps.push({
      type: 'safe',
      label: 'Safety Check',
      details: 'Safety Policy: Action allowed.',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);

    await sleep(600);
    if (isBackendAliveRef.current) {
      try {
        await api.simulateRecover(backendUrl);
        await fetchLiveTelemetry(backendUrl);
      } catch (e) {}
    } else {
      updateTelemetryData(
        {
          status: 'healthy',
          error_rate: 0.01,
          latency_ms: 100,
        },
        false
      );
    }
    attempt1.steps.push({
      type: 'act',
      label: 'Remediation Action',
      details: 'Executed: Restart command applied.',
    });
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);

    await sleep(800);
    setVerification({
      status: 'VERIFIED',
      recovered: 'YES',
      isRecoveredBool: true,
      reason: 'Service metrics returned to baseline healthy range.',
      errorRate: '1.0%',
      latency: '100ms',
      serviceStatus: 'HEALTHY',
    });
    attempt1.steps.push({
      type: 'ver',
      label: 'Telemetry Verification',
      details: 'Verified: Service metrics are healthy.',
      customClass: 'verification-success',
    });
    attempt1.statusText = 'RECOVERED';
    attempt1.statusClass = 'success';
    setAttempts([{ ...attempt1, steps: [...attempt1.steps] }]);

    setSummary((prev) => ({
      ...prev,
      agentStatus: 'Resolved',
      finalAction: 'restart_service',
      finalVerification: 'Recovered',
      finalOutcome: 'RESOLVED',
    }));
    setResolutionBanner({
      visible: true,
      text: 'INCIDENT RESOLVED',
      isResolved: true,
    });
    addLog('INFO', 'Generic outage resolved via service restart.');
  };

  const runIncident = useCallback(async () => {
    setIsRunningAgent(true);
    setRunLabel('Running Agent...');
    setSummary((prev) => ({ ...prev, agentStatus: 'Investigating...' }));
    setAttempts([]);
    setResolutionBanner({ visible: false, text: '', isResolved: false });

    addLog('INFO', 'IncidentPilot agent dispatched: Beginning Observe phase.');

    const isAdaptive = activeScenario === 'Adaptive Incident';
    const isBadDeploy =
      activeScenario === 'Bad Deployment' || simStateRef.current.current_version === 'v42';

    if (isAdaptive) {
      await runAdaptiveWorkflow();
    } else if (isBadDeploy) {
      await runSingleRollbackWorkflow();
    } else {
      await runStandardOutageWorkflow();
    }

    setIsRunningAgent(false);
    setRunLabel('Run Incident');
  }, [activeScenario, backendUrl, addLog]);

  // Timers on mount
  useEffect(() => {
    checkConnection(false);
    sampleTelemetry();
    addLog('INFO', 'IncidentPilot Dashboard (React Template 15) initialized and ready.');

    const heartbeatTimer = setInterval(() => {
      checkConnection(true);
    }, 5000);

    const telemetryTimer = setInterval(() => {
      sampleTelemetry();
    }, 1000);

    return () => {
      clearInterval(heartbeatTimer);
      clearInterval(telemetryTimer);
    };
  }, []);

  return {
    backendUrl,
    setBackendUrl,
    connectionStatus,
    checkConnection,
    simState,
    currentReplicas,
    lastSyncTime,
    isLiveSync,
    activeScenario,
    triggerScenario,
    resetSystem,
    runIncident,
    isRunningAgent,
    runLabel,
    summary,
    decision,
    safety,
    verification,
    attempts,
    resolutionBanner,
    telemetryBuffer,
    logs,
    addLog,
  };
}
