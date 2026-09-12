import React from 'react';
import type { ServiceState } from '../../types/incidentPilot';

interface CommandBarProps {
  activeScenario: string;
  /** The agent phase the backend is currently reporting. */
  agentPhase: string;
  isRunning: boolean;
  service: ServiceState;
}

/** A read-only status strip. The Run Incident and Reset controls live in the
 *  scenario panel, so there is exactly one of each on the page. */
export const CommandBar: React.FC<CommandBarProps> = ({
  activeScenario,
  agentPhase,
  isRunning,
  service,
}) => (
  <section className="command-bar" aria-label="Incident status">
    <div className="command-state">
      <span className={`command-health ${service.status}`}>{service.status.toUpperCase()}</span>
      <div><span>Active scenario</span><strong>{activeScenario}</strong></div>
      <div>
        <span>Agent state</span>
        <strong aria-live="polite">{agentPhase}</strong>
      </div>
    </div>
    {isRunning && (
      <span className="command-running" role="status">
        <span aria-hidden="true">&#9696;</span> Autonomous loop in progress
      </span>
    )}
  </section>
);
