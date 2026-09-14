import React, { useState } from 'react';
import type { DecisionDetails, IncidentSummary, LogEntry, SafetyState, VerificationState } from '../../types/incidentPilot';

interface InspectorTabsProps {
  summary: IncidentSummary;
  decision: DecisionDetails;
  safety: SafetyState;
  verification: VerificationState;
  logs: LogEntry[];
  selectedAttemptLabel: string;
}

type Tab = 'summary' | 'decision' | 'safety' | 'verification' | 'logs';
const tabs: Array<{ id: Tab; label: string }> = [
  { id: 'summary', label: 'Summary' },
  { id: 'decision', label: 'Decision' },
  { id: 'safety', label: 'Safety' },
  { id: 'verification', label: 'Verify' },
  { id: 'logs', label: 'Logs' },
];

const Row = ({ label, value }: { label: string; value: string }) => <div className="inspector-row"><dt>{label}</dt><dd>{value}</dd></div>;

export const InspectorTabs: React.FC<InspectorTabsProps> = ({ summary, decision, safety, verification, logs, selectedAttemptLabel }) => {
  const [activeTab, setActiveTab] = useState<Tab>('summary');

  return (
    <aside className="inspector-tabs" aria-label="Incident inspector">
      <div className="inspector-heading">
        <div><span className="section-kicker">{selectedAttemptLabel}</span><h2>Inspector</h2></div>
        <span className="source-pill">{summary.agentStatus}</span>
      </div>
      <div className="inspector-tablist" role="tablist" aria-label="Inspection sections">
        {tabs.map((tab) => <button key={tab.id} id={`tab-${tab.id}`} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls={activeTab === tab.id ? 'inspector-panel' : undefined} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
      </div>
      <div className="inspector-panel" id="inspector-panel" role="tabpanel" aria-labelledby={`tab-${activeTab}`}>
        {activeTab === 'summary' && <dl>
          <Row label="Active scenario" value={summary.scenario} /><Row label="Agent status" value={summary.agentStatus} />
          <Row label="Total attempts" value={summary.attempts} /><Row label="Final action" value={summary.finalAction} />
          <Row label="Final verification" value={summary.finalVerification} /><Row label="Final outcome" value={summary.finalOutcome} />
          <Row label="Probable cause" value={summary.diagnosisCause} /><Row label="Diagnosis" value={summary.diagnosisSummary} />
          <Row label="Evidence" value={summary.evidence} />
        </dl>}
        {activeTab === 'decision' && <dl>
          <Row label="Source" value={decision.source} /><Row label="Proposed action" value={decision.action} />
          <Row label="Target" value={decision.target} /><Row label="Confidence" value={decision.confidence} />
          <Row label="Reasoning" value={decision.reason} />
          <Row label="AI suggestion" value={decision.aiSuggestion} /><Row label="Deterministic validation" value={decision.validation} />
          <Row label="Validation reason" value={decision.validationReason} />
        </dl>}
        {activeTab === 'safety' && <dl>
          <Row label="Status" value={safety.status} /><Row label="Action checked" value={safety.action} />
          <Row label="Target" value={safety.target} /><Row label="Verdict" value={safety.verdict} />
          <Row label="Rule ID" value={safety.ruleId} /><Row label="Policy reason" value={safety.reason} />
          <Row label="Namespace" value={safety.namespace} /><Row label="Replica bounds" value={safety.bounds} />
          <Row label="Attempt budget" value={safety.attemptBudget} /><Row label="Executed" value={safety.executed} />
        </dl>}
        {activeTab === 'verification' && <>
          <dl>
            <Row label="Status" value={verification.status} /><Row label="Recovered" value={verification.recovered} />
            <Row label="Telemetry result" value={verification.reason} /><Row label="Error rate" value={verification.errorRate} />
            <Row label="Latency" value={verification.latency} /><Row label="Live status" value={verification.serviceStatus} />
            <Row label="Metrics before" value={verification.metricsBefore} /><Row label="Metrics after" value={verification.metricsAfter} />
            <Row label="Before/after delta" value={verification.deltas} /><Row label="Samples" value={verification.samples} />
          </dl>
          {verification.checks.length > 0 && <section className="verification-checks" aria-label="Named recovery checks">
            <h3>Named recovery checks</h3>
            {verification.checks.map((check) => <div className={`verification-check ${check.passed ? 'passed' : 'failed'}`} key={check.id}>
              <span aria-hidden="true">{check.passed ? '✓' : '✕'}</span>
              <div><strong>{check.label}</strong><p>{check.detail}</p></div>
            </div>)}
          </section>}
        </>}
        {activeTab === 'logs' && <div className="logs-container" role="log" aria-label="System diagnostic logs">
          {logs.length ? logs.map((log) => <div key={log.id} className="log-line"><span className="log-time">{log.time}</span><span className={`log-level ${log.level}`}>{log.level}</span><span className="log-msg">{log.message}</span></div>) : <p className="inspector-empty">No diagnostic logs have been received.</p>}
        </div>}
      </div>
    </aside>
  );
};
