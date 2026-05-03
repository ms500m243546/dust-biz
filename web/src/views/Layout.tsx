import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import type { Role } from '../api/types';

// Drift watch is a model-trust surface — env_manager owns model decay
// and admin sees everything. Shift-supervisors get calibration on the
// recommendation card already; sustained drift trends are not their
// real-time decision surface.
const DRIFT_ROLES: ReadonlyArray<Role> = ['environmental_manager', 'admin'];

export function Layout() {
  const { user, logout } = useAuth();
  const canSeeDrift = user != null && DRIFT_ROLES.includes(user.role);
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">DustOps AI</div>
        <nav className="primary-nav">
          <NavLink to="/control-room">Control Room</NavLink>
          <NavLink to="/compliance">Environmental</NavLink>
          {canSeeDrift && <NavLink to="/drift">Drift</NavLink>}
          <NavLink to="/operations">Operations</NavLink>
          <NavLink to="/executive">Executive</NavLink>
        </nav>
        <div className="user-strip">
          <span className="user-name">{user?.username}</span>
          <span className="user-role">{user?.role}</span>
          <button onClick={logout} className="link-button">Sign out</button>
        </div>
      </header>
      <main className="view-host">
        <Outlet />
      </main>
    </div>
  );
}
