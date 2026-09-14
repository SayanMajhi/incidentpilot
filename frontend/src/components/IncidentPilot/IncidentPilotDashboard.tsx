import React, { useEffect, useState } from 'react';
import '../../styles/incidentPilot.css';
import { useIncidentPilot } from '../../hooks/useIncidentPilot';
import { Header } from './Header';
import { BackendAlert } from './BackendAlert';
import { TelemetryDashboard } from './TelemetryDashboard';
import { ScenarioSelector } from './ScenarioSelector';
import { CorePrincipleBanner } from './CorePrincipleBanner';
import { AgentExecutionTimeline } from './AgentExecutionTimeline';
import { TelemetryMonitor } from './TelemetryMonitor';
import { InspectorTabs } from './InspectorTabs';
import { Footer } from './Footer';
import { LifecycleStrip } from './LifecycleStrip';
import { CommandBar } from './CommandBar';
import { IncidentFocus } from './IncidentFocus';
import { RunContext } from './RunContext';

interface IncidentPilotDashboardProps {
  initialBaseUrl?: string;
}

export const IncidentPilotDashboard: React.FC<IncidentPilotDashboardProps> = ({
  initialBaseUrl,
}) => {
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null);
  const {
    backendUrl,
    setBackendUrl,
    connectionStatus,
    checkConnection,
    config,
    environment,
    simState,
    currentReplicas,
    lastSyncTime,
    activeScenario,
    triggerScenario,
    resetSystem,
    runIncident,
    testSafetyGate,
    safetyAssessment,
    safetyChallenge,
    agentPhase,
    isRunningAgent,
    runLabel,
    summary,
    decision,
    safety,
    verification,
    attempts,
    events,
    resolutionBanner,
    telemetryBuffer,
    maxSamples,
    logs,
    operationError,
    agent,
  } = useIncidentPilot(initialBaseUrl);

  const isOffline = connectionStatus !== 'connected';

  // Drop a stale selection when a new run replaces the attempt list, so an
  // attempt selected in a previous run cannot stay highlighted in this one.
  useEffect(() => { setSelectedNumber(null); }, [agent.run_id]);

  const selectedAttempt = selectedNumber === null
    ? attempts[attempts.length - 1]
    : attempts.find((attempt) => attempt.number === selectedNumber) ?? attempts[attempts.length - 1];
  const inspector = selectedAttempt?.inspector;

  return (
    <div className="incidentpilot-root">
      <Header
        backendUrl={backendUrl}
        onUrlChange={setBackendUrl}
        connectionStatus={connectionStatus}
        onPing={(url) => void checkConnection(url)}
      />

      <BackendAlert
        backendUrl={backendUrl}
        isOffline={isOffline}
        onRetry={() => void checkConnection()}
      />

      {operationError && (
        <div className="operation-error" role="alert">
          <span><strong>Operation failed.</strong> {operationError}</span>
          <button type="button" onClick={() => void checkConnection()}>Retry API</button>
        </div>
      )}

      <main className="dashboard-grid">
        <CommandBar
          activeScenario={activeScenario}
          agentPhase={agentPhase}
          isRunning={isRunningAgent}
          service={simState}
        />

        <RunContext agent={agent} phase={agentPhase} />

        <IncidentFocus
          service={simState}
          summary={summary}
          decision={decision}
          verification={verification}
        />

        <TelemetryDashboard
          simState={simState}
          currentReplicas={currentReplicas}
          lastSyncTime={lastSyncTime}
          config={config}
          isOffline={isOffline}
        />

        <LifecycleStrip
          service={simState}
          events={events}
          phase={agent.phase}
          status={agent.status}
          isRunning={isRunningAgent}
        />

        <ScenarioSelector
          onSelectScenario={triggerScenario}
          onReset={resetSystem}
          onRunIncident={runIncident}
          onTestSafetyGate={testSafetyGate}
          isRunning={isRunningAgent}
          runLabel={runLabel}
          disabled={isOffline}
          activeScenario={activeScenario}
          environment={environment}
          safetyAssessment={safetyAssessment}
          safetyChallenge={safetyChallenge}
        />

        <CorePrincipleBanner />

        <div className="content-split">
          <div className="timeline-column">
            <AgentExecutionTimeline
              attempts={attempts}
              events={events}
              resolutionBanner={resolutionBanner}
              summaryAgentStatus={summary.agentStatus}
              selectedAttemptNumber={selectedAttempt?.number ?? null}
              onSelectAttempt={(attempt) => setSelectedNumber(attempt.number)}
              isRunning={isRunningAgent}
            />

            <TelemetryMonitor
              telemetryBuffer={telemetryBuffer}
              maxSamples={maxSamples}
              config={config}
              environment={environment}
            />
          </div>

          <InspectorTabs
            summary={inspector?.summary ?? summary}
            decision={inspector?.decision ?? decision}
            safety={inspector?.safety ?? safety}
            verification={inspector?.verification ?? verification}
            logs={inspector?.logs ?? logs}
            selectedAttemptLabel={selectedAttempt ? `Attempt ${selectedAttempt.number} selected` : 'Latest incident state'}
          />
        </div>
      </main>

      <Footer environment={environment} />
    </div>
  );
};

export default IncidentPilotDashboard;
