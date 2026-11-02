import { useEffect, useState } from 'react';
import { RingProgress } from '@/components/RingProgress';
import { IconPause, IconPlay, IconRefresh, IconSkip, IconStop } from '@/components/icons';
import { Badge, Button, Card, Field, Input, PageHeader, Stat, cx } from '@/components/ui';
import { useCountdown } from '@/hooks/useTicker';
import { api } from '@/lib/api';
import { formatClock, formatMinutes } from '@/lib/format';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';

const PHASE_LABEL: Record<string, string> = {
  idle: 'Idle',
  focus: 'Focus',
  short_break: 'Short break',
  long_break: 'Long break',
};

export function PomodoroPage() {
  const pomodoro = useDeskmate((state) => state.pomodoro);
  const analytics = useDeskmate((state) => state.analytics);
  const run = useDeskmate((state) => state.run);

  const [focus, setFocus] = useState(25);
  const [shortBreak, setShortBreak] = useState(5);
  const [longBreak, setLongBreak] = useState(15);
  const [cycles, setCycles] = useState(4);
  const [dirty, setDirty] = useState(false);

  // Keep the form in step with the server until the user edits it.
  useEffect(() => {
    if (!pomodoro || dirty) return;
    setFocus(pomodoro.focus_minutes);
    setShortBreak(pomodoro.short_break_minutes);
    setLongBreak(pomodoro.long_break_minutes);
    setCycles(pomodoro.cycles_before_long_break);
  }, [pomodoro, dirty]);

  const running = pomodoro?.state === 'running';
  const paused = pomodoro?.state === 'paused';
  const idle = !pomodoro || pomodoro.state === 'idle';

  const remaining = useCountdown(pomodoro?.ends_at, pomodoro?.remaining_seconds ?? 0, running);
  const total = pomodoro?.phase_total_seconds ?? 0;
  const progress = total > 0 ? 1 - remaining / total : 0;
  const isFocus = pomodoro?.phase === 'focus';

  const act = (label: string, action: () => Promise<unknown>) => {
    tap();
    void run(label, action);
  };

  const cyclesDone = pomodoro?.completed_focus_cycles ?? 0;
  const perLong = pomodoro?.cycles_before_long_break ?? 4;
  const inCurrentSet = perLong > 0 ? cyclesDone % perLong : 0;

  return (
    <>
      <PageHeader title="Pomodoro" subtitle="Focus blocks with automatic breaks. Phase changes fire on the device too." />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card>
          <div className="flex flex-col items-center gap-5 py-2">
            <RingProgress
              value={progress}
              size={248}
              thickness={12}
              tone={idle ? 'accent' : isFocus ? 'focus' : 'break'}
              label={`${PHASE_LABEL[pomodoro?.phase ?? 'idle']} — ${formatClock(remaining)} remaining`}
            >
              <div>
                <p className="tabular text-4xl font-semibold text-ink-100">
                  {idle ? formatClock((pomodoro?.focus_minutes ?? 25) * 60) : formatClock(remaining)}
                </p>
                <p className="mt-1 text-xs tracking-wide text-ink-400 uppercase">
                  {PHASE_LABEL[pomodoro?.phase ?? 'idle']}
                </p>
                {!idle && (
                  <Badge tone={running ? 'good' : 'warn'} className="mt-2">
                    {pomodoro?.state}
                  </Badge>
                )}
              </div>
            </RingProgress>

            {/* cycle pips */}
            <div className="flex items-center gap-2" aria-label={`${inCurrentSet} of ${perLong} blocks before a long break`}>
              {Array.from({ length: perLong }).map((_, index) => (
                <span
                  key={index}
                  aria-hidden
                  className={cx(
                    'size-2.5 rounded-full',
                    index < inCurrentSet ? 'bg-accent' : 'bg-ink-700',
                    index === inCurrentSet && isFocus && running && 'animate-pulse bg-focus',
                  )}
                />
              ))}
              <span className="ml-1 text-[11px] text-ink-400">
                {inCurrentSet}/{perLong} to long break
              </span>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-2">
              {idle && (
                <Button
                  variant="primary"
                  size="lg"
                  onClick={() =>
                    act('Start Pomodoro', () =>
                      api.pomodoro.start({
                        focus_minutes: focus,
                        short_break_minutes: shortBreak,
                        long_break_minutes: longBreak,
                        cycles_before_long_break: cycles,
                      }),
                    )
                  }
                >
                  <IconPlay className="size-5" /> Start focus
                </Button>
              )}

              {running && (
                <Button onClick={() => act('Pause Pomodoro', () => api.pomodoro.pause())}>
                  <IconPause className="size-4" /> Pause
                </Button>
              )}

              {paused && (
                <Button variant="primary" onClick={() => act('Resume Pomodoro', () => api.pomodoro.resume())}>
                  <IconPlay className="size-4" /> Resume
                </Button>
              )}

              {!idle && (
                <>
                  <Button variant="outline" onClick={() => act('Skip phase', () => api.pomodoro.skip())}>
                    <IconSkip className="size-4" /> Skip phase
                  </Button>
                  <Button variant="danger" onClick={() => act('Stop Pomodoro', () => api.pomodoro.stop())}>
                    <IconStop className="size-4" /> Stop
                  </Button>
                </>
              )}
            </div>

            {idle && cyclesDone > 0 && (
              <Button size="sm" variant="ghost" onClick={() => act('Reset cycles', () => api.pomodoro.resetCycles())}>
                <IconRefresh className="size-4" /> Reset cycle count ({cyclesDone})
              </Button>
            )}
          </div>
        </Card>

        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Focus today" value={formatMinutes(analytics?.focus_minutes_today ?? 0)} tone="focus" />
            <Stat label="Cycles today" value={analytics?.pomodoro_cycles_today ?? 0} tone="accent" />
          </div>

          <Card title="Durations" subtitle={idle ? 'Applied when you start' : 'Applies from the next phase'}>
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Focus (min)" htmlFor="pom-focus">
                  <Input
                    id="pom-focus"
                    type="number"
                    min={1}
                    max={180}
                    value={focus}
                    onChange={(event) => {
                      setDirty(true);
                      setFocus(clamp(event.target.value, 1, 180));
                    }}
                  />
                </Field>
                <Field label="Short break" htmlFor="pom-short">
                  <Input
                    id="pom-short"
                    type="number"
                    min={1}
                    max={60}
                    value={shortBreak}
                    onChange={(event) => {
                      setDirty(true);
                      setShortBreak(clamp(event.target.value, 1, 60));
                    }}
                  />
                </Field>
                <Field label="Long break" htmlFor="pom-long">
                  <Input
                    id="pom-long"
                    type="number"
                    min={1}
                    max={120}
                    value={longBreak}
                    onChange={(event) => {
                      setDirty(true);
                      setLongBreak(clamp(event.target.value, 1, 120));
                    }}
                  />
                </Field>
                <Field label="Blocks / long break" htmlFor="pom-cycles">
                  <Input
                    id="pom-cycles"
                    type="number"
                    min={1}
                    max={12}
                    value={cycles}
                    onChange={(event) => {
                      setDirty(true);
                      setCycles(clamp(event.target.value, 1, 12));
                    }}
                  />
                </Field>
              </div>

              <div className="flex gap-2">
                <Button
                  variant="primary"
                  className="flex-1"
                  disabled={!dirty}
                  onClick={() => {
                    setDirty(false);
                    act('Save durations', () =>
                      api.pomodoro.updateConfig({
                        focus_minutes: focus,
                        short_break_minutes: shortBreak,
                        long_break_minutes: longBreak,
                        cycles_before_long_break: cycles,
                      }),
                    );
                  }}
                >
                  Save
                </Button>
                <Button
                  variant="ghost"
                  disabled={!dirty}
                  onClick={() => {
                    setDirty(false);
                    if (pomodoro) {
                      setFocus(pomodoro.focus_minutes);
                      setShortBreak(pomodoro.short_break_minutes);
                      setLongBreak(pomodoro.long_break_minutes);
                      setCycles(pomodoro.cycles_before_long_break);
                    }
                  }}
                >
                  Revert
                </Button>
              </div>

              <div className="flex gap-2">
                {[
                  { label: '25 / 5', focus: 25, short: 5 },
                  { label: '50 / 10', focus: 50, short: 10 },
                  { label: '15 / 3', focus: 15, short: 3 },
                ].map((preset) => (
                  <Button
                    key={preset.label}
                    size="sm"
                    variant="outline"
                    className="flex-1"
                    onClick={() => {
                      setDirty(true);
                      setFocus(preset.focus);
                      setShortBreak(preset.short);
                    }}
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
            </div>
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
