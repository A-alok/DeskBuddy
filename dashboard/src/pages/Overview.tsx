import { Link } from 'react-router-dom';
import { FocusBarChart } from '@/components/BarChart';
import { OledPreview } from '@/components/OledPreview';
import { RingProgress } from '@/components/RingProgress';
import { IconPause, IconPlay, IconStop } from '@/components/icons';
import { Badge, Button, Card, EmptyState, PageHeader, Stat } from '@/components/ui';
import { useCountdown, useWallClock } from '@/hooks/useTicker';
import { api } from '@/lib/api';
import { intentLabel, screenLabel, useLightLabel } from '@/lib/device';
import { formatClock, formatMinutes, formatRelative, formatTimeOfDay } from '@/lib/format';
import { useDeskmate } from '@/store/useDeskmate';

export function Overview() {
  const device = useDeskmate((state) => state.device);
  const timer = useDeskmate((state) => state.timer);
  const pomodoro = useDeskmate((state) => state.pomodoro);
  const analytics = useDeskmate((state) => state.analytics);
  const tasks = useDeskmate((state) => state.tasks);
  const reminders = useDeskmate((state) => state.reminders);
  const alarms = useDeskmate((state) => state.alarms);
  const commands = useDeskmate((state) => state.commands);
  const run = useDeskmate((state) => state.run);
  const lightLabel = useLightLabel();

  const clock = useWallClock();
  const timerRemaining = useCountdown(timer?.ends_at, timer?.remaining_seconds ?? 0, timer?.state === 'running');
  const pomodoroRemaining = useCountdown(
    pomodoro?.ends_at,
    pomodoro?.remaining_seconds ?? 0,
    pomodoro?.state === 'running',
  );

  const openTasks = tasks.filter((task) => !task.done);
  const nextReminder = reminders.find((reminder) => !reminder.done);
  const nextAlarm = alarms
    .filter((alarm) => alarm.enabled && alarm.next_trigger_at)
    .sort((a, b) => Date.parse(a.next_trigger_at!) - Date.parse(b.next_trigger_at!))[0];

  const timerProgress = timer && timer.duration_seconds > 0 ? 1 - timerRemaining / timer.duration_seconds : 0;
  const pomodoroProgress =
    pomodoro && pomodoro.phase_total_seconds > 0 ? 1 - pomodoroRemaining / pomodoro.phase_total_seconds : 0;

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle={clock.toLocaleString(undefined, {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          hour: '2-digit',
          minute: '2-digit',
        })}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        {/* -------------------------------------------------- OLED mirror */}
        <Card
          title="Device screen"
          subtitle="Live mirror of the 128×64 OLED"
          actions={<Badge tone={device?.online ? 'good' : 'bad'}>{device?.online ? 'live' : 'offline'}</Badge>}
        >
          <OledPreview />
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <div>
              <dt className="text-ink-400">Screen</dt>
              <dd className="text-ink-200">{screenLabel(device?.current_screen)}</dd>
            </div>
            <div>
              <dt className="text-ink-400">Firmware</dt>
              <dd className="text-ink-200">{device?.firmware_version ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-ink-400">{lightLabel}</dt>
              <dd className={device?.relay_on ? 'text-accent' : 'text-ink-200'}>
                {device?.relay_on ? 'On' : 'Off'}
              </dd>
            </div>
            <div>
              <dt className="text-ink-400">Last seen</dt>
              <dd className="text-ink-200">{formatRelative(device?.last_seen_at)}</dd>
            </div>
          </dl>
        </Card>

        {/* ------------------------------------------------------- timer */}
        <Card
          title="Timer"
          subtitle={timer ? timer.label : 'Nothing running'}
          actions={
            <Link
              to="/timer"
              className="text-xs text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent"
            >
              Open
            </Link>
          }
        >
          {timer ? (
            <div className="flex flex-col items-center gap-4">
              <RingProgress value={timerProgress} size={168} label={`Timer ${formatClock(timerRemaining)} remaining`}>
                <div>
                  <p className="tabular text-2xl font-semibold text-ink-100">{formatClock(timerRemaining)}</p>
                  <p className="mt-1 text-[11px] tracking-wide text-ink-400 uppercase">{timer.state}</p>
                </div>
              </RingProgress>
              <div className="flex gap-2">
                {timer.state === 'running' ? (
                  <Button size="sm" onClick={() => void run('Pause timer', () => api.timer.pause())}>
                    <IconPause className="size-4" /> Pause
                  </Button>
                ) : (
                  <Button size="sm" variant="primary" onClick={() => void run('Resume timer', () => api.timer.resume())}>
                    <IconPlay className="size-4" /> Resume
                  </Button>
                )}
                <Button size="sm" variant="danger" onClick={() => void run('Cancel timer', () => api.timer.stop())}>
                  <IconStop className="size-4" /> Cancel
                </Button>
              </div>
            </div>
          ) : (
            <EmptyState
              title="No timer running"
              body="Start one here, from the device, or by saying “set a timer for 10 minutes” or “10 minute ka timer lagao”."
              action={
                <div className="mt-2 flex gap-2">
                  {[5, 15, 25].map((minutes) => (
                    <Button
                      key={minutes}
                      size="sm"
                      onClick={() => void run('Start timer', () => api.timer.start({ minutes }))}
                    >
                      {minutes}m
                    </Button>
                  ))}
                </div>
              }
            />
          )}
        </Card>

        {/* ---------------------------------------------------- pomodoro */}
        <Card
          title="Pomodoro"
          subtitle={
            pomodoro && pomodoro.phase !== 'idle'
              ? `${pomodoro.phase.replace('_', ' ')} · cycle ${pomodoro.completed_focus_cycles + 1}`
              : 'Idle'
          }
          actions={
            <Link
              to="/pomodoro"
              className="text-xs text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent"
            >
              Open
            </Link>
          }
        >
          {pomodoro && pomodoro.state !== 'idle' ? (
            <div className="flex flex-col items-center gap-4">
              <RingProgress
                value={pomodoroProgress}
                size={168}
                tone={pomodoro.phase === 'focus' ? 'focus' : 'break'}
                label={`Pomodoro ${formatClock(pomodoroRemaining)} remaining`}
              >
                <div>
                  <p className="tabular text-2xl font-semibold text-ink-100">{formatClock(pomodoroRemaining)}</p>
                  <p className="mt-1 text-[11px] tracking-wide text-ink-400 uppercase">
                    {pomodoro.phase.replace('_', ' ')}
                  </p>
                </div>
              </RingProgress>
              <div className="flex gap-2">
                {pomodoro.state === 'running' ? (
                  <Button size="sm" onClick={() => void run('Pause Pomodoro', () => api.pomodoro.pause())}>
                    <IconPause className="size-4" /> Pause
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => void run('Resume Pomodoro', () => api.pomodoro.resume())}
                  >
                    <IconPlay className="size-4" /> Resume
                  </Button>
                )}
                <Button size="sm" variant="danger" onClick={() => void run('Stop Pomodoro', () => api.pomodoro.stop())}>
                  <IconStop className="size-4" /> Stop
                </Button>
              </div>
            </div>
          ) : (
            <EmptyState
              title="No focus session"
              body={`Default block is ${pomodoro?.focus_minutes ?? 25} minutes.`}
              action={
                <Button
                  className="mt-2"
                  size="sm"
                  variant="primary"
                  onClick={() => void run('Start Pomodoro', () => api.pomodoro.start())}
                >
                  <IconPlay className="size-4" /> Start focus
                </Button>
              }
            />
          )}
        </Card>
      </div>

      {/* ------------------------------------------------------------ stats */}
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          label="Focus today"
          value={formatMinutes(analytics?.focus_minutes_today ?? 0)}
          sub={`${analytics?.sessions_today ?? 0} sessions`}
          tone="accent"
        />
        <Stat
          label="Cycles"
          value={analytics?.pomodoro_cycles_today ?? 0}
          sub="completed today"
          tone="focus"
        />
        <Stat label="Open tasks" value={openTasks.length} sub={`${analytics?.tasks_completed_today ?? 0} done today`} />
        <Stat
          label="Streak"
          value={`${analytics?.current_streak_days ?? 0}d`}
          sub="consecutive focus days"
          tone="break"
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {/* ------------------------------------------------------ up next */}
        <Card title="Up next">
          <ul className="flex flex-col divide-y divide-ink-800 text-sm">
            <li className="flex items-center justify-between gap-3 py-2.5">
              <span className="text-ink-400">Next alarm</span>
              <span className="text-right text-ink-200">
                {nextAlarm ? (
                  <>
                    {nextAlarm.time_of_day}
                    <span className="ml-2 text-xs text-ink-400">{formatRelative(nextAlarm.next_trigger_at)}</span>
                  </>
                ) : (
                  '—'
                )}
              </span>
            </li>
            <li className="flex items-center justify-between gap-3 py-2.5">
              <span className="text-ink-400">Next reminder</span>
              <span className="min-w-0 text-right text-ink-200">
                {nextReminder ? (
                  <>
                    <span className="block truncate">{nextReminder.text}</span>
                    <span className="text-xs text-ink-400">
                      {formatTimeOfDay(nextReminder.remind_at)} · {formatRelative(nextReminder.remind_at)}
                    </span>
                  </>
                ) : (
                  '—'
                )}
              </span>
            </li>
            <li className="flex items-center justify-between gap-3 py-2.5">
              <span className="text-ink-400">Top task</span>
              <span className="min-w-0 text-right">
                {openTasks[0] ? (
                  <>
                    <span className="block truncate text-ink-200">{openTasks[0].title}</span>
                    <span className="text-xs text-ink-400">{openTasks[0].priority} priority</span>
                  </>
                ) : (
                  <span className="text-ink-200">—</span>
                )}
              </span>
            </li>
          </ul>
        </Card>

        {/* ------------------------------------------------ recent commands */}
        <Card title="Recent commands" subtitle="Voice, touch and dashboard">
          {commands.length === 0 ? (
            <EmptyState title="Nothing yet" body="Commands from any surface show up here." />
          ) : (
            <ul className="flex flex-col gap-2.5">
              {commands.slice(0, 5).map((command) => (
                <li key={command.id} className="text-sm">
                  <div className="flex items-start justify-between gap-2">
                    <p dir="auto" className="min-w-0 flex-1 truncate py-0.5 text-ink-200">
                      “{command.transcript}”
                    </p>
                    <Badge tone={command.handled_locally ? 'good' : 'info'}>
                      {command.handled_locally ? intentLabel(command.intent) : 'ai'}
                    </Badge>
                  </div>
                  {command.response_text && (
                    <p className="mt-0.5 truncate text-xs text-ink-400">{command.response_text}</p>
                  )}
                  <p className="mt-0.5 text-[11px] text-ink-400">
                    {command.source} · {formatRelative(command.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* ----------------------------------------------------- focus week */}
        <Card
          title="Focus this week"
          subtitle={`${formatMinutes(analytics?.focus_minutes_total ?? 0)} all time`}
          actions={
            <Link
              to="/analytics"
              className="text-xs text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent"
            >
              Details
            </Link>
          }
        >
          {analytics ? <FocusBarChart data={analytics.daily} /> : <EmptyState title="No data yet" />}
        </Card>
      </div>
    </>
  );
}
