import { useCallback, useEffect, useState } from 'react';
import { ApiError, DashboardSnapshot, getDashboardSnapshot } from '../services/incidentPilotApi';

type IncidentDataState = {
  data: DashboardSnapshot | null;
  error: string | null;
  loadedAt: Date | null;
  loading: boolean;
  refreshing: boolean;
};

const INITIAL_STATE: IncidentDataState = {
  data: null,
  error: null,
  loadedAt: null,
  loading: true,
  refreshing: false,
};

export function useIncidentSnapshot() {
  const [state, setState] = useState<IncidentDataState>(INITIAL_STATE);

  const refresh = useCallback(async (manual = false) => {
    setState((current) => ({
      ...current,
      error: null,
      loading: current.data === null,
      refreshing: current.data !== null && manual,
    }));

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 5_000);

    try {
      const data = await getDashboardSnapshot(controller.signal);
      setState({ data, error: null, loadedAt: new Date(), loading: false, refreshing: false });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Unable to load live incident data.';
      setState((current) => ({ ...current, error: message, loading: current.data === null ? false : current.loading, refreshing: false }));
    } finally {
      window.clearTimeout(timeoutId);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const intervalId = window.setInterval(() => void refresh(), 5_000);

    return () => window.clearInterval(intervalId);
  }, [refresh]);

  return { ...state, refresh: () => refresh(true) };
}
