import React from 'react';
import type { Attempt, ServiceState } from '../../types/incidentPilot';

interface LifecycleStripProps {
  service: ServiceState;
  attempts: Attempt[];
  /** True when the backend verified recovery, read from the incident result
   *  rather than inferred from a display string. */
  isRecovered: boolean;
  isRunning: boolean;
}

export const LifecycleStrip: React.FC<LifecycleStripProps> = ({ service, attempts, isRecovered, isRunning }) => {
  const hasRun = attempts.length > 0;
  const recovered = isRecovered;
  const activeIncident = service.status === 'down';
  const stages = [
    { label: 'Healthy', complete: service.status === 'healthy' || hasRun },
    { label: 'Incident', complete: activeIncident || hasRun },
    { label: 'Investigate', complete: hasRun },
    { label: 'Decide', complete: hasRun },
    { label: 'Safety', complete: hasRun },
    { label: 'Remediate', complete: hasRun },
    { label: 'Verify', complete: hasRun },
    { label: 'Recovered', complete: recovered },
  ];

  return (
    <section className="lifecycle-panel" aria-label="Agent incident lifecycle">
      <div className="lifecycle-heading">
        <span className="panel-title">Autonomous response lifecycle</span>
        <span className={`lifecycle-mode ${isRunning ? 'running' : recovered ? 'recovered' : activeIncident ? 'incident' : ''}`}>
          {isRunning ? 'Agent active' : recovered ? 'Recovery verified' : activeIncident ? 'Incident awaiting response' : 'Monitoring'}
        </span>
      </div>
      <ol className="lifecycle-track">
        {stages.map((stage, index) => (
          <li key={stage.label} className={stage.complete ? 'complete' : ''}>
            <span className="lifecycle-index">{stage.complete ? '✓' : String(index + 1).padStart(2, '0')}</span>
            <span>{stage.label}</span>
          </li>
        ))}
      </ol>
      {attempts.length > 1 && <div className="adaptation-proof">↻ Adaptation confirmed: {attempts.length} evidence-driven attempts</div>}
    </section>
  );
};
