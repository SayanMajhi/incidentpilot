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
  current_version: string;
}

export interface MetricsResponse {
  error_rate: number;
  latency_ms: number;
  status: 'healthy' | 'down';
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
  running: boolean;
  phase: string;
  attempt: number;
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
}

export interface DecisionDetails {
  source: string;
  action: string;
  target: string;
  confidence: string;
  reason: string;
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
}

export interface AttemptStep {
  type: 'obs' | 'inv' | 'diag' | 'dec' | 'safe' | 'act' | 'ver' | 'adapt';
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
}

export interface BackendVerification {
  recovered: boolean;
  reason: string;
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
    logs: BackendLogEntry[];
    current_version: string;
    deployment_history: Array<Record<string, unknown>>;
    previous_attempt?: Record<string, unknown>;
  };
  detection: BackendDetection;
  diagnosis: BackendDiagnosis;
  decision: BackendDecision;
  safety_result: BackendSafetyResult;
  action_result: BackendActionResult;
  verification: BackendVerification | null;
}

export type IncidentStatus = 'resolved' | 'unresolved' | 'blocked' | 'escalated' | 'idle';

export interface IncidentResult {
  attempts: BackendAttempt[];
  status: Exclude<IncidentStatus, 'idle'>;
  decision: BackendDecision;
  action_result: BackendActionResult;
  verification: BackendVerification | null;
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
  agent: AgentRunState;
  attempt_count: number;
  timeline: BackendAttempt[];
}

export interface RunIncidentResponse {
  status: IncidentResult['status'];
  result: IncidentResult;
}
