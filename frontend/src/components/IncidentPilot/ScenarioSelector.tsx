import React from 'react';
import type { ScenarioId } from '../../types/incidentPilot';
import { SCENARIO_LABELS } from '../../types/incidentPilot';

interface ScenarioSelectorProps {
  onSelectScenario: (scenario: ScenarioId) => void;
  onReset: () => void;
  onRunIncident: () => void;
  isRunning: boolean;
  runLabel: string;
  disabled?: boolean;
  /** The scenario the backend currently reports as active. */
  activeScenario?: string;
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
  isRunning,
  runLabel,
  disabled = false,
  activeScenario = 'None',
}) => {
  const controlsDisabled = isRunning || disabled;

  return (
    <section className="controls-panel" aria-labelledby="controls-heading">
      <div className="controls-split">
        <div className="scenario-group">
          <span className="panel-title" id="controls-heading" style={{ marginRight: '6px' }}>
            Demo scenarios:
          </span>
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
                disabled={controlsDisabled}
              >
                {label}
              </button>
            );
          })}
        </div>

        <div className="action-group">
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
    </section>
  );
};
