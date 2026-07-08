import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import ErrorBoundary from './components/ErrorBoundary';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import MeetingPage from './pages/MeetingPage';
import AdminPage from './pages/AdminPage';
import SchedulePage from './pages/SchedulePage';
import SettingsPage from './pages/SettingsPage';
import GanttPage from './pages/GanttPage';
import SearchPage from './pages/SearchPage';

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex justify-center items-center h-screen"><div className="text-gray-500">Загрузка...</div></div>;
  return user ? children : <Navigate to="/login" />;
}

function AdminRoute({ children }) {
  const { isAdmin, loading } = useAuth();
  if (loading) return null;
  return isAdmin ? children : <Navigate to="/" />;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex justify-center items-center h-screen"><div className="text-gray-500">Загрузка...</div></div>;

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" /> : <LoginPage />} />
      <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
        <Route index element={<DashboardPage />} />
        <Route path="meetings/:id" element={<MeetingPage />} />
        <Route path="schedule" element={<SchedulePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="gantt" element={<GanttPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="admin" element={<AdminRoute><AdminPage /></AdminRoute>} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ErrorBoundary>
          <AppRoutes />
        </ErrorBoundary>
      </AuthProvider>
    </BrowserRouter>
  );
}
