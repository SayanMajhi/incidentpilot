import { useLayoutEffect } from 'react';
import { Link } from 'react-router-dom';
import { IncidentPilotDashboard } from '../components/IncidentPilot';

export default function DashboardPage() {
  useLayoutEffect(() => { window.scrollTo(0, 0); }, []);
  return <div><nav style={{ padding: '16px 24px' }} aria-label="Page navigation">
  <Link
    to="/"
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '8px',
      padding: '8px 16px',
      borderRadius: '999px',
      background: 'rgba(21, 29, 49, 0.7)',
      border: '1px solid #2b3856',
      color: '#cbd5e1',
      fontSize: '0.85rem',
      fontWeight: 600,
      textDecoration: 'none',
      transition: 'all 0.2s ease',
      backdropFilter: 'blur(8px)',
      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.25)',
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.borderColor = '#818cf8';
      e.currentTarget.style.color = '#ffffff';
      e.currentTarget.style.transform = 'translateX(-3px)';
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.borderColor = '#2b3856';
      e.currentTarget.style.color = '#cbd5e1';
      e.currentTarget.style.transform = 'translateX(0)';
    }}
  >
    <span style={{ color: '#818cf8', fontSize: '1rem' }}>←</span>
    <span>Back to Product Overview</span>
  </Link>
</nav><IncidentPilotDashboard /></div>;
}
