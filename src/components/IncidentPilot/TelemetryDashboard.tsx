import React from 'react';
import type { ServiceState } from '../../types/incidentPilot';

interface TelemetryDashboardProps {
  simState: ServiceState;
  currentReplicas: number;
  lastSyncTime: string;
}

export const TelemetryDashboard: React.FC<TelemetryDashboardProps> = ({
  simState,
  currentReplicas,
  lastSyncTime,
}) => {
  const status = simState.status || 'healthy';
  const isDown = status === 'down';
  const statusDesc = isDown
    ? 'Active production incident detected'
    : 'All SLO objectives nominal';

  const errRateNum = typeof simState.error_rate === 'number' ? simState.error_rate : 0.01;
  const errRateFormatted = (errRateNum * 100).toFixed(1) + '%';
  const isErrSpike = errRateNum > 0.1;

  const latencyNum = typeof simState.latency_ms === 'number' ? simState.latency_ms : 100;
  const isLatSpike = latencyNum > 300;

  const version = simState.current_version || 'v41';
  const versionDesc = version === 'v42' ? 'Incident trigger deployment' : 'Stable build';

  return (
    <section className="hud-panel" aria-labelledby="hud-heading">
      <div className="panel-header-row">
        <h2 className="panel-title" id="hud-heading">
          Live Service Telemetry and State
        </h2>
        <span className="hud-subtext" id="lastTelemetryUpdate">
          {lastSyncTime}
        </span>
      </div>

      <div className="hud-metrics-grid">
        <div className="hud-card">
          <span className="hud-label">Service Status</span>
          <div className={`status-badge ${status}`} id="valStatus">
            {status.toUpperCase()}
          </div>
          <span className="hud-subtext" id="statusDesc">
            {statusDesc}
          </span>
        </div>

        <div className="hud-card">
          <span className="hud-label">Error Rate</span>
          <div
            className="hud-value"
            id="valErrorRate"
            style={{ color: isErrSpike ? '#ff9da8' : 'var(--text-bright)' }}
          >
            {errRateFormatted}
          </div>
          <span className="hud-subtext">Threshold: &gt; 10.0% alert</span>
        </div>

        <div className="hud-card">
          <span className="hud-label">Latency (p99)</span>
          <div
            className="hud-value"
            id="valLatency"
            style={{ color: isLatSpike ? '#ff9da8' : 'var(--text-bright)' }}
          >
            {latencyNum}
            <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>ms</span>
          </div>
          <span className="hud-subtext">SLA Limit: 300ms</span>
        </div>

        <div className="hud-card">
          <span className="hud-label">Current Version</span>
          <div className="hud-value" id="valVersion">
            {version}
          </div>
          <span className="hud-subtext" id="versionDesc">
            {versionDesc}
          </span>
        </div>

        <div className="hud-card">
          <span className="hud-label">Replicas</span>
          <div className="hud-value" id="valReplicas">
            {currentReplicas}
          </div>
          <span className="hud-subtext">Permitted: 1 to 5 pods</span>
        </div>
      </div>
    </section>
  );
};
