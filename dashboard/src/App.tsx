import { useEffect } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AppShell } from '@/components/AppShell';
import { Button, EmptyState } from '@/components/ui';
import { isNative } from '@/lib/config';
import { initNative, onAppResume } from '@/lib/native';
import { AlarmsPage } from '@/pages/AlarmsPage';
import { AnalyticsPage } from '@/pages/AnalyticsPage';
import { ChatPage } from '@/pages/ChatPage';
import { CompetitivePage } from '@/pages/CompetitivePage';
import { DevicePage } from '@/pages/DevicePage';
import { LandingPage } from '@/pages/LandingPage';
import { LoginPage } from '@/pages/LoginPage';
import { LogoutPage } from '@/pages/LogoutPage';
import { Overview } from '@/pages/Overview';
import { PomodoroPage } from '@/pages/PomodoroPage';
import { RemindersPage } from '@/pages/RemindersPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { StopwatchPage } from '@/pages/StopwatchPage';
import { StudyPage } from '@/pages/StudyPage';
import { TasksPage } from '@/pages/TasksPage';
import { TimerPage } from '@/pages/TimerPage';
import { useDeskmate } from '@/store/useDeskmate';

function RootRoute() {
  const currentUser = useDeskmate((state) => state.currentUser);
  // If user is already authenticated, go directly to the app dashboard
  if (currentUser) {
    return <Navigate to="/app" replace />;
  }
  // On native mobile app shell (Capacitor), default into login
  if (isNative()) {
    return <Navigate to="/login" replace />;
  }
  return <LandingPage />;
}

/**
 * Route protection guard:
 * Unauthenticated users are strictly barred from accessing the dashboard routes
 * and are redirected to /login with their attempted URL preserved.
 */
function RequireAuth() {
  const currentUser = useDeskmate((state) => state.currentUser);
  const location = useLocation();

  if (!currentUser) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <AppShell />;
}

export function App() {
  const init = useDeskmate((state) => state.init);
  const teardown = useDeskmate((state) => state.teardown);
  const refresh = useDeskmate((state) => state.refresh);
  const reconnect = useDeskmate((state) => state.reconnect);

  useEffect(() => {
    void initNative();
    init();
    return () => teardown();
  }, [init, teardown]);

  // A phone suspends sockets when the app is backgrounded. Resync on return.
  useEffect(() => {
    const off = onAppResume(() => {
      reconnect();
      void refresh();
    });
    return off;
  }, [reconnect, refresh]);

  return (
    <Routes>
      {/* Public Unrestricted Pages */}
      <Route path="/" element={<RootRoute />} />
      <Route path="/landing" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/logout" element={<LogoutPage />} />

      {/* Protected Dashboard Routes — Authenticated Access Only */}
      <Route element={<RequireAuth />}>
        <Route path="/app" element={<Overview />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/competitive" element={<CompetitivePage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/timer" element={<TimerPage />} />
        <Route path="/stopwatch" element={<StopwatchPage />} />
        <Route path="/alarms" element={<AlarmsPage />} />
        <Route path="/pomodoro" element={<PomodoroPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/reminders" element={<RemindersPage />} />
        <Route path="/study" element={<StudyPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/device" element={<DevicePage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>

      {/* Fallback 404 Route */}
      <Route
        path="*"
        element={
          <div className="min-h-screen bg-ink-950 flex items-center justify-center p-4">
            <EmptyState
              title="Page not found"
              body="That route does not exist."
              action={
                <div className="flex items-center gap-3 mt-3">
                  <Link to="/app">
                    <Button variant="primary" size="sm">
                      Go to Dashboard
                    </Button>
                  </Link>
                  <Link to="/">
                    <Button variant="outline" size="sm">
                      Landing Page
                    </Button>
                  </Link>
                </div>
              }
            />
          </div>
        }
      />
    </Routes>
  );
}
