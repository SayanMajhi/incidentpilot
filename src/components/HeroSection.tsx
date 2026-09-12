import React, { useEffect, useRef, useState } from 'react';

// Smooth cubic easing function for organic movement
function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

export const HeroSection: React.FC<{ onScrollComplete: () => void }> = ({ onScrollComplete }) => {
  const heroRef = useRef<HTMLDivElement>(null);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [hasCompleted, setHasCompleted] = useState(false);
  const [time, setTime] = useState(0);

  // Smooth scroll progress handler
  useEffect(() => {
    const handleScroll = () => {
      if (!heroRef.current) return;
      const rect = heroRef.current.getBoundingClientRect();
      const heroHeight = heroRef.current.offsetHeight;
      const scrolled = -rect.top;
      const progress = Math.max(0, Math.min(1, scrolled / (heroHeight - window.innerHeight)));
      setScrollProgress(progress);
      if (progress >= 0.95 && !hasCompleted) {
        setHasCompleted(true);
        onScrollComplete();
      }
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [hasCompleted, onScrollComplete]);

  // Organic idle floating animation loop
  useEffect(() => {
    let animId: number;
    let startTime = performance.now();
    const loop = (now: number) => {
      setTime((now - startTime) / 1000);
      animId = requestAnimationFrame(loop);
    };
    animId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId);
  }, []);

  // Eased progress (goes smoothly from 0 to 1)
  const animProgress = easeOutCubic(scrollProgress);

  // --- INDEPENDENT NATURAL MOTION CALCULATIONS ---
  // Left Hand (Robotic Arm):
  // Starts far left (-100vw, +50vh, -20deg), moves inward to (-0.65vw, 0vh, -0.5deg)
  const leftFloatY = Math.sin(time * 1.4) * 0.6; // subtle idle float (vh)
  const leftFloatRot = Math.cos(time * 1.2) * 0.4; // subtle rotation (deg)
  
  const leftTX = -100 * (1 - animProgress) - 0.65;
  const leftTY = 50 * (1 - animProgress) + leftFloatY;
  const leftRot = -20 * (1 - animProgress) + leftFloatRot - 0.5 * animProgress;

  // Right Hand (Human Arm):
  // Starts far right (+100vw, -50vh, +20deg), moves inward to (-7.0vw, 0vh, +0.5deg)
  const rightFloatY = Math.cos(time * 1.5 + 0.5) * 0.6; // out-of-phase float (vh)
  const rightFloatRot = Math.sin(time * 1.3 + 0.5) * 0.4; // out-of-phase tilt (deg)

  const rightTX = 100 * (1 - animProgress) - 7.0;
  const rightTY = -50 * (1 - animProgress) + rightFloatY;
  const rightRot = 20 * (1 - animProgress) + rightFloatRot + 0.5 * animProgress;

  // Contact glow intensity (builds up as fingertips approach the ~4px gap)
  const proximity = Math.pow(animProgress, 2.5);
  const glowIntensity = proximity * (0.8 + 0.2 * Math.sin(time * 3.5));

  // Atmospheric background pulse
  const atmosPulse = 0.35 + 0.15 * Math.sin(time * 1.8);

  // Text opacities
  const titleOpacity = scrollProgress < 0.1
    ? scrollProgress / 0.1
    : scrollProgress > 0.65
      ? Math.max(0, 1 - (scrollProgress - 0.65) / 0.2)
      : 1;

  const scrollHintOpacity = scrollProgress < 0.05 ? 1 : Math.max(0, 1 - scrollProgress * 12);

  // Shared transparent image style
  const sharedImgStyle: React.CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: 'contain',
    objectPosition: 'center center',
    display: 'block',
  };

  return (
    <div ref={heroRef} style={{ height: '280vh', position: 'relative' }}>
      <div style={{
        position: 'sticky',
        top: 0,
        height: '100vh',
        width: '100%',
        overflow: 'hidden',
        background: 'radial-gradient(ellipse at center, #1c0505 0%, #0c0202 60%, #000000 100%)',
        zIndex: 50,
      }}>

        {/* Atmospheric Background Glow */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 1,
          background: `radial-gradient(ellipse 65% 45% at 50% 50.7%, rgba(180, 30, 15, ${atmosPulse}) 0%, transparent 70%)`,
        }} />

        {/* Subtle Dither Noise */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 2, opacity: 0.45,
          backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.08) 1px, transparent 1px)',
          backgroundSize: '4px 4px',
        }} />

        {/* Divine Anticipation Spark Lines */}
        <svg viewBox="-50 -50 100 100" style={{
          position: 'absolute', top: '50.7%', left: '50.0%',
          transform: 'translate(-50%, -50%)',
          width: '240px', height: '240px', zIndex: 5,
          opacity: glowIntensity * 0.9, pointerEvents: 'none',
        }}>
          {[0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330].map((angle) => {
            const len = 8 + glowIntensity * 22;
            const startR = 3 + glowIntensity * 4;
            return (
              <line key={angle} x1={0} y1={0} x2={0} y2={-(startR + len)}
                stroke={`rgba(255, ${180 + (angle % 60)}, 90, ${0.4 + glowIntensity * 0.6})`}
                strokeWidth={0.6 + glowIntensity * 0.6} strokeLinecap="round"
                transform={`rotate(${angle}) translate(0, -${startR})`}
              />
            );
          })}
        </svg>

        {/* Soft Touch Bloom (Centered right at fingertip contact point) */}
        <div style={{
          position: 'absolute', left: '50.0%', top: '50.7%', pointerEvents: 'none', zIndex: 4,
          width: `${120 + glowIntensity * 340}px`,
          height: `${80 + glowIntensity * 240}px`,
          transform: 'translate(-50%, -50%)',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(255,220,140,0.85) 0%, rgba(230,70,25,0.4) 45%, transparent 75%)',
          opacity: glowIntensity,
          filter: 'blur(16px)',
        }} />

        {/*
          =====================================================================
          LEFT HAND CONTAINER (ROBOTIC ARM)
          Uses 100% PURE TRANSPARENT PNG: /left-hand.png
          =====================================================================
        */}
        <div style={{
          position: 'absolute', inset: 0, zIndex: 3,
          transform: `translate(${leftTX}vw, ${leftTY}vh) rotate(${leftRot}deg)`,
          transformOrigin: 'center center',
          willChange: 'transform',
        }}>
          <img src="/left-hand.png" alt="Robotic Hand" style={sharedImgStyle} />
        </div>

        {/*
          =====================================================================
          RIGHT HAND CONTAINER (HUMAN ARM)
          Uses 100% PURE TRANSPARENT PNG: /right-hand.png
          =====================================================================
        */}
        <div style={{
          position: 'absolute', inset: 0, zIndex: 3,
          transform: `translate(${rightTX}vw, ${rightTY}vh) rotate(${rightRot}deg)`,
          transformOrigin: 'center center',
          willChange: 'transform',
        }}>
          <img src="/right-hand.png" alt="Human Hand" style={sharedImgStyle} />
        </div>

        {/* Title Overlay */}
        <div style={{
          position: 'absolute', top: '8%', left: '50%', zIndex: 6,
          transform: 'translateX(-50%)', textAlign: 'center',
          opacity: titleOpacity, pointerEvents: 'none',
          width: '85%', maxWidth: '750px',
        }}>
          <h1 style={{
            fontFamily: 'Arial, Helvetica, sans-serif',
            fontSize: 'clamp(2.2rem, 5.2vw, 3.8rem)',
            fontWeight: 800, color: '#f0ede8',
            letterSpacing: '-0.03em', lineHeight: 1.1, margin: 0,
            textShadow: '0 0 50px rgba(220,50,20,0.5)',
          }}>
            AI Meets Human.<br />Incidents End Here.
          </h1>
          <p style={{
            fontFamily: 'Georgia, "Times New Roman", serif',
            fontSize: 'clamp(0.95rem, 1.3vw, 1.15rem)',
            fontStyle: 'italic',
            color: 'rgba(255,200,170,0.5)', marginTop: '1.2rem',
            letterSpacing: '0.04em',
          }}>
            In every system, in every incident, in every moment of chaos... there is order waiting to be found.
          </p>
        </div>

        {/* Scroll Hint */}
        <div style={{
          position: 'absolute', bottom: '3.5%', left: '50%', zIndex: 6,
          transform: 'translateX(-50%)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.4rem',
          opacity: scrollHintOpacity,
        }}>
          <span style={{
            fontFamily: 'Arial, sans-serif', fontSize: '0.68rem',
            color: 'rgba(255,180,140,0.4)', letterSpacing: '0.14em',
            textTransform: 'uppercase', fontWeight: 700,
          }}>Scroll to connect</span>
          <div style={{
            width: '1px', height: '32px',
            background: 'linear-gradient(to bottom, rgba(255,160,80,0.5), transparent)',
            animation: 'scrollPulse 2s ease-in-out infinite',
          }} />
        </div>

      </div>
    </div>
  );
};
