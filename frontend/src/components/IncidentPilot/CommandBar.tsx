import React from 'react';
import type { ServiceState } from '../../types/incidentPilot';

interface CommandBarProps {
  activeScenario: string;
  agentStatus: string;
  isRunning: boolean;
  onRunIncident: () => void;
  runLabel: string;
  service: ServiceState;
  disabled: boolean;
}

export const CommandBar: React.FC<CommandBarProps> = ({
  activeScenario,
  agentStatus,
  isRunning,
  onRunIncident,
  runLabel,
  service,
  disabled,
}) => (
  <section className="command-bar" aria-label="Incident command controls">
    <div className="command-state">
      <span className={`command-health ${service.status}`}>{service.status.toUpperCase()}</span>
      <div><span>Active scenario</span><strong>{activeScenario}</strong></div>
      <div><span>Agent state</span><strong>{agentStatus}</strong></div>
    </div>
    <button className="command-run" type="button" onClick={onRunIncident} disabled={disabled || isRunning}>
      {isRunning ? 'Agent running…' : runLabel}
    </button>
  </section>
);
