import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button, Input, cx } from '@/components/ui';
import {
  IconChip,
  IconEye,
  IconEyeOff,
  IconGear,
  IconLock,
  IconLogout,
} from '@/components/icons';
import { api } from '@/lib/api';
import { apiBaseUrl, deviceId, setApiBaseUrl, setDeviceId } from '@/lib/config';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';

const AVATAR_OPTIONS = ['⚡', '👩‍🎓', '🧑‍💻', '🚀', '🦉', '🦁', '🎯', '🔬', '💡', '🏆'];

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const currentUser = useDeskmate((state) => state.currentUser);
  const setCurrentUser = useDeskmate((state) => state.setCurrentUser);
  const logout = useDeskmate((state) => state.logout);
  const pushToast = useDeskmate((state) => state.pushToast);
  const status = useDeskmate((state) => state.status);

  // Path the user originally wanted to visit before being blocked
  const attemptedFrom = (location.state as { from?: { pathname?: string } })?.from?.pathname;
  const targetDestination = attemptedFrom && attemptedFrom !== '/login' ? attemptedFrom : '/app';

  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login');
  const [submitting, setSubmitting] = useState(false);

  // Login form state
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);

  // Register form state
  const [regUsername, setRegUsername] = useState('');
  const [regDisplayName, setRegDisplayName] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regConfirmPassword, setRegConfirmPassword] = useState('');
  const [showRegPassword, setShowRegPassword] = useState(false);
  const [regAvatar, setRegAvatar] = useState('⚡');
  const [regDeviceId, setRegDeviceId] = useState('');

  // Connection settings state
  const [showSettings, setShowSettings] = useState(false);
  const [customApiUrl, setCustomApiUrl] = useState(apiBaseUrl());
  const [customDeviceId, setCustomDeviceId] = useState(deviceId());

  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const username = loginUsername.trim();
    if (!username) return;

    tap();
    setSubmitting(true);
    try {
      const user = await api.auth.login(username, loginPassword || undefined);
      setCurrentUser(user);
      pushToast({
        kind: 'success',
        title: 'Authentication Successful',
        body: `Welcome back, ${user.display_name}!`,
      });
      navigate(targetDestination, { replace: true });
    } catch (err: any) {
      const detail = err?.detail || err?.message || 'Login failed';
      pushToast({
        kind: 'error',
        title: 'Authentication Failed',
        body: detail,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUsername = regUsername.trim().toLowerCase().replace(/[^a-z0-9_\-]/g, '');
    if (!cleanUsername) return;

    if (regPassword && regPassword.length < 4) {
      pushToast({
        kind: 'error',
        title: 'Password Too Short',
        body: 'Password must be at least 4 characters.',
      });
      return;
    }

    if (regPassword && regPassword !== regConfirmPassword) {
      pushToast({
        kind: 'error',
        title: 'Passwords Do Not Match',
        body: 'Please ensure both password fields match.',
      });
      return;
    }

    tap();
    setSubmitting(true);
    try {
      const newUser = await api.auth.register({
        username: cleanUsername,
        password: regPassword || undefined,
        display_name: regDisplayName.trim() || undefined,
        avatar: regAvatar,
        device_id: regDeviceId.trim() || undefined,
      });
      setCurrentUser(newUser);
      pushToast({
        kind: 'success',
        title: 'Account Registered & Authenticated!',
        body: `Welcome to AI DeskMate, ${newUser.display_name}!`,
      });
      navigate(targetDestination, { replace: true });
    } catch (err: any) {
      pushToast({
        kind: 'error',
        title: 'Registration Error',
        body: err?.detail || err?.message || 'Could not create account',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = () => {
    tap();
    logout();
  };

  const handleSaveConnectionSettings = (e: React.FormEvent) => {
    e.preventDefault();
    tap();
    setApiBaseUrl(customApiUrl);
    setDeviceId(customDeviceId);
    pushToast({
      kind: 'success',
      title: 'Settings Saved',
      body: 'Connection parameters updated. Reconnecting...',
    });
    setShowSettings(false);
  };

  return (
    <div className="min-h-screen bg-ink-950 text-ink-200 flex flex-col justify-between p-4 sm:p-6 font-sans antialiased selection:bg-accent/30 selection:text-accent">
      {/* ------------------------------------------------------------------- */}
      {/* Header with Navigation */}
      <header className="max-w-4xl w-full mx-auto flex items-center justify-between pb-4">
        {currentUser ? (
          <Link
            to="/app"
            className="flex items-center gap-2 text-xs font-semibold text-accent hover:text-accent/80 transition-colors"
          >
            <span>← Back to Dashboard</span>
          </Link>
        ) : (
          <Link
            to="/"
            className="flex items-center gap-2 text-xs font-semibold text-ink-400 hover:text-accent transition-colors"
          >
            <span>← Back to Home</span>
          </Link>
        )}

        <div className="flex items-center gap-2">
          <span className="size-2 rounded-full bg-accent animate-pulse" />
          <span className="text-xs font-mono text-ink-400">Backend: {status}</span>
        </div>
      </header>

      {/* ------------------------------------------------------------------- */}
      {/* Main Authentication Card */}
      {/* ------------------------------------------------------------------- */}
      <main className="max-w-md w-full mx-auto my-auto py-2">
        {/* Protected Route Alert if user was redirected from a locked URL */}
        {attemptedFrom && !currentUser && (
          <div className="mb-4 p-3.5 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-300 flex items-center gap-3 text-xs shadow-md">
            <span className="p-1 rounded-lg bg-amber-500/20 text-amber-400 shrink-0">
              <IconLock className="size-4" />
            </span>
            <div>
              <p className="font-bold">Authentication Required</p>
              <p className="text-ink-300 text-[11px] mt-0.5">
                Dashboard access to <code className="font-mono text-amber-300 font-bold">{attemptedFrom}</code> is restricted. Please sign in or create an account to proceed.
              </p>
            </div>
          </div>
        )}

        {/* Active User Banner if already signed in */}
        {currentUser && (
          <div className="mb-6 p-4 rounded-2xl bg-accent/10 border border-accent/30 shadow-[var(--shadow-neo)] flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-2xl">{currentUser.avatar || '⚡'}</span>
              <div className="min-w-0">
                <p className="text-xs text-accent font-bold uppercase tracking-wider flex items-center gap-1">
                  <span>● Authenticated Session</span>
                </p>
                <h4 className="text-sm font-bold text-ink-100 truncate">{currentUser.display_name}</h4>
                <p className="text-[11px] text-ink-400 font-mono">
                  @{currentUser.username} • Code: <strong className="text-amber-400">{currentUser.competition_code}</strong>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button size="sm" variant="outline" onClick={handleLogout} title="Sign Out">
                <IconLogout className="size-3.5" />
                <span className="hidden sm:inline">Sign Out</span>
              </Button>
              <Button size="sm" variant="primary" onClick={() => navigate(targetDestination)}>
                Dashboard →
              </Button>
            </div>
          </div>
        )}

        <div className="rounded-3xl p-6 sm:p-8 bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)]">
          {/* Brand Logo & Heading */}
          <div className="text-center mb-6">
            <div className="size-12 rounded-2xl bg-accent/15 border border-accent/30 flex items-center justify-center text-accent mx-auto mb-3 shadow-[var(--shadow-neo-glow)]">
              <IconChip className="size-7" />
            </div>
            <h2 className="text-2xl font-black text-ink-100 tracking-tight flex items-center justify-center gap-2">
              <span>AI DeskMate Portal</span>
              <IconLock className="size-5 text-accent" />
            </h2>
            <p className="text-xs text-ink-400 mt-1">
              Secure authentication required to access device controls and productivity tools.
            </p>
          </div>

          {/* Tab Selector */}
          <div className="flex rounded-xl bg-ink-950 p-1 border border-ink-800/80 mb-6 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setActiveTab('login')}
              className={cx(
                'flex-1 py-2 rounded-lg transition-all text-center',
                activeTab === 'login'
                  ? 'bg-ink-850 text-accent font-bold shadow-sm'
                  : 'text-ink-400 hover:text-ink-200',
              )}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('register')}
              className={cx(
                'flex-1 py-2 rounded-lg transition-all text-center',
                activeTab === 'register'
                  ? 'bg-ink-850 text-accent font-bold shadow-sm'
                  : 'text-ink-400 hover:text-ink-200',
              )}
            >
              + Create Account
            </button>
          </div>

          {/* ------------------------------------------------------------- */}
          {/* TAB 1: Log In Form */}
          {/* ------------------------------------------------------------- */}
          {activeTab === 'login' && (
            <form onSubmit={handleLogin} className="flex flex-col gap-3.5">
              <div>
                <label className="block text-xs font-medium text-ink-300 mb-1.5">
                  Username <span className="text-accent">*</span>
                </label>
                <Input
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                  placeholder="Enter your registered username"
                  required
                  autoFocus
                  className="h-10 text-sm font-mono"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-medium text-ink-300">
                    Password <span className="text-accent">*</span>
                  </label>
                </div>
                <div className="relative">
                  <Input
                    type={showLoginPassword ? 'text' : 'password'}
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="Enter account password"
                    required
                    className="h-10 text-sm pr-10 font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowLoginPassword(!showLoginPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-200 p-1"
                    title={showLoginPassword ? 'Hide password' : 'Show password'}
                  >
                    {showLoginPassword ? <IconEyeOff className="size-4" /> : <IconEye className="size-4" />}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="lg"
                disabled={submitting || !loginUsername.trim()}
                className="w-full font-bold mt-2"
              >
                {submitting ? 'Authenticating...' : 'Sign In & Access Dashboard →'}
              </Button>
            </form>
          )}

          {/* ------------------------------------------------------------- */}
          {/* TAB 2: Register Form */}
          {/* ------------------------------------------------------------- */}
          {activeTab === 'register' && (
            <form onSubmit={handleRegister} className="flex flex-col gap-3">
              <div>
                <label className="block text-xs font-medium text-ink-300 mb-1">
                  Choose Username <span className="text-accent">*</span>
                </label>
                <Input
                  value={regUsername}
                  onChange={(e) => setRegUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_\-]/g, ''))}
                  placeholder="e.g. jordan"
                  required
                  className="h-9 text-xs font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-ink-300 mb-1">Display Name</label>
                <Input
                  value={regDisplayName}
                  onChange={(e) => setRegDisplayName(e.target.value)}
                  placeholder="e.g. Jordan Hayes"
                  className="h-9 text-xs"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs font-medium text-ink-300 mb-1">Password</label>
                  <div className="relative">
                    <Input
                      type={showRegPassword ? 'text' : 'password'}
                      value={regPassword}
                      onChange={(e) => setRegPassword(e.target.value)}
                      placeholder="Min 4 chars"
                      className="h-9 text-xs pr-8 font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowRegPassword(!showRegPassword)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-200"
                    >
                      {showRegPassword ? <IconEyeOff className="size-3.5" /> : <IconEye className="size-3.5" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-ink-300 mb-1">Confirm Password</label>
                  <Input
                    type={showRegPassword ? 'text' : 'password'}
                    value={regConfirmPassword}
                    onChange={(e) => setRegConfirmPassword(e.target.value)}
                    placeholder="Repeat password"
                    className="h-9 text-xs font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-ink-300 mb-1">Select Avatar</label>
                <div className="flex flex-wrap gap-2">
                  {AVATAR_OPTIONS.map((av) => (
                    <button
                      key={av}
                      type="button"
                      onClick={() => setRegAvatar(av)}
                      className={cx(
                        'size-8 rounded-xl border flex items-center justify-center text-base transition-all',
                        regAvatar === av
                          ? 'border-accent bg-accent/20 scale-105 shadow-sm'
                          : 'border-ink-800 bg-ink-950 hover:border-ink-700',
                      )}
                    >
                      {av}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-ink-300 mb-1">
                  Device ID (Optional)
                </label>
                <Input
                  value={regDeviceId}
                  onChange={(e) => setRegDeviceId(e.target.value)}
                  placeholder={`dev-${regUsername || 'student'}`}
                  className="h-8 text-xs font-mono"
                />
              </div>

              {/* Code Preview Box */}
              <div className="p-2.5 rounded-xl bg-ink-950 border border-amber-500/30 flex items-center justify-between">
                <div>
                  <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider block">
                    Unique Competition Code
                  </span>
                  <span className="text-[10px] text-ink-400">Classmates enter this to challenge you</span>
                </div>
                <span className="font-mono text-xs font-extrabold text-amber-300 bg-ink-900 px-2 py-0.5 rounded border border-ink-800">
                  {regUsername ? `${regUsername.slice(0, 4).toUpperCase()}-XXXX` : 'CODE-XXXX'}
                </span>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="md"
                disabled={submitting || !regUsername.trim()}
                className="w-full font-bold mt-1"
              >
                {submitting ? 'Registering...' : '✨ Create Account & Authenticate'}
              </Button>
            </form>
          )}

          {/* Connection settings toggle */}
          <div className="mt-6 pt-4 border-t border-ink-800/80">
            <button
              type="button"
              onClick={() => setShowSettings(!showSettings)}
              className="text-[11px] text-ink-400 hover:text-ink-200 flex items-center gap-1.5 mx-auto"
            >
              <IconGear className="size-3.5" />
              <span>{showSettings ? 'Hide Backend Connection' : 'Advanced Connection Settings (LAN / IP)'}</span>
            </button>

            {showSettings && (
              <form onSubmit={handleSaveConnectionSettings} className="mt-3 p-3.5 rounded-xl bg-ink-950 border border-ink-800 flex flex-col gap-2.5">
                <div>
                  <label className="block text-[11px] text-ink-400 mb-1">Backend Base URL</label>
                  <Input
                    value={customApiUrl}
                    onChange={(e) => setCustomApiUrl(e.target.value)}
                    placeholder="http://192.168.1.50:8000"
                    className="h-8 text-xs font-mono"
                  />
                  <span className="text-[10px] text-ink-400 mt-0.5 block">
                    Leave blank for same-origin dev proxy. Use local IP for phone.
                  </span>
                </div>

                <div>
                  <label className="block text-[11px] text-ink-400 mb-1">Target Device ID</label>
                  <Input
                    value={customDeviceId}
                    onChange={(e) => setCustomDeviceId(e.target.value)}
                    placeholder="deskmate-01"
                    className="h-8 text-xs font-mono"
                  />
                </div>

                <Button type="submit" variant="outline" size="sm" className="mt-1">
                  Save Connection Settings
                </Button>
              </form>
            )}
          </div>
        </div>
      </main>

      {/* ------------------------------------------------------------------- */}
      {/* Footer */}
      {/* ------------------------------------------------------------------- */}
      <footer className="max-w-4xl w-full mx-auto text-center pt-4 text-[11px] text-ink-400">
        <p>AI DeskMate • ESP32-S3 Physical Assistant & Secure Access</p>
      </footer>
    </div>
  );
}
