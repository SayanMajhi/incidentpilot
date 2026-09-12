import React, { useRef, useEffect, useCallback } from 'react';
import type { RuntimeConfig, TelemetryPoint } from '../../types/incidentPilot';

interface TelemetryMonitorProps {
  telemetryBuffer: TelemetryPoint[];
  maxSamples: number;
  config: RuntimeConfig;
}

export const TelemetryMonitor: React.FC<TelemetryMonitorProps> = ({ telemetryBuffer, maxSamples, config }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Thresholds and the chart's y-axis ceiling come from `GET /config`, so the
  // lines drawn here are the ones the backend actually enforces.
  const alertErrorRate = config.elevated.error_rate;
  const alertLatencyMs = config.elevated.latency_ms;
  const sloErrorRate = config.recovery.max_error_rate;
  const sloLatencyMs = config.recovery.max_latency_ms;
  const latencyCeiling = config.chart.latency_ceiling_ms;

  const lastSample = telemetryBuffer[telemetryBuffer.length - 1];

  const isSpike = Boolean(lastSample && (lastSample.errorRate > alertErrorRate || lastSample.latency > alertLatencyMs));
  const statusPillClass = !lastSample ? 'monitor-pill' : isSpike ? 'monitor-pill surge' : 'monitor-pill nominal';
  const statusPillText = !lastSample ? 'AWAITING DATA' : isSpike ? 'SURGE DETECTED' : 'NOMINAL STEADY';

  const deltaValText = !lastSample ? '—' : isSpike ? 'Spike Active' : 'Baseline';
  const deltaValColor = isSpike ? '#ff9da8' : 'var(--emerald)';
  const deltaSubText = isSpike ? 'Elevated metrics detected' : 'Steady state nominal';

  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const displayWidth = rect.width || 750;
    const displayHeight = 160;

    if (canvas.width !== displayWidth * dpr || canvas.height !== displayHeight * dpr) {
      canvas.width = displayWidth * dpr;
      canvas.height = displayHeight * dpr;
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, displayWidth, displayHeight);

    const w = displayWidth;
    const h = displayHeight;
    const padX = 54;
    const padY = 20;
    const plotW = w - padX - 10;
    const plotH = h - padY * 2;

    // Background gridlines
    ctx.strokeStyle = 'rgba(56, 67, 88, 0.4)';
    ctx.lineWidth = 1;

    // Horizontal gridlines (4 steps)
    for (let i = 0; i <= 4; i++) {
      const y = padY + (plotH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padX, y);
      ctx.lineTo(padX + plotW, y);
      ctx.stroke();
    }

    // Draw thresholds. Error rate is plotted on a 0-100% scale; latency on a
    // 0..latencyCeiling scale.
    const errorThresholdY = padY + plotH - alertErrorRate * plotH;
    ctx.strokeStyle = 'rgba(181, 26, 43, 0.5)';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(padX, errorThresholdY);
    ctx.lineTo(padX + plotW, errorThresholdY);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.font = '11px "IBM Plex Mono", monospace';
    ctx.fillStyle = 'rgba(255, 157, 168, 0.9)';
    ctx.fillText(`${(alertErrorRate * 100).toFixed(0)}% Alert`, 4, errorThresholdY + 4);

    const latThresholdY = padY + plotH - (alertLatencyMs / latencyCeiling) * plotH;
    ctx.strokeStyle = 'rgba(255, 165, 134, 0.45)';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(padX, latThresholdY);
    ctx.lineTo(padX + plotW, latThresholdY);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = 'rgba(255, 165, 134, 0.9)';
    ctx.fillText(`${alertLatencyMs}ms alert`, 4, latThresholdY + 4);

    if (telemetryBuffer.length < 2) {
      ctx.restore();
      return;
    }

    const step = plotW / Math.max(maxSamples - 1, 1);

    // 1. Draw the latency trace.
    ctx.beginPath();
    telemetryBuffer.forEach((pt, idx) => {
      const x = padX + idx * step;
      const normalized = Math.min(Math.max(pt.latency / latencyCeiling, 0), 1);
      const y = padY + plotH - normalized * plotH;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#ffa586';
    ctx.lineWidth = 2;
    ctx.stroke();

    // 2. Draw the error-rate trace.
    ctx.beginPath();
    telemetryBuffer.forEach((pt, idx) => {
      const x = padX + idx * step;
      const normalized = Math.min(Math.max(pt.errorRate, 0), 1);
      const y = padY + plotH - normalized * plotH;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#b51a2b';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Highlight latest data points on right edge
    const lastPt = telemetryBuffer[telemetryBuffer.length - 1];
    const lastX = padX + (telemetryBuffer.length - 1) * step;

    const lastErrY = padY + plotH - Math.min(Math.max(lastPt.errorRate, 0), 1) * plotH;
    ctx.fillStyle = '#b51a2b';
    ctx.beginPath();
    ctx.arc(lastX, lastErrY, 4, 0, Math.PI * 2);
    ctx.fill();

    const lastLatY = padY + plotH - Math.min(Math.max(lastPt.latency / latencyCeiling, 0), 1) * plotH;
    ctx.fillStyle = '#ffa586';
    ctx.beginPath();
    ctx.arc(lastX, lastLatY, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }, [telemetryBuffer, maxSamples, alertErrorRate, alertLatencyMs, latencyCeiling]);

  // Redraw whenever the buffer or the thresholds change.
  useEffect(() => { renderCanvas(); }, [renderCanvas]);

  // Register the resize listener once, and read the latest renderer from a ref
  // so a new telemetry sample does not tear down and re-add the listener.
  const renderRef = useRef(renderCanvas);
  useEffect(() => { renderRef.current = renderCanvas; }, [renderCanvas]);
  useEffect(() => {
    const handleResize = () => renderRef.current();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <section className="telemetry-monitor-panel" aria-labelledby="monitor-heading">
      <div className="monitor-header">
        <div>
          <h3 id="monitor-heading">Real Time Telemetry Spike Monitor</h3>
          <span className="hud-subtext">Live SLI telemetry sampled from the FastAPI simulator</span>
        </div>
        <div className={statusPillClass} id="monitorStatusPill">
          <span className="dot" aria-hidden="true"></span>
          <span id="monitorStatusText">{statusPillText}</span>
        </div>
      </div>

      <div className="monitor-hud-stats">
        <div className="monitor-stat-box">
          <span className="monitor-stat-label">Error Rate Stream</span>
          <span className="monitor-stat-value" id="monitorErrVal">
            {lastSample ? `${(lastSample.errorRate * 100).toFixed(1)}%` : '—'}
          </span>
          <span className="hud-subtext">
            Alert &gt;{(alertErrorRate * 100).toFixed(1)}% · SLO {(sloErrorRate * 100).toFixed(1)}%
          </span>
        </div>

        <div className="monitor-stat-box">
          <span className="monitor-stat-label">Latency Stream</span>
          <span className="monitor-stat-value" id="monitorLatVal">
            {lastSample ? `${lastSample.latency}ms` : '—'}
          </span>
          <span className="hud-subtext">Alert &gt;{alertLatencyMs}ms · SLO {sloLatencyMs}ms</span>
        </div>

        <div className="monitor-stat-box">
          <span className="monitor-stat-label">Telemetry Delta</span>
          <span
            className="monitor-stat-value"
            id="monitorDeltaVal"
            style={{ color: deltaValColor }}
          >
            {deltaValText}
          </span>
          <span className="hud-subtext" id="monitorDeltaSub">
            {deltaSubText}
          </span>
        </div>

        <div className="monitor-stat-box">
          <span className="monitor-stat-label">Buffer Window</span>
          <span className="monitor-stat-value" id="monitorSampleVal">
            {telemetryBuffer.length} / {maxSamples}
          </span>
          <span className="hud-subtext">Rolling samples</span>
        </div>
      </div>

      <div className="monitor-canvas-box">
        <canvas
          ref={canvasRef}
          id="telemetryCanvas"
          className="monitor-canvas"
          width="800"
          height="160"
          aria-label="Real time error rate and latency graph"
        />
      </div>

      <div className="monitor-legend">
        <div className="legend-items">
          <div className="legend-item">
            <span className="legend-swatch" style={{ background: '#b51a2b' }}></span>
            <span>Error Rate (%) [{(alertErrorRate * 100).toFixed(0)}% alert]</span>
          </div>
          <div className="legend-item">
            <span className="legend-swatch" style={{ background: '#ffa586' }}></span>
            <span>Latency (ms) [{alertLatencyMs}ms alert]</span>
          </div>
        </div>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Dual-Trace Oscilloscope
        </span>
      </div>
    </section>
  );
};
