import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">DustOps AI</div>
        <nav className="primary-nav">
          <NavLink to="/control-room">Control Room</NavLink>
          <NavLink to="/compliance">Environmental</NavLink>
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
