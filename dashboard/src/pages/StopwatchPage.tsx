import { IconFlag, IconPlay, IconRefresh, IconStop } from '@/components/icons';
import { Badge, Button, Card, EmptyState, PageHeader, Stat } from '@/components/ui';
import { useElapsedMs } from '@/hooks/useTicker';
import { api } from '@/lib/api';
import { formatStopwatch } from '@/lib/format';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';

export function StopwatchPage() {
  const stopwatch = useDeskmate((state) => state.stopwatch);
  const run = useDeskmate((state) => state.run);

  const running = stopwatch?.state === 'running';
  const elapsedMs = useElapsedMs(stopwatch?.started_at, stopwatch?.accumulated_ms ?? 0, running);
  const laps = stopwatch?.laps ?? [];

  // Lap splits: difference from the previous lap, newest first.
  const splits = laps.map((total, index) => ({
    index: index + 1,
    total,
    split: index === 0 ? total : total - (laps[index - 1] ?? 0),
  }));
  const fastest = splits.length > 1 ? Math.min(...splits.map((s) => s.split)) : null;
  const slowest = splits.length > 1 ? Math.max(...splits.map((s) => s.split)) : null;

  const act = (label: string, action: () => Promise<unknown>) => {
    tap();
    void run(label, action);
  };

  return (
    <>
      <PageHeader title="Stopwatch" subtitle="Elapsed time is derived from the start timestamp, not counted up." />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card>
          <div className="flex flex-col items-center gap-6 py-6">
            <p
              className="tabular text-5xl font-semibold text-ink-100 sm:text-6xl"
              role="timer"
              aria-live="off"
              aria-label={`Elapsed ${formatStopwatch(elapsedMs)}`}
            >
              {formatStopwatch(elapsedMs)}
            </p>

            <Badge tone={running ? 'good' : stopwatch?.state === 'paused' ? 'warn' : 'neutral'}>
              {stopwatch?.state ?? 'idle'}
            </Badge>

            <div className="flex flex-wrap items-center justify-center gap-2">
              {running ? (
                <Button variant="outline" onClick={() => act('Stop stopwatch', () => api.stopwatch.stop())}>
                  <IconStop className="size-4" /> Stop
                </Button>
              ) : (
                <Button variant="primary" onClick={() => act('Start stopwatch', () => api.stopwatch.start())}>
                  <IconPlay className="size-4" /> {stopwatch?.state === 'paused' ? 'Resume' : 'Start'}
                </Button>
              )}
              <Button disabled={!running} onClick={() => act('Record lap', () => api.stopwatch.lap())}>
                <IconFlag className="size-4" /> Lap
              </Button>
              <Button
                variant="danger"
                disabled={elapsedMs === 0 && laps.length === 0}
                onClick={() => act('Reset stopwatch', () => api.stopwatch.reset())}
              >
                <IconRefresh className="size-4" /> Reset
              </Button>
            </div>
          </div>
        </Card>

        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Laps" value={laps.length} />
            <Stat
              label="Best lap"
              value={fastest !== null ? formatStopwatch(fastest) : '—'}
              tone="accent"
            />
          </div>

          <Card title="Laps" subtitle="Newest first">
            {splits.length === 0 ? (
              <EmptyState title="No laps" body="Press Lap while running to record a split." />
            ) : (
              <ol className="flex max-h-[420px] flex-col divide-y divide-ink-800 overflow-y-auto">
                {splits
                  .slice()
                  .reverse()
                  .map((lap) => (
                    <li key={lap.index} className="flex items-center justify-between gap-3 py-2 text-sm">
                      <span className="text-ink-400">Lap {lap.index}</span>
                      <span className="flex items-center gap-2">
                        <span className="tabular text-ink-100">{formatStopwatch(lap.split)}</span>
                        {fastest === lap.split && splits.length > 1 && <Badge tone="good">best</Badge>}
                        {slowest === lap.split && splits.length > 1 && fastest !== lap.split && (
                          <Badge tone="warn">slowest</Badge>
                        )}
                      </span>
                      <span className="tabular w-20 text-right text-xs text-ink-400">
                        {formatStopwatch(lap.total)}
                      </span>
                    </li>
                  ))}
              </ol>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
