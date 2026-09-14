import React from 'react';
import type { Attempt, ResolutionBanner, TimelineEvent } from '../../types/incidentPilot';
import { titleCase } from '../../viewModels/incidentPilot';

interface AgentExecutionTimelineProps {
  attempts: Attempt[];
  events: TimelineEvent[];
  resolutionBanner: ResolutionBanner;
  summaryAgentStatus: string;
  selectedAttemptNumber: number | null;
  onSelectAttempt: (attempt: Attempt) => void;
  isRunning: boolean;
}

function eventTone(event: TimelineEvent): string {
  const value = `${event.event_type} ${event.phase}`;
  if (/failed|error|blocked|escalat/i.test(value)) return 'failure';
  if (/resolved|passed|recovered|no_incident|complete/i.test(value)) return 'success';
  if (/replan|partial|retry/i.test(value)) return 'warning';
  return 'neutral';
}

function eventTime(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? timestamp
    : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function compactData(data: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(data)
    .filter(([, value]) => value !== null && value !== undefined)
    .slice(0, 6)
    .map(([key, value]) => {
      if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        return [titleCase(key), String(value)];
      }
      return [titleCase(key), JSON.stringify(value)];
    });
}

export const AgentExecutionTimeline: React.FC<AgentExecutionTimelineProps> = ({
  attempts,
  events,
  resolutionBanner,
  summaryAgentStatus,
  selectedAttemptNumber,
  onSelectAttempt,
  isRunning,
}) => {
  const isStandby = events.length === 0 && attempts.length === 0;
  const timelineSummary = isRunning
    ? summaryAgentStatus
    : isStandby
      ? 'Awaiting incident execution'
      : `${events.length} backend events recorded`;

  return (
    <section className="timeline-panel" aria-labelledby="timeline-heading">
      <div className="timeline-header">
        <div>
          <span className="section-kicker">Backend audit trail</span>
          <h2 id="timeline-heading">Agent Execution Timeline</h2>
        </div>
        <span className="hud-subtext" id="timelineSummary">{timelineSummary}</span>
      </div>

      {isStandby ? (
        <div className="attempt-card" id="standbyCard">
          <div className="attempt-header">
            <span className="attempt-tag">STANDBY STATE</span>
            <span className="attempt-status-pill running">IDLE</span>
          </div>
          <div className="attempt-body timeline-empty">
            Select a scenario and run the agent. Every item shown here will come from a timestamped backend event.
          </div>
        </div>
      ) : (
        <ol className="backend-event-stream" aria-label="Timestamped backend agent events">
          {events.map((event) => {
            const data = compactData(event.data || {});
            return (
              <li key={event.event_id} className={`backend-event ${eventTone(event)}`}>
                <div className="event-rail" aria-hidden="true"><span /></div>
                <article>
                  <header>
                    <time dateTime={event.timestamp}>{eventTime(event.timestamp)}</time>
                    <span className="event-type">{titleCase(event.event_type)}</span>
                    <span className="event-phase">{titleCase(event.phase)}</span>
                    {event.attempt != null && event.attempt > 0 && <span className="event-attempt">Attempt {event.attempt}</span>}
                  </header>
                  <p>{event.message}</p>
                  {data.length > 0 && (
                    <dl className="event-data">
                      {data.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
                    </dl>
                  )}
                </article>
              </li>
            );
          })}
          {isRunning && (
            <li className="backend-event live-waiting">
              <div className="event-rail" aria-hidden="true"><span /></div>
              <article><p>Waiting for the next controller event…</p></article>
            </li>
          )}
        </ol>
      )}

      {attempts.length > 0 && (
        <div className="attempt-summary-section">
          <div className="attempt-summary-heading">
            <h3>Attempt records</h3>
            <span>Select one to inspect its stored evidence</span>
          </div>
          <div className="attempts-container" id="attemptsContainer">
            {attempts.map((attempt) => (
              <details
                key={attempt.id}
                className={`attempt-card compact-attempt ${attempt.statusClass}-attempt ${selectedAttemptNumber === attempt.number ? 'selected-attempt' : ''}`}
                id={attempt.id}
                open={selectedAttemptNumber === attempt.number}
                onToggle={(event) => { if (event.currentTarget.open) onSelectAttempt(attempt); }}
              >
                <summary className="attempt-header">
                  <span className="attempt-tag">{attempt.tag}</span>
                  <span className={`attempt-status-pill ${attempt.statusClass}`}>{attempt.statusText}</span>
                </summary>
                <div className="attempt-body attempt-facts">
                  <div><strong>Recorded action</strong><span>{attempt.actionSummary}</span></div>
                  <div><strong>Evidence</strong><span>{attempt.evidenceSummary}</span></div>
                </div>
              </details>
            ))}
          </div>
        </div>
      )}

      {resolutionBanner.visible && (
        <div
          className={`resolution-banner ${resolutionBanner.isResolved ? 'resolved' : 'escalated'}`}
          id="resolutionBanner"
        >
          {resolutionBanner.text}
        </div>
      )}
    </section>
  );
};
