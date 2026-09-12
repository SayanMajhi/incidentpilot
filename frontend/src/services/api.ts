import type {
  IncidentStatusResponse,
  RunIncidentResponse,
  RuntimeConfig,
  SimulationActionResponse,
  TimelineResponse,
} from '../types/incidentPilot';

const ENV_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined;
const FALLBACK_BASE_URL = 'http://127.0.0.1:8000';

export const DEFAULT_BASE_URL = normalizeBaseUrl(ENV_BASE_URL || FALLBACK_BASE_URL);

/** Default request budget. `/run-incident` runs the whole bounded loop, so it
 *  is given a much longer one. */
const DEFAULT_TIMEOUT_MS = 5_000;
const RUN_INCIDENT_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function normalizeBaseUrl(url?: string): string {
  const value = url?.trim();
  return value ? value.replace(/\/+$/, '') : FALLBACK_BASE_URL;
}

interface RequestOptions extends RequestInit {
  /** Caller-owned signal, so an unmount or a superseded poll can cancel. */
  signal?: AbortSignal | null;
  timeoutMs?: number;
}

async function request<T>(baseUrl: string, endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal: callerSignal, ...init } = options;

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const abortFromCaller = () => controller.abort();
  callerSignal?.addEventListener('abort', abortFromCaller);

  try {
    const response = await fetch(`${normalizeBaseUrl(baseUrl)}${endpoint}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers,
      },
    });

    if (!response.ok) {
      let message = `IncidentPilot API returned ${response.status}.`;
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === 'string' && body.detail.trim()) message = body.detail;
      } catch {
        // Keep the status-based message when the response has no JSON error body.
      }
      throw new ApiError(message, response.status);
    }

    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError('IncidentPilot API returned an invalid JSON response.', response.status);
    }
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (callerSignal?.aborted) throw new ApiError('The IncidentPilot API request was cancelled.');
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('The IncidentPilot API request timed out.');
    }
    throw new ApiError('Cannot reach the IncidentPilot API.');
  } finally {
    window.clearTimeout(timeoutId);
    callerSignal?.removeEventListener('abort', abortFromCaller);
  }
}

/** Thresholds and bounds the backend enforces, so the UI never hardcodes them. */
export function fetchConfig(baseUrl: string, signal?: AbortSignal): Promise<RuntimeConfig> {
  return request<RuntimeConfig>(baseUrl, '/config', { signal });
}

export function fetchStatus(baseUrl: string, signal?: AbortSignal): Promise<IncidentStatusResponse> {
  return request<IncidentStatusResponse>(baseUrl, '/status', { signal });
}

export function fetchTimeline(baseUrl: string, signal?: AbortSignal): Promise<TimelineResponse> {
  return request<TimelineResponse>(baseUrl, '/timeline', { signal });
}

export function simulateOutage(baseUrl: string, signal?: AbortSignal): Promise<SimulationActionResponse> {
  return request<SimulationActionResponse>(baseUrl, '/simulate/outage', { method: 'POST', signal });
}

export function simulateBadDeployment(baseUrl: string, signal?: AbortSignal): Promise<SimulationActionResponse> {
  return request<SimulationActionResponse>(baseUrl, '/simulate/bad-deployment', { method: 'POST', signal });
}

export function simulateAdaptiveIncident(baseUrl: string, signal?: AbortSignal): Promise<SimulationActionResponse> {
  return request<SimulationActionResponse>(baseUrl, '/simulate/adaptive-incident', { method: 'POST', signal });
}

export function runIncident(baseUrl: string, signal?: AbortSignal): Promise<RunIncidentResponse> {
  return request<RunIncidentResponse>(baseUrl, '/run-incident', {
    method: 'POST',
    signal,
    timeoutMs: RUN_INCIDENT_TIMEOUT_MS,
  });
}

export function resetIncident(baseUrl: string, signal?: AbortSignal): Promise<SimulationActionResponse> {
  return request<SimulationActionResponse>(baseUrl, '/reset', { method: 'POST', signal });
}
