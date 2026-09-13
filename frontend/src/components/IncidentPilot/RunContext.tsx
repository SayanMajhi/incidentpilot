import React from 'react';
import type { AgentRunState } from '../../types/incidentPilot';

interface RunContextProps {
  agent: AgentRunState;
  phase: string;
}

export const RunContext: React.FC<RunContextProps> = ({ agent, phase }) => (
  <section className="run-context" aria-label="Incident run goal and state">
    <div>
      <span className="section-kicker">Goal-driven run</span>
      <strong>{agent.run_id ? `Run ${agent.run_id}` : 'No run started'}</strong>
      <p>{agent.goal}</p>
    </div>
    <dl>
      <div><dt>Phase</dt><dd>{phase}</dd></div>
      <div><dt>Attempt</dt><dd>{agent.attempt} / {agent.max_attempts}</dd></div>
      <div><dt>Status</dt><dd>{agent.status.toUpperCase()}</dd></div>
    </dl>
  </section>
);
