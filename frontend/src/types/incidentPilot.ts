export interface ServiceState {
  status: 'healthy' | 'down' | 'degraded';
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
  type: 'obs' | 'dec' | 'safe' | 'act' | 'ver' | 'adapt';
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
