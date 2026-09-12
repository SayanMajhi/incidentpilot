import React from 'react';

export const CorePrincipleBanner: React.FC = () => {
  return (
    <div className="axiom-callout" role="note">
      <div className="axiom-text">
        <span className="axiom-badge">CORE PRINCIPLE</span>
        <div>
          <div className="axiom-statement">Action Execution Success is not Incident Recovery</div>
          <div className="axiom-desc">
            A remediation action may execute cleanly without resolving root cause. IncidentPilot strictly verifies telemetry before declaring resolution.
          </div>
        </div>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--peach)' }}>
        Observe &rarr; Decide &rarr; Safety Check &rarr; Act &rarr; Verify &rarr; Adapt
      </div>
    </div>
  );
};
