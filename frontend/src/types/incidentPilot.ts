/** Shared types for the IncidentPilot dashboard.
 *
 * The `Backend*` types mirror the FastAPI response shapes exactly; everything
 * else is the view model the hook derives for the components.
 */

/** Scenario identifiers as the backend reports and accepts them. */
export type ScenarioId = 'healthy' | 'generic_outage' | 'bad_deployment' | 'adaptive_incident';

export const SCENARIO_LABELS: Record<ScenarioId, string> = {
  healthy: 'Normal / Healthy',
  generic_outage: 'Generic Outage',
  bad_deployment: 'Bad Deployment',
  adaptive_incident: 'Adaptive Incident',
};

export interface ServiceState {
  status: 'healthy' | 'down' | 'degraded' | 'unknown';
  error_rate: number;
  latency_ms: number;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  current_version: string;
}

export interface MetricsResponse {
  error_rate: number;
  latency_ms: number;
  status: 'healthy' | 'down';
  cpu_percent?: number | null;
  memory_percent?: number | null;
  replicas?: number | null;
  ready_replicas?: number | null;
}

export interface SimulationActionResponse {
  message: string;
  state: ServiceState;
}

/** `GET /config` — the thresholds and bounds the backend actually enforces. */
export interface RuntimeConfig {
  recovery: { max_error_rate: number; max_latency_ms: number };
  elevated: { error_rate: number; latency_ms: number };
  replicas: { min: number; max: number };
  baseline: { error_rate: number; latency_ms: number; version: string };
  chart: { latency_ceiling_ms: number };
  bad_deployment_version: string;
}

export interface AgentRunState {
  run_id: string | null;
  goal: string;
  started_at: string | null;
  running: boolean;
  status: IncidentStatus | 'running';
  phase: string;
  attempt: number;
  max_attempts: number;
  history: BackendAttempt[];
  reason: string | null;
  updated_at: string | null;
  details: Record<string, unknown>;
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
  diagnosis: string;
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
  verdict: string;
  reason: string;
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
}

export interface AttemptStep {
  type: 'obs' | 'inv' | 'diag' | 'dec' | 'safe' | 'act' | 'ver' | 'result' | 'adapt';
  label: string;
  details: string;
  customClass?: string;
}

export interface Attempt {
  id: string;
  number: number;
  tag: string;
  statusText: string;
  statusClass: 'running' | 'success' | 'retry';
  steps: AttemptStep[];
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

export interface BackendLogEntry {
  timestamp: string;
  level: string;
  message: string;
}

export interface BackendDetection {
  incident_detected: boolean;
  signals: string[];
}

export interface BackendDiagnosis {
  probable_cause: string;
  summary: string;
  confidence: number;
}

export interface BackendDecision {
  action: string;
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
  deterministic_validation?: {
    status: 'accepted' | 'rejected';
    reason: string;
  };
}

export interface BackendVerification {
  recovered: boolean;
  reason: string;
  status?: 'recovered' | 'failed';
  metrics_before?: MetricsResponse | null;
  metrics_after?: MetricsResponse | null;
  telemetry?: {
    metrics?: MetricsResponse;
    capacity?: BackendCapacity;
    samples?: number;
  } | null;
}

export interface BackendEvidence {
  id: string;
  source: string;
  signal: string;
  detail: string;
}

export interface BackendCapacity {
  replicas: number;
  ready_replicas?: number;
  restart_count?: number;
  utilization?: number | null;
  telemetry?: string;
}

export interface BackendSafetyResult {
  action: string;
  checked: boolean;
  allowed: boolean | null;
}

export interface BackendActionResult extends Record<string, unknown> {
  action: string;
  success: boolean;
  status: string;
  message: string;
  /** The deterministic policy gate's verdict, distinct from `success`. */
  policy_allowed?: boolean;
}

export interface BackendAttempt {
  attempt: number;
  observations: {
    metrics: MetricsResponse;
    health: { status: string; is_healthy: boolean };
    capacity: BackendCapacity;
    logs: BackendLogEntry[];
    current_version: string;
    deployment_history: Array<Record<string, unknown>>;
    evidence?: BackendEvidence[];
    previous_attempt?: Record<string, unknown>;
  };
  evidence?: BackendEvidence[];
  new_evidence?: string[];
  evidence_after_action?: BackendEvidence[] | null;
  new_evidence_after_action?: string[] | null;
  detection: BackendDetection;
  diagnosis: BackendDiagnosis;
  decision: BackendDecision;
  safety_result: BackendSafetyResult;
  action_result: BackendActionResult;
  verification: BackendVerification | null;
}

export type IncidentStatus = 'resolved' | 'unresolved' | 'blocked' | 'escalated' | 'idle';

export interface IncidentResult {
  run_id: string;
  goal: string;
  started_at: string;
  completed_at: string;
  phase: string;
  attempt: number;
  history: BackendAttempt[];
  attempts: BackendAttempt[];
  status: Exclude<IncidentStatus, 'idle'>;
  decision: BackendDecision;
  action_result: BackendActionResult;
  verification: BackendVerification | null;
  reason: string | null;
}

/** `GET /status` — live service state plus the agent's live run progress. */
export interface IncidentStatusResponse {
  service: ServiceState;
  scenario: ScenarioId | string;
  replicas: number;
  agent: AgentRunState;
  diagnostics: {
    logs: BackendLogEntry[];
    deployment_history: Array<Record<string, unknown>>;
  };
  incident: IncidentResult | null;
}

/** `GET /timeline` — the render-ready execution history for the timeline. */
export interface TimelineResponse {
  status: IncidentStatus;
  run_id: string | null;
  goal: string;
  started_at: string | null;
  reason: string | null;
  agent: AgentRunState;
  attempt_count: number;
  timeline: BackendAttempt[];
}

export interface RunIncidentResponse {
  status: IncidentResult['status'];
  result: IncidentResult;
}
