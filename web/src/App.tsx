import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { Layout } from './views/Layout';
import { ControlRoom } from './views/ControlRoom';
import { Compliance } from './views/Compliance';
import { Operations } from './views/Operations';
import { Executive } from './views/Executive';

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
