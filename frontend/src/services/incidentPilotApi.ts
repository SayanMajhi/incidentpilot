import type {
  HealthResponse,
  MetricsResponse,
  VersionResponse,
  SimulationActionResponse,
  IncidentStatusResponse,
  RunIncidentResponse,
} from '../types/incidentPilot';

export const DEFAULT_BASE_URL: string =
  typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL
    ? (import.meta.env.VITE_API_BASE_URL as string).trim().replace(/\/+$/, '')
    : 'http://127.0.0.1:8000';

export function normalizeBaseUrl(url?: string): string {
  if (!url || typeof url !== 'string') return DEFAULT_BASE_URL;
  return url.trim().replace(/\/+$/, '');
}

export async function apiFetch(
  baseUrl: string,
  endpoint: string,
  options: RequestInit = {},
  timeoutMs = 5000
): Promise<Response> {
  const cleanBase = normalizeBaseUrl(baseUrl);
  const targetUrl = `${cleanBase}${endpoint}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(targetUrl, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
    });
    clearTimeout(timeoutId);
    return response;
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}

async function readJson<T>(response: Response, label: string): Promise<T> {
  if (!response.ok) {
    let detail = `${label} returned ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Preserve the status-based error when the response has no JSON body.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function checkHealth(baseUrl: string): Promise<HealthResponse> {
  const res = await apiFetch(baseUrl, '/health');
  if (!res.ok) throw new Error(`Health check returned status ${res.status}`);
  return (await res.json()) as HealthResponse;
}

export async function fetchMetrics(baseUrl: string): Promise<MetricsResponse> {
  const res = await apiFetch(baseUrl, '/metrics');
  if (!res.ok) throw new Error(`Metrics returned status ${res.status}`);
  return (await res.json()) as MetricsResponse;
}

export async function fetchVersion(baseUrl: string): Promise<VersionResponse> {
  const res = await apiFetch(baseUrl, '/version');
  if (!res.ok) throw new Error(`Version returned status ${res.status}`);
  return (await res.json()) as VersionResponse;
}

export async function simulateOutage(baseUrl: string): Promise<SimulationActionResponse> {
  const res = await apiFetch(baseUrl, '/simulate/outage', { method: 'POST' });
  if (!res.ok) throw new Error(`Simulate outage returned ${res.status}`);
  return (await res.json()) as SimulationActionResponse;
}

export async function simulateBadDeployment(baseUrl: string): Promise<SimulationActionResponse> {
  const res = await apiFetch(baseUrl, '/simulate/bad-deployment', { method: 'POST' });
  if (!res.ok) throw new Error(`Simulate bad deployment returned ${res.status}`);
  return (await res.json()) as SimulationActionResponse;
}

export async function simulateAdaptiveIncident(baseUrl: string): Promise<SimulationActionResponse> {
  const res = await apiFetch(baseUrl, '/simulate/adaptive-incident', { method: 'POST' });
  return readJson<SimulationActionResponse>(res, 'Adaptive incident');
}

export async function simulateRecover(baseUrl: string): Promise<SimulationActionResponse> {
  const res = await apiFetch(baseUrl, '/simulate/recover', { method: 'POST' });
  if (!res.ok) throw new Error(`Simulate recover returned ${res.status}`);
  return (await res.json()) as SimulationActionResponse;
}

export async function simulateRollback(
  baseUrl: string,
  version: string = 'v41'
): Promise<SimulationActionResponse> {
  const res = await apiFetch(
    baseUrl,
    `/simulate/rollback?version=${encodeURIComponent(version)}`,
    { method: 'POST' }
  );
  if (!res.ok) throw new Error(`Simulate rollback returned ${res.status}`);
  return (await res.json()) as SimulationActionResponse;
}

export async function fetchStatus(baseUrl: string): Promise<IncidentStatusResponse> {
  const res = await apiFetch(baseUrl, '/status');
  return readJson<IncidentStatusResponse>(res, 'Status');
}

export async function runIncident(baseUrl: string): Promise<RunIncidentResponse> {
  const res = await apiFetch(baseUrl, '/run-incident', { method: 'POST' }, 15000);
  return readJson<RunIncidentResponse>(res, 'Incident run');
}

export async function resetIncident(baseUrl: string): Promise<SimulationActionResponse> {
  const res = await apiFetch(baseUrl, '/reset', { method: 'POST' });
  return readJson<SimulationActionResponse>(res, 'Reset');
}
