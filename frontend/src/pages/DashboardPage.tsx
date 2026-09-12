import { useLayoutEffect } from 'react';
import { Link } from 'react-router-dom';
import { IncidentPilotDashboard } from '../components/IncidentPilot';

export default function DashboardPage() {
  useLayoutEffect(() => { window.scrollTo(0, 0); }, []);
  return <div><nav style={{padding: '12px 24px'}} aria-label="Page navigation"><Link to="/">← Product overview</Link></nav><IncidentPilotDashboard /></div>;
}
