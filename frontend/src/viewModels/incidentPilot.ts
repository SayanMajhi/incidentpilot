import { SCENARIO_LABELS } from '../types/incidentPilot';
import type {
  AgentRunState,
  Attempt,
  BackendAttempt,
  BackendDecision,
  BackendLogEntry,
  BackendSafetyDecision,
  BackendVerification,
  DecisionDetails,
  IncidentStatus,
  IncidentSummary,
  LogEntry,
  ResolutionBanner,
  RuntimeConfig,
  SafetyAssessment,
  SafetyState,
  ScenarioId,
  VerificationCheck,
  VerificationState,
} from '../types/incidentPilot';

export const FALLBACK_CONFIG: RuntimeConfig = {
  slo: {
    recovery_max_error_rate: 0.05,
    recovery_max_latency_ms: 200,
    incident_error_rate: 0.1,
    incident_latency_ms: 300,
  },
  replicas: { min: 1, max: 3 },
  agent: { max_remediation_attempts: 3 },
  verification: { samples: 3, interval_seconds: 1 },
  environment: { mode: 'simulator', supports_scenario_injection: true },
};

export const DEFAULT_GOAL = 'Restore the service to configured SLOs while respecting safety constraints.';

export const EMPTY_SUMMARY: IncidentSummary = {
  scenario: 'None',
  agentStatus: 'Idle',
  attempts: '0',
  finalAction: 'None',
  finalVerification: 'Pending',
  finalOutcome: 'None',
  diagnosisCause: 'None',
  diagnosisSummary: 'No diagnosis has been produced.',
  evidence: 'None',
};

export const EMPTY_DECISION: DecisionDetails = {
  source: 'none',
  action: 'None',
  target: 'None',
  confidence: '0%',
  reason: 'No action has been proposed.',
  aiSuggestion: 'Not used',
  validation: 'Deterministic mode',
  validationReason: 'No model proposal was requested.',
};

export const EMPTY_SAFETY: SafetyState = {
  status: 'UNCHECKED',
  action: 'None',
  target: 'None',
  verdict: 'Pending',
  ruleId: 'None',
  reason: 'Awaiting a proposed action.',
  namespace: '—',
  bounds: '—',
  attemptBudget: '—',
  executed: 'No action requested',
};

export const EMPTY_VERIFICATION: VerificationState = {
  status: 'UNVERIFIED',
  recovered: 'Pending',
  isRecoveredBool: null,
  reason: 'No remediation has been verified.',
  errorRate: '—',
  latency: '—',
  serviceStatus: '—',
  metricsBefore: '—',
  metricsAfter: '—',
  deltas: '—',
  samples: '—',
  checks: [],
};

export function idleAgent(config: RuntimeConfig = FALLBACK_CONFIG): AgentRunState {
  return {
    run_id: null,
    goal: DEFAULT_GOAL,
    started_at: null,
    running: false,
    status: 'idle',
    phase: 'idle',
    attempt: 0,
    max_attempts: config.agent.max_remediation_attempts,
    reason: null,
  };
}

export function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function scenarioLabel(scenario: string): string {
  return SCENARIO_LABELS[scenario as ScenarioId] || titleCase(scenario);
}

const PHASE_LABELS: Record<string, string> = {
  idle: 'Idle',
  observing: 'Observing live state…',
  incident_detected: 'Incident detected',
  investigating: 'Investigating evidence…',
  diagnosing: 'Diagnosing probable cause…',
  planning: 'Planning remediation…',
  safety_check: 'Checking deterministic policy…',
  executing: 'Executing remediation…',
  verifying: 'Verifying recovery…',
  replanning: 'Replanning from fresh evidence…',
  resolved: 'Resolved',
  blocked: 'Blocked by policy',
  escalated: 'Escalated',
  failed: 'Run failed',
  complete: 'Complete',
};

export function phaseLabel(agent: AgentRunState): string {
  const label = PHASE_LABELS[agent.phase] || titleCase(agent.phase);
  return agent.running && agent.attempt > 0 ? `${label} (attempt ${agent.attempt})` : label;
}

export function formatTarget(target: string | number | null | undefined): string {
  if (target === null || target === undefined) return 'None';
  return typeof target === 'number' ? `${target} replicas` : String(target);
}

function actionLabel(action: string, target: string | number | null | undefined): string {
  if (action === 'restart_service') return 'Restart service';
  if (action === 'rollback_deployment') return `Rollback deployment → ${formatTarget(target)}`;
  if (action === 'scale_service') return `Scale service → ${formatTarget(target)}`;
  if (action === 'escalate') return 'Escalate to an operator';
  return titleCase(action);
}

function formatMetric(metrics: { error_rate: number; latency_ms: number; status: string } | null | undefined): string {
  if (!metrics) return 'unavailable';
  return `${(metrics.error_rate * 100).toFixed(1)}% errors · ${metrics.latency_ms}ms · ${metrics.status}`;
}

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined) return 'unavailable';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number' || typeof value === 'string') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function mapLogs(entries: BackendLogEntry[] = []): LogEntry[] {
  return entries.map((entry, index) => ({
    id: `${entry.timestamp}-${index}`,
    time: entry.timestamp.includes('T') ? entry.timestamp.slice(11, 19) : entry.timestamp,
    level: entry.level === 'ERROR' ? 'ERROR' : entry.level === 'WARNING' ? 'WARNING' : 'INFO',
    message: entry.message,
  }));
}

export function mapDecision(decision?: BackendDecision | null): DecisionDetails {
  if (!decision) return EMPTY_DECISION;
  const proposal = decision.llm_proposal;
  const validation = decision.deterministic_validation;
  return {
    source: decision.source === 'llm' ? 'Qwen-assisted' : decision.source || 'deterministic',
    action: actionLabel(decision.action, decision.target),
    target: formatTarget(decision.target),
    confidence: `${(decision.confidence * 100).toFixed(0)}%`,
    reason: decision.reason,
    aiSuggestion: proposal
      ? `${actionLabel(proposal.action, proposal.target)} (${(proposal.confidence * 100).toFixed(0)}%)`
      : 'Not used',
    validation: validation?.status.toUpperCase() || (proposal ? 'REJECTED' : 'Deterministic mode'),
    validationReason: validation?.reason || decision.arbitration_reason || decision.fallback_reason || 'No model proposal was requested.',
  };
}

export function mapSafety(
  safety: BackendSafetyDecision | undefined,
  config: RuntimeConfig,
  executed?: boolean,
): SafetyState {
  if (!safety) return EMPTY_SAFETY;
  const min = safety.bounds?.min_replicas ?? safety.min_replicas ?? config.replicas.min;
  const max = safety.bounds?.max_replicas ?? safety.max_replicas ?? config.replicas.max;
  const attempt = safety.budget?.attempt ?? safety.attempt;
  const maxAttempts = safety.budget?.maximum ?? safety.max_attempts ?? config.agent.max_remediation_attempts;
  return {
    status: safety.allowed ? 'ALLOWED' : 'BLOCKED',
    action: actionLabel(safety.action, safety.target),
    target: formatTarget(safety.target),
    verdict: safety.allowed ? 'ALLOWED' : 'BLOCKED',
    ruleId: safety.rule_id,
    reason: safety.reason,
    namespace: safety.namespace || config.safety?.allowed_namespace || config.environment.namespace || 'incidentpilot',
    bounds: `${min}–${max} replicas`,
    attemptBudget: attempt == null ? `${maxAttempts} maximum` : `${attempt} of ${maxAttempts}`,
    executed: executed === undefined ? 'Pending execution result' : executed ? 'Yes' : 'No',
  };
}

function mapCheck(id: string, check: VerificationCheck) {
  const expected = check.expected ?? check.threshold;
  const threshold = expected === undefined ? '' : ` · expected ${stringifyValue(expected)}`;
  const reasonText = check.message || check.reason;
  const reason = reasonText ? ` · ${reasonText}` : '';
  return {
    id,
    label: titleCase(check.name || id),
    passed: check.passed,
    detail: `Observed ${stringifyValue(check.observed)}${threshold}${reason}`,
  };
}

export function mapVerification(verification?: BackendVerification | null): VerificationState {
  if (!verification) return EMPTY_VERIFICATION;
  const after = verification.metrics_after || verification.telemetry?.metrics;
  const samples = verification.samples;
  const sampleCount = samples?.length ?? verification.telemetry?.samples;
  const deltas = verification.deltas
    ? Object.entries(verification.deltas).map(([key, value]) => `${titleCase(key)} ${stringifyValue(value)}`).join(' · ')
    : 'unavailable';
  return {
    status: verification.status.toUpperCase(),
    recovered: verification.recovered ? 'YES' : 'NO',
    isRecoveredBool: verification.recovered,
    reason: verification.reason,
    errorRate: after ? `${(after.error_rate * 100).toFixed(1)}%` : 'unavailable',
    latency: after ? `${after.latency_ms}ms` : 'unavailable',
    serviceStatus: after?.status?.toUpperCase() || 'UNKNOWN',
    metricsBefore: formatMetric(verification.metrics_before),
    metricsAfter: formatMetric(after),
    deltas,
    samples: sampleCount == null ? 'unavailable' : `${sampleCount} fresh sample${sampleCount === 1 ? '' : 's'}`,
    checks: Array.isArray(verification.checks)
      ? verification.checks.map((check, index) => mapCheck(check.name || String(index + 1), check))
      : Object.entries(verification.checks || {}).map(([id, check]) => mapCheck(id, check)),
  };
}

function attemptObservation(attempt: BackendAttempt) {
  return attempt.observation || attempt.observations;
}

function attemptDecision(attempt: BackendAttempt) {
  return attempt.proposal || attempt.decision;
}

function attemptSafety(attempt: BackendAttempt) {
  return attempt.safety || attempt.safety_result;
}

export function mapAttempt(
  attempt: BackendAttempt,
  total: number,
  scenario: string,
  config: RuntimeConfig,
): Attempt {
  const observation = attemptObservation(attempt);
  const decision = attemptDecision(attempt);
  const safety = attemptSafety(attempt);
  const verification = attempt.verification;
  const diagnosis = attempt.diagnosis;
  const evidence = attempt.evidence || observation?.evidence || [];
  const evidenceSummary = evidence.length
    ? evidence.map((item) => `${item.id}: ${item.detail}`).join(' ')
    : 'No causal evidence was recorded.';
  const actionExecuted = attempt.action_result?.executed ?? attempt.action_result?.success;
  const statusClass: Attempt['statusClass'] = safety?.allowed === false
    ? 'blocked'
    : verification?.recovered
      ? 'success'
      : verification || attempt.action_result?.success === false
        ? 'retry'
        : 'running';
  const statusText = safety?.allowed === false
    ? 'BLOCKED'
    : verification
      ? verification.status.toUpperCase()
      : attempt.action_result
        ? attempt.action_result.status.toUpperCase()
        : 'IN PROGRESS';
  const decisionView = mapDecision(decision);
  const verificationView = mapVerification(verification);
  return {
    id: `attempt-${attempt.attempt}`,
    number: attempt.attempt,
    tag: `ATTEMPT ${attempt.attempt}`,
    statusText,
    statusClass,
    actionSummary: decision ? actionLabel(decision.action, decision.target) : 'No action proposed yet',
    evidenceSummary,
    inspector: {
      summary: {
        scenario: scenarioLabel(scenario),
        agentStatus: statusText,
        attempts: `${attempt.attempt} of ${total}`,
        finalAction: decisionView.action,
        finalVerification: verification ? titleCase(verification.status) : 'Not run',
        finalOutcome: statusText,
        diagnosisCause: diagnosis ? titleCase(diagnosis.probable_cause) : 'Pending',
        diagnosisSummary: diagnosis?.summary || 'Diagnosis has not completed.',
        evidence: evidenceSummary,
      },
      decision: decisionView,
      safety: mapSafety(safety, config, actionExecuted),
      verification: verificationView,
      logs: mapLogs(observation?.logs),
    },
  };
}

export function buildIncidentView(
  attemptsData: BackendAttempt[],
  status: IncidentStatus,
  reason: string | null | undefined,
  scenario: string,
  agent: AgentRunState,
  config: RuntimeConfig,
) {
  const attempts = attemptsData.map((attempt) => mapAttempt(attempt, attemptsData.length, scenario, config));
  const latest = attempts[attempts.length - 1];
  const terminal = status !== 'running' && status !== 'idle';
  if (!latest) {
    const noIncident = status === 'no_incident';
    return {
      attempts,
      summary: {
        ...EMPTY_SUMMARY,
        scenario: scenarioLabel(scenario),
        agentStatus: agent.running ? phaseLabel(agent) : titleCase(status),
        finalVerification: noIncident ? 'Not required' : 'Pending',
        finalOutcome: noIncident ? 'NO INCIDENT' : status === 'idle' ? 'None' : titleCase(status),
        diagnosisSummary: noIncident ? (reason || 'Live telemetry is within incident thresholds.') : EMPTY_SUMMARY.diagnosisSummary,
      },
      decision: EMPTY_DECISION,
      safety: EMPTY_SAFETY,
      verification: EMPTY_VERIFICATION,
      resolutionBanner: {
        visible: terminal,
        text: noIncident ? 'NO INCIDENT — SERVICE IS WITHIN CONFIGURED THRESHOLDS' : `INCIDENT ${status.toUpperCase()}`,
        isResolved: noIncident,
      } satisfies ResolutionBanner,
    };
  }

  const summary: IncidentSummary = {
    ...latest.inspector.summary,
    agentStatus: agent.running ? phaseLabel(agent) : titleCase(status),
    attempts: String(attempts.length),
    finalOutcome: agent.running ? 'RUNNING' : status.toUpperCase(),
  };
  const bannerText = status === 'resolved'
    ? 'INCIDENT RECOVERED — VERIFIED AGAINST FRESH TELEMETRY'
    : status === 'blocked'
      ? `INCIDENT BLOCKED BY SAFETY POLICY — ${reason || latest.inspector.safety.reason}`
      : status === 'escalated'
        ? `INCIDENT ESCALATED — ${reason || 'Human investigation required'}`
        : status === 'failed'
          ? `INCIDENT RUN FAILED — ${reason || 'Internal agent error'}`
          : '';

  return {
    attempts,
    summary,
    decision: latest.inspector.decision,
    safety: latest.inspector.safety,
    verification: latest.inspector.verification,
    resolutionBanner: {
      visible: terminal,
      text: bannerText,
      isResolved: status === 'resolved',
    } satisfies ResolutionBanner,
  };
}

export function mapSafetyAssessment(assessment: SafetyAssessment, config: RuntimeConfig): SafetyState {
  return mapSafety(assessment.decision, config, assessment.executed);
}
