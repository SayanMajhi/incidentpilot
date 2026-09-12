import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import '../styles/landing.css';

const RESPONSE_STAGES = [
  { label: 'Observe', icon: '◎' },
  { label: 'Investigate', icon: '⌕' },
  { label: 'Decide', icon: '⬡' },
  { label: 'Act safely', icon: '▶' },
  { label: 'Verify', icon: '◈' },
  { label: 'Adapt', icon: '↻' },
];

function ResponseLifecyclePreview() {
  return (
    <figure className="pipeline-container lifecycle-preview">
      <div className="pipeline-wrapper" aria-label="Illustrative incident response lifecycle">
        {RESPONSE_STAGES.map((stage, index) => (
          <div className="lifecycle-stage" key={stage.label}>
            <div className="pipeline-node lifecycle-node">
              <div className="pipeline-node-circle" aria-hidden="true">{stage.icon}</div>
              <span className="pipeline-node-label">{stage.label}</span>
            </div>
            {index < RESPONSE_STAGES.length - 1 && <div className="pipeline-connector lifecycle-connector" />}
          </div>
        ))}
      </div>
      <figcaption className="pipeline-status lifecycle-caption">
        Illustrative response lifecycle — live status is shown in the dashboard.
      </figcaption>
    </figure>
  );
}

function HumanAgentGesture() {
  return (
    <figure className="human-agent-gesture" aria-labelledby="gesture-caption">
      <svg viewBox="0 0 360 104" role="img" aria-labelledby="gesture-title gesture-description">
        <title id="gesture-title">Human and agent collaboration</title>
        <desc id="gesture-description">Two abstract fingertips meet at the IncidentPilot signal.</desc>
        <defs>
          <linearGradient id="human-finger" x1="0" x2="1">
            <stop stopColor="#A5B4FC" />
            <stop offset="1" stopColor="#818CF8" />
          </linearGradient>
          <linearGradient id="agent-finger" x1="1" x2="0">
            <stop stopColor="#67E8F9" />
            <stop offset="1" stopColor="#22D3EE" />
          </linearGradient>
          <radialGradient id="gesture-glow">
            <stop stopColor="#E0E7FF" stopOpacity="0.95" />
            <stop offset="1" stopColor="#6366F1" stopOpacity="0" />
          </radialGradient>
        </defs>

        <circle className="gesture-glow" cx="180" cy="52" r="38" fill="url(#gesture-glow)" />
        <g className="gesture-human" aria-hidden="true">
          <path d="M28 63 C73 63 96 48 126 48 H153" fill="none" stroke="url(#human-finger)" strokeWidth="14" strokeLinecap="round" />
          <path d="M70 77 C94 70 111 63 127 58" fill="none" stroke="#6366F1" strokeOpacity="0.35" strokeWidth="5" strokeLinecap="round" />
        </g>
        <g className="gesture-agent" aria-hidden="true">
          <path d="M332 63 C287 63 264 48 234 48 H207" fill="none" stroke="url(#agent-finger)" strokeWidth="14" strokeLinecap="round" />
          <path d="M290 77 C266 70 249 63 233 58" fill="none" stroke="#22D3EE" strokeOpacity="0.35" strokeWidth="5" strokeLinecap="round" />
        </g>
        <circle className="gesture-signal" cx="180" cy="48" r="14" fill="#0C0C14" stroke="#E0E7FF" strokeWidth="2" />
        <path className="gesture-bolt" d="M183 35 L172 51 H180 L177 63 L189 46 H181 Z" fill="#E0E7FF" />
      </svg>
      <figcaption id="gesture-caption">
        <strong>Human control. Agent assistance.</strong>
        <span>The agent proposes; people retain control.</span>
      </figcaption>
    </figure>
  );
}

/* ═══════════════════════════════════════════════
   SCROLL REVEAL HOOK
   ═══════════════════════════════════════════════ */

function useScrollReveal() {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
          }
        });
      },
      { threshold: 0.1, rootMargin: '0px 0px -50px 0px' }
    );

    document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
    return () => observer.disconnect();
  }, []);
}

/* ═══════════════════════════════════════════════
   LANDING PAGE
   ═══════════════════════════════════════════════ */

export default function LandingPage() {
  useScrollReveal();
  const navigate = useNavigate();

  const handleLaunch = () => {
    navigate('/dashboard');
  };
  const handleSeeHow = () => {
    document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="landing-page">
      {/* Navigation */}
      <nav className="landing-nav">
        <div className="landing-nav-brand">
          <div className="brand-icon">⚡</div>
          IncidentPilot
        </div>
        <button className="landing-nav-cta" onClick={handleLaunch}>
          Launch Dashboard
        </button>
      </nav>

      {/* Hero */}
      <section className="hero">
        <div className="hero-bg-gradient" />
        <div className="hero-grid-overlay" />

        <div className="hero-badge">
          <span className="hero-badge-dot" />
          Autonomous Incident Response
        </div>

        <h1 className="hero-title">
          Your infrastructure has an incident.
          <br />
          <span className="hero-title-accent">Your agent has a plan.</span>
        </h1>

        <p className="hero-subtitle">
          An autonomous SRE agent that investigates incidents, executes safe remediation,
          verifies recovery, and adapts when the first fix fails.
        </p>

        <div className="hero-actions">
          <button className="btn-primary" onClick={handleLaunch}>
            Launch IncidentPilot
            <span style={{ fontSize: '14px' }}>→</span>
          </button>
          <button className="btn-secondary" onClick={handleSeeHow}>
            See how it works
            <span style={{ fontSize: '14px' }}>↓</span>
          </button>
        </div>

        <HumanAgentGesture />
        <ResponseLifecyclePreview />
      </section>

      {/* The Problem */}
      <section className="landing-section landing-section-dark">
        <div className="container-landing">
          <div className="reveal">
            <span className="section-label">The Problem</span>
            <h2 className="section-title">
              Traditional automation stops<br />
              at "action succeeded."
            </h2>
            <p className="section-description">
              Most runbooks execute a fix and assume the incident is resolved.
              But a successful action isn't the same as a recovered service.
            </p>
          </div>

          <div className="problem-comparison reveal">
            {/* Traditional */}
            <div className="problem-card problem-card-old">
              <div className="problem-card-label">
                <span>✕</span> Traditional Automation
              </div>
              <div className="problem-step">
                <div className="problem-step-icon">📡</div>
                <span>Incident detected</span>
              </div>
              <div className="problem-step-arrow">↓</div>
              <div className="problem-step">
                <div className="problem-step-icon">📋</div>
                <span>Match runbook rule</span>
              </div>
              <div className="problem-step-arrow">↓</div>
              <div className="problem-step">
                <div className="problem-step-icon">⚙</div>
                <span>Execute action</span>
              </div>
              <div className="problem-step-arrow">↓</div>
              <div className="problem-step danger">
                <div className="problem-step-icon">⚠</div>
                <span>Assume success ← blind spot</span>
              </div>
            </div>

            {/* IncidentPilot */}
            <div className="problem-card problem-card-new">
              <div className="problem-card-label">
                <span>✓</span> IncidentPilot
              </div>
              <div className="problem-step">
                <div className="problem-step-icon">◎</div>
                <span>Observe & investigate</span>
              </div>
              <div className="problem-step-arrow">↓</div>
              <div className="problem-step">
                <div className="problem-step-icon">⬡</div>
                <span>Reason about the evidence</span>
              </div>
              <div className="problem-step-arrow">↓</div>
              <div className="problem-step">
                <div className="problem-step-icon">▶</div>
                <span>Act with safety checks</span>
              </div>
              <div className="problem-step-arrow">↓</div>
              <div className="problem-step">
                <div className="problem-step-icon">◈</div>
                <span>Verify actual recovery</span>
              </div>
              <div className="problem-step-arrow">↓</div>
              <div className="problem-step">
                <div className="problem-step-icon">↻</div>
                <span>Adapt if verification fails</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="landing-section" id="how-it-works">
        <div className="container-landing">
          <div className="reveal">
            <span className="section-label">How It Works</span>
            <h2 className="section-title">
              Six stages of<br />intelligent response
            </h2>
            <p className="section-description">
              IncidentPilot follows a structured, verifiable workflow — not a simple if-then script.
            </p>
          </div>

          <div className="how-grid reveal">
            <div className="how-card">
              <div className="how-card-number">01</div>
              <div className="how-card-icon">◎</div>
              <h3 className="how-card-title">Observe</h3>
              <p className="how-card-desc">
                Collect service metrics, logs, and health signals.
                Understand the current state before acting.
              </p>
            </div>
            <div className="how-card">
              <div className="how-card-number">02</div>
              <div className="how-card-icon">🔍</div>
              <h3 className="how-card-title">Investigate</h3>
              <p className="how-card-desc">
                Analyze error patterns, deployment history, and
                correlations to identify root cause.
              </p>
            </div>
            <div className="how-card">
              <div className="how-card-number">03</div>
              <div className="how-card-icon">⬡</div>
              <h3 className="how-card-title">Decide</h3>
              <p className="how-card-desc">
                Choose the best remediation action based on evidence,
                with confidence scoring and reasoning.
              </p>
            </div>
            <div className="how-card">
              <div className="how-card-number">04</div>
              <div className="how-card-icon">🛡</div>
              <h3 className="how-card-title">Act Safely</h3>
              <p className="how-card-desc">
                Every action is validated by a safety policy engine
                before execution. No uncontrolled autonomy.
              </p>
            </div>
            <div className="how-card">
              <div className="how-card-number">05</div>
              <div className="how-card-icon">◈</div>
              <h3 className="how-card-title">Verify</h3>
              <p className="how-card-desc">
                Check if the service is actually healthy — not just
                whether the action completed successfully.
              </p>
            </div>
            <div className="how-card">
              <div className="how-card-number">06</div>
              <div className="how-card-icon">↻</div>
              <h3 className="how-card-title">Adapt</h3>
              <p className="how-card-desc">
                If verification fails, re-investigate with new evidence
                and choose a different remediation strategy.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Adaptive Intelligence */}
      <section className="adaptive-section landing-section-dark">
        <div className="container-landing">
          <div className="reveal">
            <span className="section-label">Adaptive Intelligence</span>
            <h2 className="section-title">
              Because a successful action isn't<br />
              the same as a recovered service.
            </h2>
            <p className="section-description">
              When the first fix doesn't work, IncidentPilot doesn't give up —
              it adapts, re-investigates, and tries a different approach.
            </p>
            <p className="section-note">
              Walkthrough of the built-in Adaptive Incident scenario. Run it on the
              dashboard to watch the same loop against live telemetry.
            </p>
          </div>

          <div className="adaptive-visual reveal">
            {/* Attempt 1 — Fails */}
            <div className="adaptive-attempt">
              <div className="adaptive-timeline-line" />
              <div className="adaptive-attempt-content">
                <div className="adaptive-attempt-label failed">
                  <span>ATTEMPT 01</span>
                  <span style={{ fontSize: '10px', opacity: 0.6 }}>— verification failed</span>
                </div>
                <div className="adaptive-attempt-card failed-card">
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Observed: service DOWN, error rate 70%, latency 1000ms</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Decision: restart service (transient failure suspected)</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Safety check: allowed</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Action: restart completed successfully</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker fail">✕</span>
                    <span><strong>Verification: service still unhealthy</strong></span>
                  </div>
                </div>
              </div>
            </div>

            {/* Adaptation divider */}
            <div className="adaptive-divider">
              <div className="adaptive-divider-icon">↻</div>
              <div className="adaptive-divider-text">
                Agent adapts — re-investigating with new evidence
              </div>
            </div>

            {/* Attempt 2 — Succeeds */}
            <div className="adaptive-attempt">
              <div className="adaptive-timeline-line" />
              <div className="adaptive-attempt-content">
                <div className="adaptive-attempt-label success">
                  <span>ATTEMPT 02</span>
                  <span style={{ fontSize: '10px', opacity: 0.6 }}>— verification passed</span>
                </div>
                <div className="adaptive-attempt-card success-card">
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>New evidence: resource exhaustion under sustained load</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Decision: scale service → 3 replicas</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Safety check: allowed</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Action: scaling completed</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span><strong>Verification: service healthy ✓</strong></span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Safety */}
      <section className="landing-section">
        <div className="container-landing">
          <div className="reveal">
            <span className="section-label">Safety First</span>
            <h2 className="section-title">
              AI proposes.<br />
              Policy decides.
            </h2>
            <p className="section-description">
              The LLM never directly executes commands. Every proposed action
              is validated against a safety policy engine before execution.
            </p>
          </div>

          <div className="safety-visual reveal">
            <div className="safety-flow">
              <div className="safety-flow-node">
                <div className="safety-flow-node-icon" style={{ background: 'var(--accent-ultra-light)', color: 'var(--accent-light)' }}>
                  🤖
                </div>
                <div className="safety-flow-node-text">
                  <h4>AI Agent</h4>
                  <p>Proposes a remediation action based on evidence</p>
                </div>
              </div>

              <div className="safety-flow-arrow">↓</div>

              <div className="safety-flow-node">
                <div className="safety-flow-node-icon" style={{ background: 'var(--status-warning-dim)', color: 'var(--status-warning)' }}>
                  🛡
                </div>
                <div className="safety-flow-node-text">
                  <h4>Safety Policy Engine</h4>
                  <p>Validates against predefined safety rules and boundaries</p>
                </div>
              </div>

              <div className="safety-flow-arrow">↓</div>

              <div className="safety-flow-node">
                <div className="safety-flow-node-icon" style={{ background: 'var(--status-healthy-dim)', color: 'var(--status-healthy)' }}>
                  ✓
                </div>
                <div className="safety-flow-node-text">
                  <h4>Allowed → Execute</h4>
                  <p>Only approved actions proceed to execution</p>
                </div>
              </div>
            </div>

            <div className="safety-example">
              <div className="safety-example-title">Example: Blocked Action</div>
              <dl>
                <div className="safety-example-row">
                  <dt>AI proposed</dt>
                  <dd><code style={{ color: 'var(--text-primary)' }}>DELETE DATABASE</code></dd>
                </div>
                <div className="safety-example-row">
                  <dt>Safety check</dt>
                  <dd className="safety-blocked">⊘ BLOCKED</dd>
                </div>
                <div className="safety-example-row">
                  <dt>Reason</dt>
                  <dd style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-sans)' }}>
                    Destructive database operations are prohibited
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="final-cta">
        <div className="final-cta-bg" />
        <div className="container-landing reveal">
          <h2 className="final-cta-title">
            Turn incidents into recoveries.
          </h2>
          <p className="final-cta-subtitle">
            Don't just automate responses — verify them.
          </p>
          <button className="btn-primary" onClick={handleLaunch}>
            Launch IncidentPilot
            <span style={{ fontSize: '14px' }}>→</span>
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        IncidentPilot · Autonomous Incident Response · Built for the future of SRE
      </footer>
    </div>
  );
}
