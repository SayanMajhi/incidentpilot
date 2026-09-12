import type {
  HealthResponse,
  MetricsResponse,
  VersionResponse,
  SimulationActionResponse,
} from '../types/incidentPilot';

export const DEFAULT_BASE_URL: string =
  typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL
    ? (import.meta.env.VITE_API_BASE_URL as string).trim().replace(/\/+$/, '')
    : 'http://localhost:8000';

export function normalizeBaseUrl(url?: string): string {
  if (!url || typeof url !== 'string') return DEFAULT_BASE_URL;
  return url.trim().replace(/\/+$/, '');
}

export async function apiFetch(
  baseUrl: string,
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const cleanBase = normalizeBaseUrl(baseUrl);
  const targetUrl = `${cleanBase}${endpoint}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);

  try {
    const response = await fetch(targetUrl, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
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
