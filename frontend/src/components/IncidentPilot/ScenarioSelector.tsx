import React from 'react';

interface ScenarioSelectorProps {
  onSelectScenario: (scenario: string) => void;
  onReset: () => void;
  onRunIncident: () => void;
  isRunning: boolean;
  runLabel: string;
  disabled?: boolean;
  activeScenario?: string;
}

export const ScenarioSelector: React.FC<ScenarioSelectorProps> = ({
  onSelectScenario,
  onReset,
  onRunIncident,
  isRunning,
  runLabel,
  disabled = false,
  activeScenario = 'None',
}) => {
  return (
    <section className="controls-panel" aria-labelledby="controls-heading">
      <div className="controls-split">
        <div className="scenario-group">
          <span className="panel-title" id="controls-heading" style={{ marginRight: '6px' }}>
            Scenarios:
          </span>
          <button
            className={`btn-scenario ${activeScenario === 'Normal / Healthy' ? 'selected' : ''}`}
            id="btnScenarioNormal"
            type="button"
            onClick={() => onSelectScenario('Normal / Healthy')}
            disabled={isRunning || disabled}
          >
            Normal / Healthy
          </button>
          <button
            className={`btn-scenario ${activeScenario === 'Generic Outage' ? 'selected' : ''}`}
            id="btnScenarioOutage"
            type="button"
            onClick={() => onSelectScenario('Generic Outage')}
            disabled={isRunning || disabled}
          >
            Generic Outage
          </button>
          <button
            className={`btn-scenario ${activeScenario === 'Bad Deployment' ? 'selected' : ''}`}
            id="btnScenarioBadDeploy"
            type="button"
            onClick={() => onSelectScenario('Bad Deployment')}
            disabled={isRunning || disabled}
          >
            Bad Deployment
          </button>
          <button
            className={`btn-scenario adaptive-highlight ${activeScenario === 'Adaptive Incident' ? 'selected' : ''}`}
            id="btnScenarioAdaptive"
            type="button"
            onClick={() => onSelectScenario('Adaptive Incident')}
            disabled={isRunning || disabled}
          >
            Adaptive Incident
          </button>
        </div>

        <div className="action-group">
          <button
            className="btn-reset"
            id="btnReset"
            type="button"
            onClick={() => onReset()}
            disabled={isRunning || disabled}
          >
            Reset
          </button>
          <button
            className="btn-run-incident"
            id="btnRunIncident"
            type="button"
            onClick={() => onRunIncident()}
            disabled={isRunning || disabled}
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
            <span id="runLabel">{runLabel || 'Run Incident'}</span>
          </button>
        </div>
      </div>
    </section>
  );
};
