import { useCallback, useEffect, useState } from 'react';
import { ApiError, getBackendHealth } from '../services/incidentPilotApi';

export type ConnectionStatus = 'connecting' | 'online' | 'offline';

type BackendConnection = {
  checkedAt: Date | null;
  message: string;
  status: ConnectionStatus;
};

const INITIAL_CONNECTION: BackendConnection = {
  checkedAt: null,
  message: 'Connecting to IncidentPilot API…',
  status: 'connecting',
};

export function useBackendConnection() {
  const [connection, setConnection] = useState<BackendConnection>(INITIAL_CONNECTION);

  const checkConnection = useCallback(async (showConnecting = true) => {
    if (showConnecting) {
      setConnection({ checkedAt: null, message: 'Connecting to IncidentPilot API…', status: 'connecting' });
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 4_000);

    try {
      await getBackendHealth(controller.signal);
      setConnection({ checkedAt: new Date(), message: 'IncidentPilot API connected', status: 'online' });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Unable to check the IncidentPilot API.';
      setConnection({ checkedAt: new Date(), message, status: 'offline' });
    } finally {
      window.clearTimeout(timeoutId);
    }
  }, []);

  useEffect(() => {
    void checkConnection();
    const intervalId = window.setInterval(() => void checkConnection(false), 10_000);

    return () => window.clearInterval(intervalId);
  }, [checkConnection]);

  return { connection, retry: () => checkConnection() };
}
