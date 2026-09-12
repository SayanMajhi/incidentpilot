import React from 'react';
import type { Attempt, ResolutionBanner } from '../../types/incidentPilot';

const STEP_ICONS: Record<string, string> = {
  obs: '\uD83D\uDD0D',   // 🔍
  dec: '\uD83E\uDDE0',   // 🧠
  safe: '\uD83D\uDEE1',  // 🛡️
  act: '\u2699',         // ⚙️
  ver: '\uD83D\uDD0E',   // 🔎
  adapt: '\uD83D\uDD04', // 🔄
};

interface AgentExecutionTimelineProps {
  attempts: Attempt[];
  resolutionBanner: ResolutionBanner;
  summaryAgentStatus: string;
}

export const AgentExecutionTimeline: React.FC<AgentExecutionTimelineProps> = ({
  attempts,
  resolutionBanner,
  summaryAgentStatus,
}) => {
  const isStandby = attempts.length === 0;

  const timelineSummary = isStandby
    ? 'Awaiting incident execution'
    : summaryAgentStatus === 'Resolved'
    ? 'Incident cycle concluded'
    : 'Autonomous loop active';

  return (
    <section className="timeline-panel" aria-labelledby="timeline-heading">
      <div className="timeline-header">
        <h2 id="timeline-heading">Agent Execution Timeline</h2>
        <span className="hud-subtext" id="timelineSummary">
          {timelineSummary}
        </span>
      </div>

      <div className="attempts-container" id="attemptsContainer">
        {isStandby ? (
          <div className="attempt-card" id="standbyCard">
            <div className="attempt-header">
              <span className="attempt-tag">STANDBY STATE</span>
              <span className="attempt-status-pill running">IDLE</span>
            </div>
            <div className="attempt-body" style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Select a scenario above and click <strong>Run Incident</strong> to trigger the autonomous loop.
            </div>
          </div>
        ) : (
          attempts.map((attempt) => {
            let stateClass = 'active-attempt';
            if (attempt.statusClass === 'success') {
              stateClass = 'resolved-attempt';
            } else if (attempt.statusClass === 'retry') {
              stateClass = 'failed-attempt';
            }

            return (
              <div key={attempt.id} className={`attempt-card ${stateClass}`} id={attempt.id}>
                <div className="attempt-header">
                  <span className="attempt-tag">{attempt.tag}</span>
                  <span className={`attempt-status-pill ${attempt.statusClass}`}>
                    {attempt.statusText}
                  </span>
                </div>
                <div className="attempt-body">
                  {attempt.steps.map((step, idx) => (
                    <div key={idx} className="step-item">
                      <div className="step-track">
                        <div className="step-icon-circle">
                          {STEP_ICONS[step.type] || '\u25CB'}
                        </div>
                        <div className="step-connector"></div>
                      </div>
                      <div className="step-content">
                        <div className="step-label">{step.label}</div>
                        <div className={`step-details ${step.customClass || ''}`}>
                          {step.details}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })
        )}
      </div>

      {resolutionBanner.visible && (
        <div
          className={`resolution-banner ${resolutionBanner.isResolved ? 'resolved' : ''}`}
          id="resolutionBanner"
          style={{ display: 'block' }}
        >
          {resolutionBanner.text}
        </div>
      )}
    </section>
  );
};
