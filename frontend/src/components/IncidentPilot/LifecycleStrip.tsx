import React from 'react';
import type { IncidentStatus, ServiceState, TimelineEvent } from '../../types/incidentPilot';

interface LifecycleStripProps {
  service: ServiceState;
  events: TimelineEvent[];
  phase: string;
  status: IncidentStatus;
  isRunning: boolean;
}

const NORMALIZED_PHASE: Record<string, string> = {
  deciding: 'planning',
  checking_safety: 'safety_check',
  remediating: 'executing',
  adapting: 'replanning',
};

function normalizePhase(phase: string): string {
  return NORMALIZED_PHASE[phase] || phase;
}

export const LifecycleStrip: React.FC<LifecycleStripProps> = ({ service, events, phase, status, isRunning }) => {
  const current = normalizePhase(phase);
  const visited = new Set(events.map((event) => normalizePhase(event.phase)));
  const terminal = ['no_incident', 'resolved', 'blocked', 'escalated', 'failed'].includes(status);
  const stageDefinitions = [
    { key: 'observing', label: 'Observe' },
    { key: 'incident_detected', label: 'Detect' },
    { key: 'investigating', label: 'Investigate' },
    { key: 'diagnosing', label: 'Diagnose' },
    { key: 'planning', label: 'Plan' },
    { key: 'safety_check', label: 'Safety' },
    { key: 'executing', label: 'Execute' },
    { key: 'verifying', label: 'Verify' },
    { key: 'resolved', label: status === 'no_incident' ? 'No incident' : 'Recovered' },
  ];

  return (
    <section className="lifecycle-panel" aria-label="Agent incident lifecycle">
      <div className="lifecycle-heading">
        <span className="panel-title">Autonomous response lifecycle</span>
        <span className={`lifecycle-mode ${isRunning ? 'running' : status === 'resolved' ? 'recovered' : service.status !== 'healthy' ? 'incident' : ''}`}>
          {isRunning
            ? 'Agent active'
            : status === 'resolved'
              ? 'Recovery verified'
              : status === 'no_incident'
                ? 'No incident detected'
                : service.status !== 'healthy'
                  ? 'Incident awaiting response'
                  : 'Monitoring'}
        </span>
      </div>
      <ol className="lifecycle-track">
        {stageDefinitions.map((stage, index) => {
          const isCurrent = current === stage.key || (['no_incident', 'resolved'].includes(status) && stage.key === 'resolved');
          const complete = visited.has(stage.key) && (!isCurrent || terminal);
          return (
            <li key={stage.key} className={`${complete ? 'complete' : ''} ${isCurrent ? 'current' : ''}`} aria-current={isCurrent ? 'step' : undefined}>
              <span className="lifecycle-index">{complete ? '✓' : String(index + 1).padStart(2, '0')}</span>
              <span>{stage.label}</span>
            </li>
          );
        })}
      </ol>
      {visited.has('replanning') && <div className="adaptation-proof">↻ Replanning confirmed by the backend event stream</div>}
    </section>
  );
};
