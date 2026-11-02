import { useState } from 'react';
import { RingProgress } from '@/components/RingProgress';
import { IconPause, IconPlay, IconStop } from '@/components/icons';
import { Badge, Button, Card, EmptyState, Field, Input, PageHeader } from '@/components/ui';
import { useCountdown } from '@/hooks/useTicker';
import { api } from '@/lib/api';
import { formatClock, formatDateTime, formatDuration } from '@/lib/format';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';

const PRESETS = [
  { label: '1 min', minutes: 1 },
  { label: '5 min', minutes: 5 },
  { label: '10 min', minutes: 10 },
  { label: '15 min', minutes: 15 },
  { label: '25 min', minutes: 25 },
  { label: '45 min', minutes: 45 },
];

export function TimerPage() {
  const timer = useDeskmate((state) => state.timer);
  const history = useDeskmate((state) => state.timers);
  const run = useDeskmate((state) => state.run);

  const [label, setLabel] = useState('');
  const [hours, setHours] = useState(0);
  const [minutes, setMinutes] = useState(10);
  const [seconds, setSeconds] = useState(0);

  const remaining = useCountdown(timer?.ends_at, timer?.remaining_seconds ?? 0, timer?.state === 'running');
  const progress = timer && timer.duration_seconds > 0 ? 1 - remaining / timer.duration_seconds : 0;
  const customTotal = hours * 3600 + minutes * 60 + seconds;

  const start = (input: { hours?: number; minutes?: number; seconds?: number; label?: string }) => {
    tap();
    void run('Start timer', () => api.timer.start(input));
  };

  return (
    <>
      <PageHeader
        title="Timer"
        subtitle="Runs on the device. Both surfaces count down from the same end timestamp."
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          {timer ? (
            <div className="flex flex-col items-center gap-5 py-2">
              <RingProgress
                value={progress}
                size={236}
                thickness={12}
                tone={remaining <= 10 && timer.state === 'running' ? 'danger' : 'accent'}
                label={`${formatClock(remaining)} remaining`}
              >
                <div>
                  <p className="tabular text-4xl font-semibold text-ink-100">{formatClock(remaining)}</p>
                  <p className="mt-1 text-xs text-ink-400">{timer.label}</p>
                  <Badge tone={timer.state === 'running' ? 'good' : 'warn'} className="mt-2">
                    {timer.state}
                  </Badge>
                </div>
              </RingProgress>

              <div className="flex flex-wrap items-center justify-center gap-2">
                {timer.state === 'running' ? (
                  <Button onClick={() => void run('Pause timer', () => api.timer.pause())}>
                    <IconPause className="size-4" /> Pause
                  </Button>
                ) : (
                  <Button variant="primary" onClick={() => void run('Resume timer', () => api.timer.resume())}>
                    <IconPlay className="size-4" /> Resume
                  </Button>
                )}
                <Button variant="outline" onClick={() => void run('Extend timer', () => api.timer.extend(60))}>
                  +1 min
                </Button>
                <Button variant="outline" onClick={() => void run('Shorten timer', () => api.timer.extend(-60))}>
                  −1 min
                </Button>
                <Button variant="danger" onClick={() => void run('Cancel timer', () => api.timer.stop())}>
                  <IconStop className="size-4" /> Cancel
                </Button>
              </div>

              <p className="text-xs text-ink-400">
                Started {formatDateTime(timer.started_at)} · total {formatDuration(timer.duration_seconds)}
              </p>
            </div>
          ) : (
            <div className="py-6">
              <EmptyState
                title="No timer running"
                body="Pick a preset or set a custom duration. Starting it here also starts it on the device."
              />
            </div>
          )}
        </Card>

        <div className="flex flex-col gap-4">
          <Card title="Presets">
            <div className="grid grid-cols-3 gap-2">
              {PRESETS.map((preset) => (
                <Button
                  key={preset.label}
                  variant="outline"
                  onClick={() => start({ minutes: preset.minutes, label: `${preset.minutes} min` })}
                >
                  {preset.label}
                </Button>
              ))}
            </div>
          </Card>

          <Card title="Custom timer">
            <form
              className="flex flex-col gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                if (customTotal < 1) return;
                start({ hours, minutes, seconds, label: label.trim() || undefined });
              }}
            >
              <Field label="Label" htmlFor="timer-label" hint="Optional — shown on the OLED and the dashboard.">
                <Input
                  id="timer-label"
                  value={label}
                  maxLength={64}
                  placeholder="Deep work"
                  onChange={(event) => setLabel(event.target.value)}
                />
              </Field>

              <div className="grid grid-cols-3 gap-3">
                <Field label="Hours" htmlFor="timer-h">
                  <Input
                    id="timer-h"
                    type="number"
                    min={0}
                    max={99}
                    value={hours}
                    onChange={(event) => setHours(clamp(event.target.value, 0, 99))}
                  />
                </Field>
                <Field label="Minutes" htmlFor="timer-m">
                  <Input
                    id="timer-m"
                    type="number"
                    min={0}
                    max={59}
                    value={minutes}
                    onChange={(event) => setMinutes(clamp(event.target.value, 0, 59))}
                  />
                </Field>
                <Field label="Seconds" htmlFor="timer-s">
                  <Input
                    id="timer-s"
                    type="number"
                    min={0}
                    max={59}
                    value={seconds}
                    onChange={(event) => setSeconds(clamp(event.target.value, 0, 59))}
                  />
                </Field>
              </div>

              <div className="flex items-center justify-between gap-3">
                <p className="tabular text-sm text-ink-400">
                  {customTotal > 0 ? formatClock(customTotal) : 'Set a duration'}
                </p>
                <Button type="submit" variant="primary" disabled={customTotal < 1}>
                  <IconPlay className="size-4" /> Start
                </Button>
              </div>
            </form>
          </Card>

          <Card title="History" subtitle="Most recent first">
            {history.length === 0 ? (
              <EmptyState title="No timers yet" />
            ) : (
              <ul className="flex flex-col divide-y divide-ink-800">
                {history.slice(0, 8).map((entry) => (
                  <li key={entry.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <div className="min-w-0">
                      <p className="truncate text-ink-200">{entry.label}</p>
                      <p className="text-[11px] text-ink-400">{formatDateTime(entry.created_at)}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="tabular text-xs text-ink-400">
                        {formatDuration(entry.duration_seconds)}
                      </span>
                      <Badge
                        tone={
                          entry.state === 'finished'
                            ? 'good'
                            : entry.state === 'cancelled'
                              ? 'neutral'
                              : entry.state === 'running'
                                ? 'info'
                                : 'warn'
                        }
                      >
                        {entry.state}
                      </Badge>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

function clamp(raw: string, min: number, max: number): number {
  const parsed = Number.parseInt(raw, 10);
  if (Number.isNaN(parsed)) return min;
  return Math.min(max, Math.max(min, parsed));
}
