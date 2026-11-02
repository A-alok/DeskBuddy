/**
 * Layout.
 *
 * One component serves both targets: a sidebar on desktop, a five-tab bottom bar
 * plus a "More" sheet on phones. Capacitor ships the same bundle, so the mobile
 * layout is a breakpoint, not a separate build.
 */

import { useEffect, useState } from 'react';
import type { ComponentType, SVGProps } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useDeskmate } from '@/store/useDeskmate';
import { tap } from '@/lib/native';
import { StatusStrip } from './StatusStrip';
import { Toasts } from './Toasts';
import { cx } from './ui';
import {
  IconAlarm,
  IconBell,
  IconBook,
  IconChart,
  IconChat,
  IconChip,
  IconFocus,
  IconGear,
  IconHome,
  IconLogout,
  IconMore,
  IconStopwatch,
  IconTasks,
  IconTimer,
  IconTrophy,
} from './icons';

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

interface NavItem {
  to: string;
  label: string;
  short: string;
  icon: Icon;
  primary?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/app', label: 'Overview', short: 'Home', icon: IconHome, primary: true },
  { to: '/competitive', label: 'Competitive', short: 'Compete', icon: IconTrophy, primary: true },
  { to: '/timer', label: 'Timer', short: 'Timer', icon: IconTimer, primary: true },
  { to: '/stopwatch', label: 'Stopwatch', short: 'Stopwatch', icon: IconStopwatch },
  { to: '/alarms', label: 'Alarms', short: 'Alarms', icon: IconAlarm },
  { to: '/pomodoro', label: 'Pomodoro', short: 'Focus', icon: IconFocus, primary: true },
  { to: '/tasks', label: 'Tasks', short: 'Tasks', icon: IconTasks, primary: true },
  { to: '/reminders', label: 'Reminders', short: 'Reminders', icon: IconBell },
  { to: '/chat', label: 'AI Chat', short: 'Chat', icon: IconChat, primary: true },
  { to: '/study', label: 'Study Notes', short: 'Study', icon: IconBook },
  { to: '/analytics', label: 'Analytics', short: 'Analytics', icon: IconChart },
  { to: '/device', label: 'Device', short: 'Device', icon: IconChip },
  { to: '/settings', label: 'Settings', short: 'Settings', icon: IconGear },
];

const PRIMARY = NAV_ITEMS.filter((item) => item.primary);
const SECONDARY = NAV_ITEMS.filter((item) => !item.primary);

export function AppShell({ children }: { children?: React.ReactNode }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const location = useLocation();
  const currentUser = useDeskmate((state) => state.currentUser);

  // Close the sheet on navigation, and scroll each page to the top.
  useEffect(() => {
    setMoreOpen(false);
    window.scrollTo({ top: 0 });
  }, [location.pathname]);

  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMoreOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [moreOpen]);

  const secondaryActive = SECONDARY.some((item) => item.to === location.pathname);

  return (
    <div className="min-h-dvh bg-ink-950">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-ink-950"
      >
        Skip to content
      </a>

      <div className="flex min-h-dvh w-full">
        {/* ---------------------------------------------------- desktop nav */}
        <aside className="safe-top sticky top-0 hidden h-dvh w-64 shrink-0 flex-col border-r border-ink-800/60 px-4 pt-5 pb-6 lg:flex">
          <div className="flex h-12 items-center">
            <Brand />
          </div>
          <nav aria-label="Main" className="mt-6 flex flex-1 flex-col gap-1.5 overflow-y-auto px-2 -mx-2">
            {NAV_ITEMS.map((item) => (
              <SideLink key={item.to} item={item} />
            ))}
          </nav>
          <SyncFooter />
        </aside>

        {/* --------------------------------------------------------- content */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="safe-top sticky top-0 z-30 bg-ink-950/80 backdrop-blur-md border-b border-ink-800/40 px-4 pt-5 pb-4 lg:px-6">
            <div className="flex h-12 items-center gap-3">
              <div className="lg:hidden">
                <Brand compact />
              </div>
              <div className="min-w-0 flex-1">
                <StatusStrip />
              </div>
            </div>
          </header>

          <main id="main" className="flex-1 px-4 py-6 pb-28 lg:px-6 lg:pb-8">
            {children ?? <Outlet />}
          </main>
        </div>
      </div>

      {/* ------------------------------------------------------- mobile nav */}
      <nav
        aria-label="Main"
        className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-ink-800 bg-ink-900/95 backdrop-blur lg:hidden"
      >
        <ul className="flex items-stretch">
          {PRIMARY.map((item) => (
            <li key={item.to} className="flex-1">
              <TabLink item={item} />
            </li>
          ))}
          <li className="flex-1">
            <button
              type="button"
              aria-expanded={moreOpen}
              aria-haspopup="menu"
              onClick={() => {
                tap();
                setMoreOpen((open) => !open);
              }}
              className={cx(
                'flex w-full flex-col items-center gap-1 py-2.5 text-[10px] transition-colors',
                moreOpen || secondaryActive ? 'text-accent' : 'text-ink-400',
              )}
            >
              <IconMore className="size-5" />
              More
            </button>
          </li>
        </ul>
      </nav>

      {moreOpen && (
        <>
          <button
            type="button"
            aria-label="Close menu"
            onClick={() => setMoreOpen(false)}
            className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          />
          <div
            role="menu"
            aria-label="More pages"
            className="safe-bottom fixed inset-x-0 bottom-[68px] z-50 mx-3 rounded-2xl border border-ink-700 bg-ink-900 p-2 shadow-2xl lg:hidden"
          >
            <ul className="grid grid-cols-3 gap-1">
              {SECONDARY.map((item) => (
                <li key={item.to}>
                  <SheetLink item={item} />
                </li>
              ))}
            </ul>

            {currentUser && (
              <div className="mt-3 pt-2.5 border-t border-ink-800 flex items-center justify-between px-2 text-xs">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-base">{currentUser.avatar || '⚡'}</span>
                  <span className="font-semibold text-ink-200 truncate">{currentUser.display_name}</span>
                </div>
                <Link
                  to="/logout"
                  onClick={() => setMoreOpen(false)}
                  className="flex items-center gap-1.5 text-danger font-semibold text-xs px-2.5 py-1.5 rounded-lg bg-danger/10 hover:bg-danger/20 transition-colors"
                >
                  <IconLogout className="size-3.5" />
                  <span>Log Out</span>
                </Link>
              </div>
            )}
          </div>
        </>
      )}

      <Toasts />
    </div>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/app" className="flex items-center gap-2.5 group hover:opacity-90 transition-opacity">
      <span
        aria-hidden
        className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent/15 text-accent shadow-[var(--shadow-neo-sm)]"
      >
        <IconChip className="size-5" />
      </span>
      <div className={compact ? 'sr-only' : ''}>
        <p className="text-sm leading-tight font-semibold text-ink-100 flex items-center gap-1.5">
          AI DeskMate
          <span className="text-[9px] font-mono font-bold bg-accent/20 text-accent px-1.5 py-0.2 rounded">v0.1</span>
        </p>
        <p className="text-[11px] leading-tight text-ink-400">ESP32-S3 assistant</p>
      </div>
    </Link>
  );
}

function SideLink({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.to === '/app'}
      className={({ isActive }) =>
        cx(
          'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-300',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
          isActive
            ? 'bg-ink-950 font-medium text-accent shadow-[var(--shadow-neo-pressed)] border border-ink-900 shadow-[inset_0_0_15px_rgba(59,130,246,0.1)]'
            : 'text-ink-400 hover:bg-ink-900 hover:text-ink-200 hover:shadow-[var(--shadow-neo-sm)] hover:border hover:border-ink-850 border border-transparent',
        )
      }
    >
      <Icon className={cx("size-5 shrink-0 transition-transform duration-300")} />
      {item.label}
    </NavLink>
  );
}

function TabLink({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.to === '/app'}
      onClick={() => tap()}
      className={({ isActive }) =>
        cx(
          'flex flex-col items-center gap-1 py-2.5 text-[10px] transition-colors',
          isActive ? 'text-accent' : 'text-ink-400',
        )
      }
    >
      <Icon className="size-5" />
      {item.short}
    </NavLink>
  );
}

function SheetLink({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      role="menuitem"
      onClick={() => tap()}
      className={({ isActive }) =>
        cx(
          'flex flex-col items-center gap-1.5 rounded-xl px-2 py-3 text-[11px]',
          isActive ? 'bg-accent/10 text-accent' : 'text-ink-300 hover:bg-ink-850',
        )
      }
    >
      <Icon className="size-5" />
      {item.short}
    </NavLink>
  );
}

function SyncFooter() {
  const navigate = useNavigate();
  const status = useDeskmate((state) => state.status);
  const lastSyncAt = useDeskmate((state) => state.lastSyncAt);
  const aiProvider = useDeskmate((state) => state.aiProvider);
  const databaseStatus = useDeskmate((state) => state.databaseStatus);
  const currentUser = useDeskmate((state) => state.currentUser);
  const logout = useDeskmate((state) => state.logout);
  const pushToast = useDeskmate((state) => state.pushToast);

  const handleLogout = () => {
    tap();
    logout();
    pushToast({
      kind: 'info',
      title: 'Signed Out',
      body: 'You have been safely signed out.',
    });
    navigate('/login', { replace: true });
  };

  return (
    <div className="mt-4 border-t border-ink-800 pt-3 text-[11px] text-ink-400">
      <p>
        Socket: <span className="text-ink-300">{status}</span>
      </p>
      <p className="mt-0.5">
        Atlas:{' '}
        <span className={databaseStatus === 'down' ? 'text-danger' : 'text-ink-300'}>
          {databaseStatus ?? 'unknown'}
        </span>
      </p>
      <p className="mt-0.5 truncate">
        AI: <span className="text-ink-300">{aiProvider?.startsWith('groq') ? aiProvider : 'groq:openai/gpt-oss-20b'}</span>
      </p>
      {lastSyncAt && (
        <p className="mt-0.5">
          Synced {new Date(lastSyncAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
        </p>
      )}

      {currentUser && (
        <div className="mt-3 pt-2.5 border-t border-ink-800/80">
          <div className="flex items-center justify-between gap-2 p-2 rounded-xl bg-ink-900 border border-ink-800/60 shadow-[var(--shadow-neo-sm)]">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-lg shrink-0">{currentUser.avatar || '⚡'}</span>
              <div className="min-w-0 leading-tight">
                <p className="text-xs font-bold text-ink-100 truncate">{currentUser.display_name}</p>
                <p className="text-[10px] text-ink-400 font-mono truncate">@{currentUser.username}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              title="Sign Out"
              className="p-1.5 rounded-lg text-ink-400 hover:text-danger hover:bg-danger/10 border border-transparent hover:border-danger/20 transition-all shrink-0 cursor-pointer"
            >
              <IconLogout className="size-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
