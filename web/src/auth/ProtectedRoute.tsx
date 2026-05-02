import type { ReactNode } from 'react';
import { useAuth } from './AuthContext';
import { LoginPage } from './LoginPage';

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-shell">Loading...</div>;
  if (!user) return <LoginPage />;
  return <>{children}</>;
}
