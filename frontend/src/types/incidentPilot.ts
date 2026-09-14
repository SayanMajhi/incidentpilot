/** API contracts and render models for the IncidentPilot dashboard. */

export type ScenarioId = 'healthy' | 'generic_outage' | 'bad_deployment' | 'adaptive_incident';

export const SCENARIO_LABELS: Record<ScenarioId, string> = {
  healthy: 'Normal / Healthy',
  generic_outage: 'Generic Outage',
  bad_deployment: 'Bad Deployment',
  adaptive_incident: 'Adaptive Incident',
};

export type AgentPhase =
  | 'idle'
  | 'observing'
  | 'incident_detected'
  | 'investigating'
  | 'diagnosing'
  | 'planning'
  | 'safety_check'
  | 'executing'
  | 'verifying'
  | 'replanning'
  | 'resolved'
  | 'blocked'
  | 'escalated'
  | 'failed'
  | 'complete';

export type IncidentStatus =
  | 'idle'
  | 'running'
  | 'no_incident'
  | 'resolved'
  | 'blocked'
  | 'escalated'
  | 'failed';

export type ActionType =
  | 'restart_service'
  | 'rollback_deployment'
  | 'scale_service'
  | 'escalate';

export interface ServiceState {
  status: 'healthy' | 'down' | 'degraded' | 'unknown';
  error_rate: number;
  latency_ms: number;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  current_version: string;
  replicas?: number | null;
  ready_replicas?: number | null;
  utilization?: number | null;
}

export interface MetricsResponse {
  error_rate: number;
  latency_ms: number;
  status: 'healthy' | 'down' | 'degraded' | 'unknown';
  cpu_percent?: number | null;
  memory_percent?: number | null;
  replicas?: number | null;
  ready_replicas?: number | null;
}

export interface RuntimeEnvironment {
  mode: 'simulator' | 'kubernetes' | string;
  supports_scenario_injection: boolean;
  namespace?: string;
  target?: string;
}

/** `GET /config` contains only public, enforced runtime settings. */
export interface RuntimeConfig {
  slo: {
    recovery_max_error_rate: number;
    recovery_max_latency_ms: number;
    incident_error_rate: number;
    incident_latency_ms: number;
  };
  replicas: { min: number; max: number };
  agent: { max_remediation_attempts: number };
  verification: { samples: number; interval_seconds: number };
  safety?: { allowed_namespace: string };
  environment: RuntimeEnvironment;
  simulator?: {
    healthy_error_rate?: number;
    healthy_latency_ms?: number;
    healthy_version?: string;
    bad_deployment_version?: string;
  };
  chart?: { latency_ceiling_ms?: number };
}

export interface SimulationActionResponse {
  message: string;
  state: ServiceState | null;
}

export interface ApiHealthResponse {
  status: 'ok';
  environment: string;
  version: string;
}

export interface BackendLogEntry {
  timestamp: string;
  level: string;
  message: string;
}

export interface BackendEvidence {
  id: string;
  source: string;
  signal: string;
  detail: string;
  value?: unknown;
  severity?: string;
  timestamp?: string;
}

export interface BackendCapacity {
  replicas: number;
  ready_replicas?: number;
  restart_count?: number;
  utilization?: number | null;
  telemetry?: string;
}

export interface BackendObservation {
  metrics: MetricsResponse;
  health: { status: string; is_healthy: boolean };
  capacity: BackendCapacity;
  logs: BackendLogEntry[];
  current_version: string;
  deployment_history: Array<Record<string, unknown>>;
  evidence?: BackendEvidence[];
}

export interface BackendDetection {
  incident_detected: boolean;
  signals: string[];
}

export interface BackendDiagnosis {
  probable_cause: string;
  summary: string;
  confidence: number;
  hypotheses?: Array<Record<string, unknown>>;
}

export interface BackendDecision {
  action: ActionType | string;
  target: string | number | null;
  reason: string;
  confidence: number;
  source?: string;
  fallback_reason?: string;
  arbitration_reason?: string;
  llm_proposal?: {
    action: string;
    target: string | number | null;
    reason: string;
    confidence: number;
  };
  deterministic_validation?: { status: 'accepted' | 'rejected'; reason: string };
}

export interface BackendSafetyDecision {
  checked: boolean;
  allowed: boolean | null;
  rule_id: string;
  reason: string;
  action: string;
  target?: string | number | null;
  namespace?: string;
  min_replicas?: number | null;
  max_replicas?: number | null;
  attempt?: number | null;
  max_attempts?: number | null;
  bounds?: { min_replicas?: number; max_replicas?: number };
  budget?: { attempt: number; maximum: number; remaining_after_this_attempt: number };
}

export interface BackendActionResult extends Record<string, unknown> {
  action: string;
  success: boolean;
  status: string;
  message: string;
  executed?: boolean;
  policy_allowed?: boolean;
}

export interface VerificationCheck {
  name?: string;
  passed: boolean;
  required?: boolean;
  observed?: unknown;
  threshold?: unknown;
  expected?: unknown;
  reason?: string;
  message?: string;
}

export interface BackendVerification {
  status: 'recovered' | 'partial' | 'failed';
  recovered: boolean;
  reason: string;
  observed_at?: string;
  checks?: Record<string, VerificationCheck> | VerificationCheck[];
  samples?: MetricsResponse[];
  deltas?: Record<string, number | null>;
  metrics_before?: MetricsResponse | null;
  metrics_after?: MetricsResponse | null;
  telemetry?: {
    metrics?: MetricsResponse;
    capacity?: BackendCapacity;
    samples?: number;
  } | null;
}

export interface BackendAttempt {
  attempt: number;
  observation?: BackendObservation;
  /** Compatibility with pre-typed controller results. */
  observations?: BackendObservation;
  evidence?: BackendEvidence[];
  new_evidence?: string[];
  evidence_after_action?: BackendEvidence[] | null;
  new_evidence_after_action?: string[] | null;
  detection?: BackendDetection;
  diagnosis?: BackendDiagnosis;
  proposal?: BackendDecision;
  /** Compatibility with the former field name. */
  decision?: BackendDecision;
  safety?: BackendSafetyDecision;
  /** Compatibility with the former field name. */
  safety_result?: BackendSafetyDecision;
  action_result?: BackendActionResult;
  verification?: BackendVerification | null;
}

export interface TimelineEvent {
  event_id: string;
  timestamp: string;
  incident_id: string;
  attempt: number | null;
  phase: AgentPhase | string;
  event_type: string;
  message: string;
  data: Record<string, unknown>;
}

export interface IncidentRun {
  run_id: string;
  incident_id?: string;
  goal: string;
  started_at: string;
  completed_at?: string | null;
  status: IncidentStatus;
  phase: AgentPhase | string;
  attempt: number;
  max_attempts?: number;
  attempts: BackendAttempt[];
  events?: TimelineEvent[];
  reason?: string | null;
  diagnosis?: BackendDiagnosis | null;
  selected_action?: BackendDecision | null;
  action_result?: BackendActionResult | null;
  verification?: BackendVerification | null;
}

export interface AgentRunState {
  run_id: string | null;
  incident_id?: string | null;
  goal: string | null;
  started_at: string | null;
  running: boolean;
  status: IncidentStatus;
  phase: AgentPhase | string;
  attempt: number;
  max_attempts: number;
  reason: string | null;
  updated_at?: string | null;
  details?: Record<string, unknown>;
}

export interface IncidentStatusResponse {
  revision: number;
  service: ServiceState;
  scenario: ScenarioId | string;
  environment: RuntimeEnvironment;
  agent: AgentRunState;
  latest_incident: IncidentRun | null;
  diagnostics: {
    logs: BackendLogEntry[];
    deployment_history: Array<Record<string, unknown>>;
  };
}

export interface TimelineResponse {
  revision: number;
  run_id: string | null;
  status: IncidentStatus;
  events: TimelineEvent[];
  attempts: BackendAttempt[];
  reason?: string | null;
}

export interface RunIncidentResponse {
  run_id: string;
  status: 'running';
  status_url: string;
  timeline_url: string;
}

export interface SafetyAssessment {
  assessment_id: string;
  executed: false;
  decision: BackendSafetyDecision;
  events: TimelineEvent[];
}

export interface TelemetryPoint {
  errorRate: number;
  latency: number;
  status: string;
}

export interface IncidentSummary {
  scenario: string;
  agentStatus: string;
  attempts: string;
  finalAction: string;
  finalVerification: string;
  finalOutcome: string;
  diagnosisCause: string;
  diagnosisSummary: string;
  evidence: string;
}

export interface DecisionDetails {
  source: string;
  action: string;
  target: string;
  confidence: string;
  reason: string;
  aiSuggestion: string;
  validation: string;
  validationReason: string;
}

export interface SafetyState {
  status: string;
  action: string;
  target: string;
  verdict: string;
  ruleId: string;
  reason: string;
  namespace: string;
  bounds: string;
  attemptBudget: string;
  executed: string;
}

export interface VerificationCheckView {
  id: string;
  label: string;
  passed: boolean;
  detail: string;
}

export interface VerificationState {
  status: string;
  recovered: string;
  isRecoveredBool: boolean | null;
  reason: string;
  errorRate: string;
  latency: string;
  serviceStatus: string;
  metricsBefore: string;
  metricsAfter: string;
  deltas: string;
  samples: string;
  checks: VerificationCheckView[];
}

export interface Attempt {
  id: string;
  number: number;
  tag: string;
  statusText: string;
  statusClass: 'running' | 'success' | 'retry' | 'blocked';
  actionSummary: string;
  evidenceSummary: string;
  inspector: {
    summary: IncidentSummary;
    decision: DecisionDetails;
    safety: SafetyState;
    verification: VerificationState;
    logs: LogEntry[];
  };
}

export interface ResolutionBanner {
  visible: boolean;
  text: string;
  isResolved: boolean;
}

export interface LogEntry {
  id: string;
  time: string;
  level: 'INFO' | 'WARNING' | 'ERROR';
  message: string;
}
