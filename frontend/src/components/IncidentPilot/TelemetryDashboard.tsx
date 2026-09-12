import React from 'react';
import type { RuntimeConfig, ServiceState } from '../../types/incidentPilot';

interface TelemetryDashboardProps {
  simState: ServiceState;
  currentReplicas: number;
  lastSyncTime: string;
  config: RuntimeConfig;
  isOffline: boolean;
}

const EM_DASH = '—';

export const TelemetryDashboard: React.FC<TelemetryDashboardProps> = ({
  simState,
  currentReplicas,
  lastSyncTime,
  config,
  isOffline,
}) => {
  // Before the first successful poll there is no telemetry. The panel says so
  // rather than substituting healthy-looking placeholder values.
  const hasTelemetry = simState.status !== 'unknown';
  const status = simState.status;
  const isDown = status === 'down';
  const statusDesc = !hasTelemetry
    ? 'Awaiting backend telemetry'
    : isOffline
    ? 'Last known state · API unavailable'
    : isDown
    ? 'Active production incident detected'
    : 'All SLO objectives nominal';

  const errRateFormatted = hasTelemetry ? `${(simState.error_rate * 100).toFixed(1)}%` : EM_DASH;
  const isErrSpike = hasTelemetry && simState.error_rate > config.elevated.error_rate;

  const isLatSpike = hasTelemetry && simState.latency_ms > config.elevated.latency_ms;

  const version = simState.current_version || EM_DASH;
  const versionDesc = version === config.bad_deployment_version
    ? 'Incident trigger deployment'
    : version === config.baseline.version
    ? 'Stable build'
    : 'Deployed build';

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
          <span className="hud-subtext">
            Alert above {(config.elevated.error_rate * 100).toFixed(1)}% · SLO{' '}
            {(config.recovery.max_error_rate * 100).toFixed(1)}%
          </span>
        </div>

        <div className="hud-card">
          <span className="hud-label">Latency (p99)</span>
          <div
            className="hud-value"
            id="valLatency"
            style={{ color: isLatSpike ? '#ff9da8' : 'var(--text-bright)' }}
          >
            {hasTelemetry ? simState.latency_ms : EM_DASH}
            {hasTelemetry && (
              <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>ms</span>
            )}
          </div>
          <span className="hud-subtext">
            Alert above {config.elevated.latency_ms}ms · SLO {config.recovery.max_latency_ms}ms
          </span>
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
            {hasTelemetry ? currentReplicas : EM_DASH}
          </div>
          <span className="hud-subtext">
            Permitted: {config.replicas.min} to {config.replicas.max} pods
          </span>
        </div>
      </div>
    </section>
  );
};
