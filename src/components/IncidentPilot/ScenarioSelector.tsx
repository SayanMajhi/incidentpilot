import React from 'react';

interface ScenarioSelectorProps {
  onSelectScenario: (scenario: string) => void;
  onReset: () => void;
  onRunIncident: () => void;
  isRunning: boolean;
  runLabel: string;
}

export const ScenarioSelector: React.FC<ScenarioSelectorProps> = ({
  onSelectScenario,
  onReset,
  onRunIncident,
  isRunning,
  runLabel,
}) => {
  return (
    <section className="controls-panel" aria-labelledby="controls-heading">
      <div className="controls-split">
        <div className="scenario-group">
          <span className="panel-title" id="controls-heading" style={{ marginRight: '6px' }}>
            Scenarios:
          </span>
          <button
            className="btn-scenario"
            id="btnScenarioNormal"
            type="button"
            onClick={() => onSelectScenario('Normal / Healthy')}
            disabled={isRunning}
          >
            Normal / Healthy
          </button>
          <button
            className="btn-scenario"
            id="btnScenarioOutage"
            type="button"
            onClick={() => onSelectScenario('Generic Outage')}
            disabled={isRunning}
          >
            Generic Outage
          </button>
          <button
            className="btn-scenario"
            id="btnScenarioBadDeploy"
            type="button"
            onClick={() => onSelectScenario('Bad Deployment')}
            disabled={isRunning}
          >
            Bad Deployment
          </button>
          <button
            className="btn-scenario adaptive-highlight"
            id="btnScenarioAdaptive"
            type="button"
            onClick={() => onSelectScenario('Adaptive Incident')}
            disabled={isRunning}
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
            disabled={isRunning}
          >
            Reset
          </button>
          <button
            className="btn-run-incident"
            id="btnRunIncident"
            type="button"
            onClick={() => onRunIncident()}
            disabled={isRunning}
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
