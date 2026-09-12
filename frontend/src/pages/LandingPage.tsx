import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import '../styles/landing.css';

/* ═══════════════════════════════════════════════
   PIPELINE ANIMATION — The centerpiece
   ═══════════════════════════════════════════════ */

type NodeState = 'idle' | 'active' | 'completed' | 'failed' | 'retry';

interface PipelineNodeData {
  id: string;
  label: string;
  icon: string;
  state: NodeState;
}

const INITIAL_NODES: PipelineNodeData[] = [
  { id: 'service', label: 'Service', icon: '◆', state: 'idle' },
  { id: 'observe', label: 'Observe', icon: '◎', state: 'idle' },
  { id: 'decide', label: 'Decide', icon: '⬡', state: 'idle' },
  { id: 'act', label: 'Act', icon: '▶', state: 'idle' },
  { id: 'verify', label: 'Verify', icon: '◈', state: 'idle' },
  { id: 'recover', label: 'Recover', icon: '●', state: 'idle' },
];

type ConnectorState = 'idle' | 'active' | 'completed' | 'failed';

function PipelineAnimation() {
  const [nodes, setNodes] = useState<PipelineNodeData[]>(INITIAL_NODES);
  const [connectorStates, setConnectorStates] = useState<ConnectorState[]>(
    new Array(5).fill('idle')
  );
  const [statusText, setStatusText] = useState('System healthy');
  const [statusClass, setStatusClass] = useState('healthy');
  const [showRetryArc, setShowRetryArc] = useState(false);
  const [cycle, setCycle] = useState(0);

  const resetState = useCallback(() => {
    setNodes(INITIAL_NODES.map(n => ({ ...n, state: 'idle' })));
    setConnectorStates(new Array(5).fill('idle'));
    setStatusText('System healthy');
    setStatusClass('healthy');
    setShowRetryArc(false);
  }, []);

  useEffect(() => {
    // Check reduced motion
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion) {
      setNodes(INITIAL_NODES.map(n => ({ ...n, state: 'completed' })));
      setConnectorStates(new Array(5).fill('completed'));
      setStatusText('Incident resolved');
      setStatusClass('resolved');
      return;
    }

    const steps: Array<{ delay: number; action: () => void }> = [];
    let d = 2000; // initial wait

    // Phase 1: Service goes down
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => n.id === 'service' ? { ...n, state: 'failed' } : n));
      setStatusText('⚠ Incident detected');
      setStatusClass('failed');
    }});

    // Phase 2: Observe
    d += 1200;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'observe') return { ...n, state: 'active' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[0] = 'active'; return c; });
      setStatusText('Observing service state...');
      setStatusClass('investigating');
    }});

    // Phase 3: Decide
    d += 1400;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'observe') return { ...n, state: 'completed' };
        if (n.id === 'decide') return { ...n, state: 'active' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[0] = 'completed'; c[1] = 'active'; return c; });
      setStatusText('Deciding remediation...');
      setStatusClass('investigating');
    }});

    // Phase 4: Act
    d += 1200;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'decide') return { ...n, state: 'completed' };
        if (n.id === 'act') return { ...n, state: 'active' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[1] = 'completed'; c[2] = 'active'; return c; });
      setStatusText('Executing action...');
      setStatusClass('investigating');
    }});

    // Phase 5: Verify — FAILS
    d += 1400;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'act') return { ...n, state: 'completed' };
        if (n.id === 'verify') return { ...n, state: 'active' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[2] = 'completed'; c[3] = 'active'; return c; });
      setStatusText('Verifying recovery...');
      setStatusClass('investigating');
    }});

    d += 1400;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'verify') return { ...n, state: 'failed' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[3] = 'failed'; return c; });
      setStatusText('✕ Verification failed — adapting...');
      setStatusClass('failed');
      setShowRetryArc(true);
    }});

    // Phase 6: Retry loop — back to observe
    d += 1800;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'observe') return { ...n, state: 'active' };
        if (n.id === 'decide' || n.id === 'act') return { ...n, state: 'idle' };
        if (n.id === 'verify') return { ...n, state: 'idle' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[1] = 'idle'; c[2] = 'idle'; c[3] = 'idle'; c[0] = 'active'; return c; });
      setShowRetryArc(false);
      setStatusText('Re-observing with new evidence...');
      setStatusClass('adapting');
    }});

    // Phase 7: Second pass — decide
    d += 1200;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'observe') return { ...n, state: 'completed' };
        if (n.id === 'decide') return { ...n, state: 'active' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[0] = 'completed'; c[1] = 'active'; return c; });
      setStatusText('New decision: rollback deployment');
      setStatusClass('investigating');
    }});

    // Phase 8: Act again
    d += 1200;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'decide') return { ...n, state: 'completed' };
        if (n.id === 'act') return { ...n, state: 'active' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[1] = 'completed'; c[2] = 'active'; return c; });
      setStatusText('Executing rollback...');
      setStatusClass('investigating');
    }});

    // Phase 9: Verify — SUCCEEDS
    d += 1400;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'act') return { ...n, state: 'completed' };
        if (n.id === 'verify') return { ...n, state: 'active' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[2] = 'completed'; c[3] = 'active'; return c; });
      setStatusText('Verifying recovery...');
      setStatusClass('investigating');
    }});

    d += 1400;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'verify') return { ...n, state: 'completed' };
        if (n.id === 'recover') return { ...n, state: 'active' };
        return n;
      }));
      setConnectorStates(prev => { const c = [...prev]; c[3] = 'completed'; c[4] = 'active'; return c; });
      setStatusText('✓ Verification passed');
      setStatusClass('resolved');
    }});

    // Phase 10: Resolved
    d += 1200;
    steps.push({ delay: d, action: () => {
      setNodes(prev => prev.map(n => {
        if (n.id === 'service') return { ...n, state: 'completed' };
        if (n.id === 'recover') return { ...n, state: 'completed' };
        return n;
      }));
      setConnectorStates(new Array(5).fill('completed'));
      setStatusText('✓ Incident resolved');
      setStatusClass('resolved');
    }});

    // Reset and loop
    d += 4000;
    steps.push({ delay: d, action: () => {
      resetState();
      setCycle(c => c + 1);
    }});

    const timeouts = steps.map(s => setTimeout(s.action, s.delay));

    return () => timeouts.forEach(clearTimeout);
  }, [cycle, resetState]);

  return (
    <div className="pipeline-container">
      <div className="pipeline-wrapper">
        {nodes.map((node, i) => (
          <div key={node.id} style={{ display: 'flex', alignItems: 'center' }}>
            <div className={`pipeline-node ${node.state !== 'idle' ? node.state : ''}`}>
              <div className="pipeline-node-circle">{node.icon}</div>
              <span className="pipeline-node-label">{node.label}</span>
            </div>
            {i < nodes.length - 1 && (
              <div className={`pipeline-connector ${connectorStates[i] !== 'idle' ? connectorStates[i] : ''}`}>
                <div className="pipeline-connector-fill" />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Retry arc SVG */}
      <div className={`pipeline-retry-arc ${showRetryArc ? 'visible' : ''}`}>
        <svg width="200" height="40" viewBox="0 0 200 40" fill="none">
          <path
            d="M170 35 C170 10, 30 10, 30 35"
            stroke="var(--status-warning)"
            strokeWidth="1.5"
            strokeDasharray="4 3"
            fill="none"
            opacity="0.6"
          />
          <polygon points="28,30 34,38 24,38" fill="var(--status-warning)" opacity="0.6" />
        </svg>
      </div>

      <div className={`pipeline-status ${statusClass}`}>
        {statusText}
      </div>
    </div>
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
  const landingPageRef = useRef<HTMLDivElement>(null);
  const bottomSentinelRef = useRef<HTMLDivElement>(null);
  const isTransitioningRef = useRef(false);
  const mountCooldownRef = useRef(true); // Prevents instant re-trigger on browser-back

  // Clean reset when page mounts (supporting browser back navigation)
  useEffect(() => {
    isTransitioningRef.current = false;
    mountCooldownRef.current = true;
    if (landingPageRef.current) {
      gsap.set(landingPageRef.current, { clearProps: 'all' });
    }
    // Allow transitions only after cooldown (prevents back-button re-trigger loop)
    const cooldownTimer = setTimeout(() => {
      mountCooldownRef.current = false;
    }, 600);
    return () => clearTimeout(cooldownTimer);
  }, []);

  // Smooth GSAP transition when scrolling into Dashboard
  const triggerScrollTransition = useCallback(() => {
    if (isTransitioningRef.current || mountCooldownRef.current) return;
    isTransitioningRef.current = true;

    if (landingPageRef.current) {
      gsap.to(landingPageRef.current, {
        y: -90,
        opacity: 0,
        scale: 0.985,
        duration: 0.65,
        ease: 'power2.inOut',
        onComplete: () => {
          navigate('/dashboard', { state: { fromScrollTransition: true } });
        }
      });
    } else {
      navigate('/dashboard', { state: { fromScrollTransition: true } });
    }
  }, [navigate]);

  // 1) Detect when user approaches/reaches the bottom of LandingPage
  useEffect(() => {
    const handleScroll = () => {
      if (mountCooldownRef.current) return;
      const scrollBottom = window.innerHeight + window.scrollY;
      const documentHeight = document.documentElement.scrollHeight;

      if (scrollBottom >= documentHeight - 70 && window.scrollY > 300) {
        triggerScrollTransition();
      } else if (scrollBottom < documentHeight - 250) {
        // Re-arm if user scrolls back up
        isTransitioningRef.current = false;
      }
    };

    const handleWheel = (e: WheelEvent) => {
      if (mountCooldownRef.current) return;
      if (e.deltaY > 0 && window.scrollY > 300) {
        const scrollBottom = window.innerHeight + window.scrollY;
        const documentHeight = document.documentElement.scrollHeight;
        if (scrollBottom >= documentHeight - 90) {
          triggerScrollTransition();
        }
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('wheel', handleWheel, { passive: true });

    // Also observe bottom sentinel with IntersectionObserver
    const sentinel = bottomSentinelRef.current;
    let observer: IntersectionObserver | null = null;
    if (sentinel) {
      observer = new IntersectionObserver(
        (entries) => {
          if (mountCooldownRef.current) return;
          const [entry] = entries;
          if (entry.isIntersecting && window.scrollY > 300) {
            triggerScrollTransition();
          }
        },
        { threshold: 0.1 }
      );
      observer.observe(sentinel);
    }

    return () => {
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('wheel', handleWheel);
      if (observer && sentinel) observer.unobserve(sentinel);
    };
  }, [triggerScrollTransition]);

  // Existing Hero button click handler - untouched and works directly
  const handleLaunch = () => {
    navigate('/dashboard', { state: { fromScrollTransition: true } });
  };

  // Directly show the bottom half of page 2 (the dashboard) and skip the above animation
  const handleDirectLaunch = () => {
    navigate('/dashboard#incident-pilot-section', { state: { skipHero: true } });
  };

  const handleSeeHow = () => {
    document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div ref={landingPageRef} className="landing-page">
      {/* Navigation */}
      <nav className="landing-nav">
        <div className="landing-nav-brand">
          <div className="brand-icon">⚡</div>
          IncidentPilot
        </div>
        <button className="landing-nav-cta" onClick={handleDirectLaunch}>
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

        <PipelineAnimation />
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
                    <span>Observed: service DOWN, error rate 78%</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Decision: scale service → 4 replicas</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Safety check: allowed</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Action: scaling completed successfully</span>
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
                    <span>New evidence: NullPointerException in v41</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Decision: rollback to v40 (confidence 91%)</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Safety check: allowed</span>
                  </div>
                  <div className="adaptive-step-row">
                    <span className="adaptive-step-marker pass">✓</span>
                    <span>Action: rollback completed</span>
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
          <div className="scroll-transition-hint" onClick={triggerScrollTransition} role="button" tabIndex={0}>
            <span className="scroll-transition-label">Scroll down to enter Dashboard</span>
            <div className="scroll-transition-arrow">↓</div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        IncidentPilot · Autonomous Incident Response · Built for the future of SRE
      </footer>
      {/* Bottom sentinel to detect scroll end */}
      <div ref={bottomSentinelRef} style={{ height: '2px', width: '100%', pointerEvents: 'none' }} />
    </div>
  );
}
