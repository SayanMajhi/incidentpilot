import React from 'react';
import type { RuntimeEnvironment } from '../../types/incidentPilot';

export const Footer: React.FC<{ environment: RuntimeEnvironment }> = ({ environment }) => {
  return (
    <footer>
      <div>IncidentPilot · Autonomous, policy-gated incident recovery</div>
      <div>{environment.mode} adapter · Single-process runtime · Local-first demo</div>
    </footer>
  );
};
