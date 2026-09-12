import React from 'react';

interface HeaderProps {
  backendUrl: string;
  onUrlChange: (newUrl: string) => void;
  connectionStatus: 'connected' | 'offline' | 'checking';
  onPing: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  backendUrl,
  onUrlChange,
  connectionStatus,
  onPing,
}) => {
  const isChecking = connectionStatus === 'checking';
  const isConnected = connectionStatus === 'connected';

  let pillClass = 'pill-connection offline';
  let pillText = 'DISCONNECTED';

  if (isChecking) {
    pillClass = 'pill-connection checking';
    pillText = 'CHECKING';
  } else if (isConnected) {
    pillClass = 'pill-connection connected';
    pillText = 'CONNECTED';
  }

  return (
    <header>
      <div className="brand-cluster">
        <div className="brand-icon" aria-hidden="true">
          IP
        </div>
        <div className="brand-titles">
          <h1>IncidentPilot</h1>
          <p>Autonomous Incident Response System</p>
        </div>
      </div>

      <div className="backend-bridge">
        <label htmlFor="backendUrl" className="bridge-label">
          API TARGET:
        </label>
        <input
          type="text"
          id="backendUrl"
          className="bridge-input"
          value={backendUrl}
          onChange={(e) => onUrlChange(e.target.value)}
          aria-label="Backend FastAPI URL"
        />
        <div className={pillClass} id="connectionPill">
          <span className="dot" aria-hidden="true"></span>
          <span id="connectionText">{pillText}</span>
        </div>
        <button
          className="btn-reconnect"
          id="btnPing"
          type="button"
          onClick={() => onPing()}
          aria-label="Test Backend Connection"
        >
          Ping API
        </button>
      </div>
    </header>
  );
};
