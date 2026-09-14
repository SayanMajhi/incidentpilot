import React from 'react';
import type { RuntimeEnvironment, SafetyAssessment, SafetyState, ScenarioId } from '../../types/incidentPilot';
import { SCENARIO_LABELS } from '../../types/incidentPilot';

interface ScenarioSelectorProps {
  onSelectScenario: (scenario: ScenarioId) => void;
  onReset: () => void;
  onRunIncident: () => void;
  onTestSafetyGate: () => void;
  isRunning: boolean;
  runLabel: string;
  disabled?: boolean;
  /** The scenario the backend currently reports as active. */
  activeScenario?: string;
  environment: RuntimeEnvironment;
  safetyAssessment: SafetyAssessment | null;
  safetyChallenge: SafetyState | null;
}

/** The scenarios the backend exposes, in demo order. Identifiers match the
 *  values `/status` reports, so no label round-tripping is required. */
const SCENARIOS: Array<{ id: ScenarioId; domId: string; className?: string }> = [
  { id: 'healthy', domId: 'btnScenarioNormal' },
  { id: 'generic_outage', domId: 'btnScenarioOutage' },
  { id: 'bad_deployment', domId: 'btnScenarioBadDeploy' },
  { id: 'adaptive_incident', domId: 'btnScenarioAdaptive', className: 'adaptive-highlight' },
];

export const ScenarioSelector: React.FC<ScenarioSelectorProps> = ({
  onSelectScenario,
  onReset,
  onRunIncident,
  onTestSafetyGate,
  isRunning,
  runLabel,
  disabled = false,
  activeScenario = 'None',
  environment,
  safetyAssessment,
  safetyChallenge,
}) => {
  const controlsDisabled = isRunning || disabled;
  const simulatorControlsDisabled = controlsDisabled || !environment.supports_scenario_injection;

  return (
    <section className="controls-panel" aria-labelledby="controls-heading">
      <div className="controls-split">
        <div className="scenario-group">
          <div className="scenario-heading-row">
            <span className="panel-title" id="controls-heading">Demo scenarios</span>
            <span className="environment-badge">{environment.mode.toUpperCase()}</span>
          </div>
          {SCENARIOS.map(({ id, domId, className }) => {
            const label = SCENARIO_LABELS[id];
            return (
              <button
                key={id}
                className={`btn-scenario ${className ?? ''} ${activeScenario === label ? 'selected' : ''}`}
                id={domId}
                type="button"
                aria-pressed={activeScenario === label}
                onClick={() => onSelectScenario(id)}
                disabled={simulatorControlsDisabled}
              >
                {label}
              </button>
            );
          })}
        </div>

        <div className="action-group">
          <button
            className="btn-safety-challenge"
            id="btnSafetyChallenge"
            type="button"
            onClick={() => onTestSafetyGate()}
            disabled={controlsDisabled}
          >
            Test Safety Gate: scale to 20
          </button>
          <button
            className="btn-reset"
            id="btnReset"
            type="button"
            onClick={() => onReset()}
            disabled={controlsDisabled}
          >
            Reset
          </button>
          <button
            className="btn-run-incident"
            id="btnRunIncident"
            type="button"
            onClick={() => onRunIncident()}
            disabled={controlsDisabled}
          >
            {isRunning && (
              <span
                id="runSpinner"
                style={{ display: 'inline-block', marginRight: '6px' }}
                aria-hidden="true"
              >
                &#9696;
              </span>
            )}
            <span id="runLabel">{runLabel}</span>
          </button>
        </div>
      </div>

      {!environment.supports_scenario_injection && (
        <div className="kubernetes-scenario-guide" role="note">
          <strong>Scenario injection is external in Kubernetes mode.</strong>
          <span>Prepare the adaptive workload from the repository root, then run the agent here:</span>
          <code>.\scripts\run_kubernetes_scenario.ps1 -Scenario adaptive-resource-pressure</code>
        </div>
      )}

      {safetyChallenge && safetyAssessment && (
        <div className={`safety-challenge-result ${safetyChallenge.verdict === 'BLOCKED' ? 'blocked' : 'allowed'}`} role="status" aria-live="polite">
          <div>
            <span className="section-kicker">Policy challenge · {safetyAssessment.assessment_id}</span>
            <strong>{safetyChallenge.verdict}</strong>
          </div>
          <dl>
            <div><dt>Rule</dt><dd>{safetyChallenge.ruleId}</dd></div>
            <div><dt>Reason</dt><dd>{safetyChallenge.reason}</dd></div>
            <div><dt>Infrastructure executed</dt><dd>{safetyAssessment.executed ? 'YES' : 'NO'}</dd></div>
          </dl>
        </div>
      )}
    </section>
  );
};
