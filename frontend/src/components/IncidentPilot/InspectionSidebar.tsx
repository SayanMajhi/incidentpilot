import React from 'react';
import type {
  IncidentSummary,
  DecisionDetails,
  SafetyState,
  VerificationState,
  LogEntry,
} from '../../types/incidentPilot';

interface InspectionSidebarProps {
  summary: IncidentSummary;
  decision: DecisionDetails;
  safety: SafetyState;
  verification: VerificationState;
  logs: LogEntry[];
}

export const InspectionSidebar: React.FC<InspectionSidebarProps> = ({
  summary,
  decision,
  safety,
  verification,
  logs,
}) => {
  const isOutcomeResolved = summary.finalOutcome === 'RESOLVED';
  const isSafetyAllowed = safety.verdict === 'ALLOWED';
  const isVerificationRecovered = verification.recovered === 'YES';

  return (
    <div className="inspection-column">
      {/* Incident Summary Card */}
      <div className="card-panel">
        <h3 className="card-panel-title">Incident Summary</h3>
        <table className="data-table">
          <tbody>
            <tr>
              <td className="key">Active Scenario</td>
              <td className="val" id="summaryScenario">
                {summary.scenario}
              </td>
            </tr>
            <tr>
              <td className="key">Agent Status</td>
              <td className="val" id="summaryAgentStatus">
                {summary.agentStatus}
              </td>
            </tr>
            <tr>
              <td className="key">Total Attempts</td>
              <td className="val" id="summaryAttempts">
                {summary.attempts}
              </td>
            </tr>
            <tr>
              <td className="key">Final Action</td>
              <td className="val" id="summaryFinalAction">
                {summary.finalAction}
              </td>
            </tr>
            <tr>
              <td className="key">Final Verification</td>
              <td className="val" id="summaryFinalVerification">
                {summary.finalVerification}
              </td>
            </tr>
            <tr>
              <td className="key">Final Outcome</td>
              <td
                className="val"
                id="summaryFinalOutcome"
                style={isOutcomeResolved ? { color: 'var(--emerald)' } : {}}
              >
                {summary.finalOutcome}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Decision Card */}
      <div className="card-panel">
        <div className="card-panel-title">
          <span>Decision Details</span>
          <span className="source-pill" id="decisionSource">
            source: {decision.source || 'none'}
          </span>
        </div>
        <table className="data-table">
          <tbody>
            <tr>
              <td className="key">Proposed Action</td>
              <td className="val" id="decisionAction">
                {decision.action}
              </td>
            </tr>
            <tr>
              <td className="key">Target</td>
              <td className="val" id="decisionTarget">
                {decision.target}
              </td>
            </tr>
            <tr>
              <td className="key">Confidence</td>
              <td className="val" id="decisionConfidence">
                {decision.confidence}
              </td>
            </tr>
            <tr>
              <td className="key">Reasoning</td>
              <td
                className="val"
                id="decisionReason"
                style={{ fontFamily: 'var(--font-ui)', fontSize: '0.82rem' }}
              >
                {decision.reason}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Safety Card */}
      <div className="card-panel">
        <div className="card-panel-title">
          <span>Safety Policy Engine</span>
          <span className="source-pill" id="safetyStatus">
            {safety.status}
          </span>
        </div>
        <table className="data-table">
          <tbody>
            <tr>
              <td className="key">Action Checked</td>
              <td className="val" id="safetyAction">
                {safety.action}
              </td>
            </tr>
            <tr>
              <td className="key">Verdict</td>
              <td
                className="val"
                id="safetyVerdict"
                style={
                  safety.verdict !== 'Pending'
                    ? { color: isSafetyAllowed ? 'var(--emerald)' : '#ff9da8' }
                    : {}
                }
              >
                {safety.verdict}
              </td>
            </tr>
            <tr>
              <td className="key">Policy Notes</td>
              <td
                className="val"
                id="safetyReason"
                style={{ fontFamily: 'var(--font-ui)', fontSize: '0.82rem' }}
              >
                {safety.reason}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Verification Card */}
      <div className="card-panel">
        <div className="card-panel-title">
          <span>Verification Engine</span>
          <span className="source-pill" id="verificationStatus">
            {verification.status}
          </span>
        </div>
        <table className="data-table">
          <tbody>
            <tr>
              <td className="key">Recovered</td>
              <td
                className="val"
                id="verificationRecovered"
                style={
                  verification.recovered !== 'Pending'
                    ? { color: isVerificationRecovered ? 'var(--emerald)' : '#ff9da8' }
                    : {}
                }
              >
                {verification.recovered}
              </td>
            </tr>
            <tr>
              <td className="key">Telemetry Verification</td>
              <td
                className="val"
                id="verificationReason"
                style={{ fontFamily: 'var(--font-ui)', fontSize: '0.82rem' }}
              >
                {verification.reason}
              </td>
            </tr>
            <tr>
              <td className="key">Error Rate Post-Action</td>
              <td className="val" id="verificationErrorRate">
                {verification.errorRate}
              </td>
            </tr>
            <tr>
              <td className="key">Latency Post-Action</td>
              <td className="val" id="verificationLatency">
                {verification.latency}
              </td>
            </tr>
            <tr>
              <td className="key">Live Status</td>
              <td className="val" id="verificationServiceStatus">
                {verification.serviceStatus}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Collapsible Log Viewer */}
      <div className="card-panel">
        <div className="card-panel-title">
          <span>Diagnostic Logs</span>
          <span className="source-pill" id="logCount">
            {logs.length} entries
          </span>
        </div>
        <div
          className="logs-container"
          id="logViewer"
          role="log"
          aria-label="System diagnostic logs"
        >
          {logs.map((log) => (
            <div key={log.id} className="log-line">
              <span className="log-time">{log.time}</span>
              <span className={`log-level ${log.level}`}>{log.level}</span>
              <span className="log-msg">{log.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
