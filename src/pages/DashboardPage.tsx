import React, { useLayoutEffect, useEffect, useRef, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import { HeroSection } from '../components/HeroSection';
import { IncidentPilotDashboard } from '../components/IncidentPilot';

export const DashboardPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const mainRef = useRef<HTMLElement>(null);
  const isTransitioningBackRef = useRef(false);
  const upDeltaAccum = useRef(0);
  const mountCooldownRef = useRef(true); // Prevents scroll-up trigger during entrance animation

  const skipHero = Boolean(
    location.state?.skipHero ||
    location.hash === '#incident-pilot-section' ||
    location.hash === '#dashboard'
  );
  const fromScrollTransition = Boolean(location.state?.fromScrollTransition);

  // Cooldown: disable scroll-up detection for 1.2s after mount so the entrance
  // animation and auto-scroll don't accidentally trigger a back-navigation
  useEffect(() => {
    mountCooldownRef.current = true;
    const timer = setTimeout(() => {
      mountCooldownRef.current = false;
    }, 1200);
    return () => clearTimeout(timer);
  }, []);

  // Reverse scroll-up transition back to LandingPage
  const triggerBackTransition = useCallback(() => {
    if (isTransitioningBackRef.current) return;
    isTransitioningBackRef.current = true;

    if (mainRef.current) {
      gsap.to(mainRef.current, {
        opacity: 0,
        y: 60,
        duration: 0.4,
        ease: 'power2.in',
        onComplete: () => {
          navigate('/');
        }
      });
    } else {
      navigate('/');
    }
  }, [navigate]);

  // Detect upward scroll when at the very top of the page
  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      if (isTransitioningBackRef.current || mountCooldownRef.current) return;

      if (window.scrollY <= 5 && e.deltaY < 0) {
        upDeltaAccum.current += Math.abs(e.deltaY);
        // Require a cumulative upward delta to avoid accidental triggers
        if (upDeltaAccum.current > 80) {
          triggerBackTransition();
        }
      } else {
        // Reset accumulator if user scrolls down or is not at top
        upDeltaAccum.current = 0;
      }
    };

    window.addEventListener('wheel', handleWheel, { passive: true });
    return () => {
      window.removeEventListener('wheel', handleWheel);
    };
  }, [triggerBackTransition]);

  useLayoutEffect(() => {
    if (skipHero) {
      const jumpToDashboard = () => {
        const el = document.getElementById('incident-pilot-section');
        if (el) {
          el.scrollIntoView({ behavior: 'instant', block: 'start' });
        } else {
          window.scrollTo({ top: window.innerHeight * 2.8, behavior: 'instant' });
        }
      };

      jumpToDashboard();
      const rId = requestAnimationFrame(jumpToDashboard);
      const timer = setTimeout(jumpToDashboard, 60);

      return () => {
        cancelAnimationFrame(rId);
        clearTimeout(timer);
      };
    } else if (fromScrollTransition) {
      // Natural continuation of downward scroll momentum
      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });

      // 1) Smooth entrance fade/glide
      if (mainRef.current) {
        gsap.fromTo(
          mainRef.current,
          { opacity: 0, y: 50, scale: 1.01 },
          {
            opacity: 1,
            y: 0,
            scale: 1,
            duration: 0.6,
            ease: 'power2.out',
            clearProps: 'transform'
          }
        );
      }

      // 2) Smooth automatic scroll down to the exact hands contact point (progress ~0.58)
      const targetProgress = 0.58;
      const targetScrollY = targetProgress * (window.innerHeight * 1.8);

      const scrollProxy = { y: 0 };
      const autoScrollTween = gsap.to(scrollProxy, {
        y: targetScrollY,
        duration: 0.8,
        delay: 0.05,
        ease: 'power2.out',
        onUpdate: () => {
          window.scrollTo(0, scrollProxy.y);
        }
      });

      return () => {
        autoScrollTween.kill();
      };
    } else {
      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    }
  }, [skipHero, fromScrollTransition]);

  const handleScrollComplete = () => {
    // Scroll animation complete — no-op callback for HeroSection
  };

  return (
    <main ref={mainRef} style={{ position: 'relative', background: '#0a0a0a', minHeight: '100vh' }}>
      <HeroSection onScrollComplete={handleScrollComplete} />
      <section className="incidentpilot-section" id="incident-pilot-section" style={{ position: 'relative', zIndex: 60 }}>
        <IncidentPilotDashboard />
      </section>
    </main>
  );
};

export default DashboardPage;
