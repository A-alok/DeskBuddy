import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui';
import { IconLock, IconLogout } from '@/components/icons';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';

export function LogoutPage() {
  const navigate = useNavigate();
  const currentUser = useDeskmate((state) => state.currentUser);
  const logout = useDeskmate((state) => state.logout);
  const pushToast = useDeskmate((state) => state.pushToast);
  const [loggingOut, setLoggingOut] = useState(false);

  const handleConfirmLogout = () => {
    tap();
    setLoggingOut(true);
    setTimeout(() => {
      logout();
      setLoggingOut(false);
      pushToast({
        kind: 'info',
        title: 'Signed Out',
        body: 'You have been safely signed out of your AI DeskMate account.',
      });
      navigate('/login', { replace: true });
    }, 400);
  };

  return (
    <div className="min-h-screen bg-ink-950 text-ink-200 flex flex-col justify-between p-4 sm:p-6 font-sans antialiased selection:bg-accent/30 selection:text-accent">
      {/* Top Header */}
      <header className="max-w-4xl w-full mx-auto flex items-center justify-between pb-4">
        <Link
          to={currentUser ? '/app' : '/login'}
          className="flex items-center gap-2 text-xs font-semibold text-ink-400 hover:text-accent transition-colors"
        >
          <span>{currentUser ? '← Return to Dashboard' : '← Go to Login'}</span>
        </Link>

        <div className="flex items-center gap-2">
          <span className="size-2 rounded-full bg-accent animate-pulse" />
          <span className="text-xs font-mono text-ink-400">AI DeskMate Security</span>
        </div>
      </header>

      {/* Main Logout Card */}
      <main className="max-w-md w-full mx-auto my-auto py-4">
        <div className="rounded-3xl p-6 sm:p-8 bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)]">
          {currentUser ? (
            <>
              {/* Icon & Heading */}
              <div className="text-center mb-6">
                <div className="size-14 rounded-2xl bg-danger/15 border border-danger/30 flex items-center justify-center text-danger mx-auto mb-3 shadow-[0_0_20px_rgba(239,68,68,0.2)]">
                  <IconLogout className="size-7" />
                </div>
                <h2 className="text-2xl font-black text-ink-100 tracking-tight">
                  Sign Out
                </h2>
                <p className="text-xs text-ink-400 mt-1">
                  Are you sure you want to end your active session on this device?
                </p>
              </div>

              {/* Active Account Info Box */}
              <div className="mb-6 p-4 rounded-2xl bg-ink-950 border border-ink-800/80 shadow-[inset_0_2px_4px_rgba(0,0,0,0.3)]">
                <div className="flex items-center gap-3.5">
                  <div className="size-12 rounded-xl bg-ink-900 border border-ink-800 flex items-center justify-center text-2xl shadow-sm">
                    {currentUser.avatar || '⚡'}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] uppercase font-bold text-accent tracking-wider font-mono">
                      Active Account
                    </p>
                    <h4 className="text-sm font-bold text-ink-100 truncate">
                      {currentUser.display_name}
                    </h4>
                    <p className="text-xs text-ink-400 font-mono">
                      @{currentUser.username}
                    </p>
                  </div>
                </div>

                {currentUser.competition_code && (
                  <div className="mt-3 pt-3 border-t border-ink-900 flex justify-between items-center text-xs">
                    <span className="text-ink-400 text-[11px]">Competition Code:</span>
                    <span className="font-mono font-bold text-amber-400 bg-ink-900 px-2 py-0.5 rounded border border-ink-800">
                      {currentUser.competition_code}
                    </span>
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex flex-col gap-3">
                <Button
                  variant="primary"
                  onClick={handleConfirmLogout}
                  disabled={loggingOut}
                  className="w-full !bg-danger hover:!bg-danger/90 !text-white flex items-center justify-center gap-2 py-2.5 font-bold cursor-pointer"
                >
                  <IconLogout className="size-4" />
                  <span>{loggingOut ? 'Signing Out...' : 'Yes, Sign Out'}</span>
                </Button>

                <Button
                  variant="outline"
                  onClick={() => navigate('/app')}
                  disabled={loggingOut}
                  className="w-full text-xs font-semibold py-2.5 cursor-pointer"
                >
                  Cancel (Stay Signed In)
                </Button>
              </div>
            </>
          ) : (
            <>
              {/* Logged Out State */}
              <div className="text-center py-4">
                <div className="size-14 rounded-2xl bg-accent/15 border border-accent/30 flex items-center justify-center text-accent mx-auto mb-3 shadow-[var(--shadow-neo-glow)]">
                  <IconLock className="size-7" />
                </div>
                <h2 className="text-2xl font-black text-ink-100 tracking-tight">
                  Signed Out
                </h2>
                <p className="text-xs text-ink-400 mt-2 max-w-xs mx-auto">
                  You are not signed in. Access to device controls, study quizzes, and telemetry requires authentication.
                </p>

                <div className="mt-6 flex flex-col gap-2.5">
                  <Button
                    variant="primary"
                    onClick={() => navigate('/login')}
                    className="w-full py-2.5 font-bold flex items-center justify-center gap-2"
                  >
                    <span>Go to Sign In</span>
                    <span>→</span>
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="max-w-4xl w-full mx-auto text-center py-2 text-[11px] text-ink-500">
        AI DeskMate • ESP32-S3 IoT Hardware & Productivity System
      </footer>
    </div>
  );
}
