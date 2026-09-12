import React, { useEffect, useState } from 'react';

interface HeaderProps {
  backendUrl: string;
  /** Called only once the user commits the value (blur, Enter, or Ping). */
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
  // The input is a local draft. Committing on every keystroke would restart
  // the poll loop and fire a request against every truncated prefix of the URL.
  const [draftUrl, setDraftUrl] = useState(backendUrl);
  useEffect(() => { setDraftUrl(backendUrl); }, [backendUrl]);

  const isChecking = connectionStatus === 'checking';
  const isConnected = connectionStatus === 'connected';
  const isDirty = draftUrl.trim() !== backendUrl;

  let pillClass = 'pill-connection offline';
  let pillText = 'DISCONNECTED';

  if (isChecking) {
    pillClass = 'pill-connection checking';
    pillText = 'CHECKING';
  } else if (isConnected) {
    pillClass = 'pill-connection connected';
    pillText = 'CONNECTED';
  }

  const commit = () => {
    if (isDirty) onUrlChange(draftUrl);
  };

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
          type="url"
          id="backendUrl"
          className="bridge-input"
          value={draftUrl}
          onChange={(event) => setDraftUrl(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              commit();
            }
          }}
          spellCheck={false}
          autoComplete="off"
          aria-label="Backend FastAPI URL"
          aria-describedby="backendUrlHint"
        />
        <span className="visually-hidden" id="backendUrlHint">
          Press Enter to apply a new API target.
        </span>
        <div className={pillClass} id="connectionPill">
          <span className="dot" aria-hidden="true"></span>
          <span id="connectionText">{pillText}</span>
        </div>
        <button
          className="btn-reconnect"
          id="btnPing"
          type="button"
          onClick={() => {
            commit();
            onPing();
          }}
          aria-label="Test Backend Connection"
        >
          Ping API
        </button>
      </div>
    </header>
  );
};
