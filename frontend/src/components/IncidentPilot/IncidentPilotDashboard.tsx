import React from 'react';
import '../../styles/incidentPilot.css';
import { useIncidentPilot } from '../../hooks/useIncidentPilot';
import { Header } from './Header';
import { BackendAlert } from './BackendAlert';
import { TelemetryDashboard } from './TelemetryDashboard';
import { ScenarioSelector } from './ScenarioSelector';
import { CorePrincipleBanner } from './CorePrincipleBanner';
import { AgentExecutionTimeline } from './AgentExecutionTimeline';
import { TelemetryMonitor } from './TelemetryMonitor';
import { InspectionSidebar } from './InspectionSidebar';
import { Footer } from './Footer';
import { LifecycleStrip } from './LifecycleStrip';

interface IncidentPilotDashboardProps {
  initialBaseUrl?: string;
}

export const IncidentPilotDashboard: React.FC<IncidentPilotDashboardProps> = ({
  initialBaseUrl,
}) => {
  const {
    backendUrl,
    setBackendUrl,
    connectionStatus,
    checkConnection,
    simState,
    currentReplicas,
    lastSyncTime,
    activeScenario,
    triggerScenario,
    resetSystem,
    runIncident,
    isRunningAgent,
    runLabel,
    summary,
    decision,
    safety,
    verification,
    attempts,
    resolutionBanner,
    telemetryBuffer,
    logs,
    operationError,
  } = useIncidentPilot(initialBaseUrl);

  const isOffline = connectionStatus === 'offline';

  return (
    <div className="incidentpilot-root">
      {/* Top Navigation and Bridge Header */}
      <Header
        backendUrl={backendUrl}
        onUrlChange={(newUrl) => setBackendUrl(newUrl)}
        connectionStatus={connectionStatus}
        onPing={() => checkConnection(false)}
      />

      {/* Offline Guidance Banner */}
      <BackendAlert
        backendUrl={backendUrl}
        isOffline={isOffline}
        onRetry={() => checkConnection(false)}
      />

      {operationError && (
        <div className="operation-error" role="alert">
          <span><strong>Operation failed.</strong> {operationError}</span>
          <button type="button" onClick={() => checkConnection(false)}>Retry API</button>
        </div>
      )}

      <main className="dashboard-grid">
        {/* Live Service State HUD */}
        <TelemetryDashboard
          simState={simState}
          currentReplicas={currentReplicas}
          lastSyncTime={lastSyncTime}
        />

        <LifecycleStrip
          service={simState}
          attempts={attempts}
          agentStatus={summary.agentStatus}
          isRunning={isRunningAgent}
        />

        {/* Operational Controls and Scenario Selection */}
        <ScenarioSelector
          onSelectScenario={triggerScenario}
          onReset={resetSystem}
          onRunIncident={runIncident}
          isRunning={isRunningAgent}
          runLabel={runLabel}
          disabled={isOffline}
          activeScenario={activeScenario}
        />

        {/* Axiom Banner: Action Success != Recovery */}
        <CorePrincipleBanner />

        {/* Main Workspace Split: Agent Timeline and Inspector Cards */}
        <div className="content-split">
          {/* Left Column: Centerpiece Timeline and Real Time Telemetry Spike Monitor */}
          <div className="timeline-column">
            <AgentExecutionTimeline
              attempts={attempts}
              resolutionBanner={resolutionBanner}
              summaryAgentStatus={summary.agentStatus}
            />

            <TelemetryMonitor telemetryBuffer={telemetryBuffer} />
          </div>

          {/* Right Column: Dedicated Deep-Dive Cards and Logs */}
          <InspectionSidebar
            summary={summary}
            decision={decision}
            safety={safety}
            verification={verification}
            logs={logs}
          />
        </div>
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
};

export default IncidentPilotDashboard;
