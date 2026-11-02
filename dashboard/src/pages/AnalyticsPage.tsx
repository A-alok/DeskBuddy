import { useEffect, useState } from 'react';
import { FocusBarChart } from '@/components/BarChart';
import { Badge, Button, Card, EmptyState, PageHeader, Spinner, Stat, cx } from '@/components/ui';
import { api } from '@/lib/api';
import { formatDateTime, formatDuration, formatMinutes } from '@/lib/format';
import type { Analytics, FocusSession } from '@/lib/types';
import { useDeskmate } from '@/store/useDeskmate';

const RANGES = [7, 14, 30] as const;

export function AnalyticsPage() {
  const cached = useDeskmate((state) => state.analytics);
  const run = useDeskmate((state) => state.run);

  const [range, setRange] = useState<number>(7);
  const [analytics, setAnalytics] = useState<Analytics | null>(cached);
  const [sessions, setSessions] = useState<FocusSession[]>([]);
  const [loading, setLoading] = useState(false);

  // Keep showing the cached 7-day series until a wider range arrives.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    void Promise.all([api.analytics(range), api.pomodoro.sessions(60)])
      .then(([freshAnalytics, freshSessions]) => {
        if (cancelled) return;
        setAnalytics(freshAnalytics);
        setSessions(freshSessions);
      })
      .catch(() => {
        /* the store's error banner already covers connectivity problems */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [range]);

  const focusSessions = sessions.filter((session) => session.kind === 'pomodoro_focus');
  const completionRate =
    focusSessions.length > 0
      ? Math.round((focusSessions.filter((s) => s.completed).length / focusSessions.length) * 100)
      : null;

  return (
    <>
      <PageHeader
        title="Productivity analytics"
        subtitle="Aggregated from completed focus sessions and tasks."
        actions={
          <div className="flex items-center gap-2">
            {loading && <Spinner />}
            <div role="tablist" aria-label="Range" className="flex gap-1 rounded-xl bg-ink-900 p-1 shadow-[var(--shadow-neo-pressed)]">
              {RANGES.map((value) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={range === value}
                  onClick={() => setRange(value)}
                  className={cx(
                    'rounded-lg px-3 py-1.5 text-xs transition-all duration-300 font-medium',
                    'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent',
                    range === value 
                      ? 'bg-ink-850 text-accent shadow-[var(--shadow-neo-sm)]' 
                      : 'text-ink-400 hover:text-ink-200',
                  )}
                >
                  {value}d
                </button>
              ))}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                void run('Refresh analytics', async () => {
                  const fresh = await api.analytics(range);
                  setAnalytics(fresh);
                  return fresh;
                })
              }
            >
              Refresh
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          label="Focus today"
          value={formatMinutes(analytics?.focus_minutes_today ?? 0)}
          sub={`${analytics?.sessions_today ?? 0} sessions`}
          tone="accent"
        />
        <Stat
          label="Focus all time"
          value={formatMinutes(analytics?.focus_minutes_total ?? 0)}
          sub={`${analytics?.sessions_total ?? 0} sessions`}
          tone="focus"
        />
        <Stat
          label="Streak"
          value={`${analytics?.current_streak_days ?? 0}d`}
          sub="consecutive days with focus"
          tone="break"
        />
        <Stat
          label="Completion"
          value={completionRate === null ? '—' : `${completionRate}%`}
          sub="focus blocks finished"
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" title={`Focus minutes — last ${range} days`}>
          {analytics && analytics.daily.length > 0 ? (
            <FocusBarChart data={analytics.daily} />
          ) : (
            <EmptyState title="No sessions yet" body="Run a Pomodoro block and this fills in." />
          )}
        </Card>

        <Card title="Totals">
          <dl className="flex flex-col divide-y divide-ink-800 text-sm">
            {[
              ['Tasks open', analytics?.tasks_open ?? 0],
              ['Tasks completed today', analytics?.tasks_completed_today ?? 0],
              ['Tasks completed all time', analytics?.tasks_completed_total ?? 0],
              ['Pomodoro cycles today', analytics?.pomodoro_cycles_today ?? 0],
              ['Commands logged', analytics?.voice_commands_total ?? 0],
            ].map(([label, value]) => (
              <div key={String(label)} className="flex items-center justify-between gap-3 py-2.5">
                <dt className="text-ink-400">{label}</dt>
                <dd className="tabular text-ink-100">{value}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>

      <Card className="mt-4" title="Recent focus sessions" subtitle="Newest first">
        {focusSessions.length === 0 ? (
          <EmptyState title="No focus sessions recorded" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] tracking-wide text-ink-400 uppercase">
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Started
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Planned
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Actual
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Result
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {focusSessions.slice(0, 20).map((session) => (
                  <tr key={session.id}>
                    <td className="py-2 pr-3 text-ink-300">{formatDateTime(session.started_at)}</td>
                    <td className="tabular py-2 pr-3 text-ink-400">{formatDuration(session.planned_seconds)}</td>
                    <td className="tabular py-2 pr-3 text-ink-100">{formatDuration(session.actual_seconds)}</td>
                    <td className="py-2">
                      <Badge tone={session.completed ? 'good' : 'neutral'}>
                        {session.completed ? 'completed' : 'cut short'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
