import React from 'react';

interface BackendAlertProps {
  backendUrl: string;
  isOffline: boolean;
  onRetry: () => void;
}

export const BackendAlert: React.FC<BackendAlertProps> = ({ backendUrl, isOffline, onRetry }) => {
  if (!isOffline) return null;

  return (
    <div className="offline-banner active" id="offlineBanner" role="alert">
      <div>
        <strong>FastAPI Backend Offline or Unreachable:</strong> No active server responding at{' '}
        <span id="offlineUrlDisplay">{backendUrl}</span>. Launch your simulated production service
        using: <code>.venv\Scripts\python -m uvicorn simulator.service:app --port 8000</code>
      </div>
      <button
        className="btn-reconnect"
        id="btnRetryBanner"
        type="button"
        onClick={() => onRetry()}
      >
        Retry Connection
      </button>
    </div>
  );
};
