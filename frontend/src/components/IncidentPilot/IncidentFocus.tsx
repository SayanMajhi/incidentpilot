import React from 'react';
import type { DecisionDetails, IncidentSummary, ServiceState, VerificationState } from '../../types/incidentPilot';

interface IncidentFocusProps {
  service: ServiceState;
  summary: IncidentSummary;
  decision: DecisionDetails;
  verification: VerificationState;
}

export const IncidentFocus: React.FC<IncidentFocusProps> = ({ service, summary, decision, verification }) => {
  const hasIncident = service.status === 'down' || service.status === 'degraded';
  const isHealthy = service.status === 'healthy';
  const title = hasIncident ? 'Current incident' : isHealthy ? 'No active incident' : 'Awaiting live service state';
  const description = hasIncident
    ? `${summary.scenario}: ${decision.reason}`
    : summary.finalOutcome !== 'None'
      ? `Last run: ${summary.finalOutcome}. ${verification.reason}`
      : 'The service is healthy. Select a demo scenario to begin an incident workflow.';

  return (
    <section className={`incident-focus ${hasIncident ? 'incident-focus-active' : ''}`} aria-labelledby="incident-focus-title">
      <div className="incident-focus-heading">
        <div>
          <span className="section-kicker">{hasIncident ? 'Needs attention' : 'Service state'}</span>
          <h2 id="incident-focus-title">{title}</h2>
          <p>{description}</p>
        </div>
        <span className={`incident-verdict ${verification.isRecoveredBool === true ? 'verified' : verification.status === 'FAILED' ? 'failed' : ''}`}>
          {verification.status === 'VERIFIED' ? 'Verified recovery' : verification.status === 'FAILED' ? 'Verification failed' : 'No verification yet'}
        </span>
      </div>
      <dl className="incident-focus-facts">
        <div><dt>Suspected cause</dt><dd>{decision.reason}</dd></div>
        <div><dt>Chosen action</dt><dd>{decision.action}</dd></div>
        <div><dt>Verification</dt><dd>{verification.reason}</dd></div>
      </dl>
    </section>
  );
};
