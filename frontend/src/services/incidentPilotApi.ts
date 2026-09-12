const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

export type BackendHealth = {
  status: string;
};

type ApiRecord = Record<string, unknown>;

export type DashboardSnapshot = {
  agent: {
    attempt: number | null;
    phase: string | null;
    running: boolean | null;
  };
  incident: {
    attempts: number | null;
    status: string | null;
    verification: string | null;
  };
  service: {
    errorRate: number | null;
    latencyMs: number | null;
    replicas: number | null;
    status: string | null;
    version: string | null;
  };
  timeline: Array<{
    attempt: number | null;
    label: string;
    outcome: 'blocked' | 'failed' | 'pending' | 'success' | 'unknown';
  }>;
};

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('The IncidentPilot API did not respond in time.');
    }

    throw new ApiError('Cannot reach the IncidentPilot API.');
  }

  if (!response.ok) {
    throw new ApiError(`IncidentPilot API returned ${response.status}.`);
  }

  return response.json() as Promise<T>;
}

function asRecord(value: unknown): ApiRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as ApiRecord : {};
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function formatLabel(event: ApiRecord): string {
  const eventName = asString(event.event);
  const action = asRecord(event.action);
  const decision = asRecord(event.decision);
  const actionName = asString(event.action) ?? asString(action.action) ?? asString(decision.action);

  const labels: Record<string, string> = {
    adaptation: 'Agent adapted to new evidence',
    decision: actionName ? `Decision: ${actionName.replace(/_/g, ' ')}` : 'Remediation decision made',
    incident_detected: 'Incident detected',
    investigation: 'Evidence investigated',
    remediation: actionName ? `Remediation: ${actionName.replace(/_/g, ' ')}` : 'Remediation executed',
    safety_check: 'Safety policy checked',
    verification: 'Recovery verified',
  };

  return eventName && labels[eventName] ? labels[eventName] : actionName ? `Action: ${actionName.replace(/_/g, ' ')}` : 'Agent update';
}

function getOutcome(event: ApiRecord): DashboardSnapshot['timeline'][number]['outcome'] {
  const status = asString(event.status);
  const verification = asRecord(event.verification);
  const action = asRecord(event.action);

  if (status === 'blocked') return 'blocked';
  if (status === 'failed' || asBoolean(action.success) === false || asBoolean(verification.recovered) === false) return 'failed';
  if (status === 'pending' || status === 'running') return 'pending';
  if (status === 'completed' || status === 'allowed' || asBoolean(action.success) === true || asBoolean(verification.recovered) === true) return 'success';
  return 'unknown';
}

function normalizeTimeline(value: unknown): DashboardSnapshot['timeline'] {
  const rawTimeline = Array.isArray(value) ? value : Array.isArray(asRecord(value).timeline) ? asRecord(value).timeline as unknown[] : [];

  return rawTimeline.map((item) => {
    const event = asRecord(item);
    return {
      attempt: asNumber(event.attempt),
      label: formatLabel(event),
      outcome: getOutcome(event),
    };
  });
}

export async function getDashboardSnapshot(signal?: AbortSignal): Promise<DashboardSnapshot> {
  const [rawStatus, rawTimeline] = await Promise.all([
    request<unknown>('/status', signal),
    request<unknown>('/timeline', signal),
  ]);
  const status = asRecord(rawStatus);
  const service = asRecord(status.service);
  const incident = asRecord(status.incident);
  const verification = asRecord(incident.verification);
  const agent = asRecord(status.agent);

  return {
    agent: {
      attempt: asNumber(agent.attempt),
      phase: asString(agent.phase),
      running: asBoolean(agent.running),
    },
    incident: {
      attempts: asNumber(incident.attempts),
      status: asString(incident.status),
      verification: asString(verification.reason),
    },
    service: {
      errorRate: asNumber(service.error_rate),
      latencyMs: asNumber(service.latency_ms),
      replicas: asNumber(status.replicas) ?? asNumber(service.replica_count),
      status: asString(service.status),
      version: asString(service.current_version),
    },
    timeline: normalizeTimeline(rawTimeline),
  };
}

export async function getBackendHealth(signal?: AbortSignal): Promise<BackendHealth> {
  const health = await request<BackendHealth>('/health', signal);

  if (health.status !== 'ok' && health.status !== 'healthy') {
    throw new ApiError('IncidentPilot API returned an unexpected health response.');
  }

  return health;
}
