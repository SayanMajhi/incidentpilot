export interface ServiceState {
  status: 'healthy' | 'down' | 'degraded' | 'unknown';
  error_rate: number;
  latency_ms: number;
  current_version: string;
}

export interface HealthResponse {
  status: 'healthy' | 'down';
}

export interface MetricsResponse {
  error_rate: number;
  latency_ms: number;
  status: 'healthy' | 'down';
}

export interface VersionResponse {
  current_version: string;
}

export interface SimulationActionResponse {
  message: string;
  state: ServiceState;
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

export interface BackendAttempt {
  attempt: number;
  observations: {
    metrics: MetricsResponse;
    health: { status: string; is_healthy: boolean };
    logs: Array<{ timestamp: string; level: string; message: string }>;
    current_version: string;
    deployment_history: Array<Record<string, unknown>>;
    previous_attempt?: Record<string, unknown>;
  };
  detection: BackendDetection;
  diagnosis: BackendDiagnosis;
  decision: BackendDecision;
  safety_result: { action: string; checked: boolean; allowed: boolean | null };
  action_result: Record<string, unknown> & { action: string; success: boolean; status: string; message: string };
  verification: BackendVerification | null;
}

export interface IncidentResult {
  attempts: BackendAttempt[];
  status: 'resolved' | 'unresolved' | 'blocked' | 'escalated';
  decision: BackendDecision;
  action_result: BackendAttempt['action_result'];
  verification: BackendVerification | null;
}

export interface IncidentStatusResponse {
  service: ServiceState;
  scenario: string;
  replicas: number;
  agent: {
    running: boolean;
    phase: string;
    attempt: number;
    updated_at: string | null;
    details: Record<string, unknown>;
  };
  diagnostics: {
    logs: Array<{ timestamp: string; level: string; message: string }>;
    deployment_history: Array<Record<string, unknown>>;
  };
  incident: IncidentResult | null;
}

export interface RunIncidentResponse {
  status: IncidentResult['status'];
  result: IncidentResult;
}
