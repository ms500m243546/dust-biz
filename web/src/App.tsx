import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { Layout } from './views/Layout';
import { ControlRoom } from './views/ControlRoom';
import { Compliance } from './views/Compliance';
import { Operations } from './views/Operations';
import { Executive } from './views/Executive';
import { Drift } from './views/Drift';
import type { ReactNode } from 'react';
import type { Role } from './api/types';

const DRIFT_ROLES: ReadonlyArray<Role> = ['environmental_manager', 'admin'];

function RoleGate({ allow, children }: { allow: ReadonlyArray<Role>; children: ReactNode }) {
  const { user } = useAuth();
  if (!user || !allow.includes(user.role)) return <Navigate to="/control-room" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ProtectedRoute>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Navigate to="/control-room" replace />} />
              <Route path="control-room" element={<ControlRoom />} />
              <Route path="compliance" element={<Compliance />} />
              <Route
                path="drift"
                element={
                  <RoleGate allow={DRIFT_ROLES}>
                    <Drift />
                  </RoleGate>
                }
              />
              <Route path="operations" element={<Operations />} />
              <Route path="executive" element={<Executive />} />
              <Route path="*" element={<Navigate to="/control-room" replace />} />
            </Route>
          </Routes>
        </ProtectedRoute>
      </BrowserRouter>
    </AuthProvider>
  );
}
