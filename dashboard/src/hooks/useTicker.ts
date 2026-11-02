/**
 * Local tickers.
 *
 * The network never sends per-second updates. Countdowns and the stopwatch are
 * derived here from an absolute timestamp, which is why the display stays smooth
 * over a flaky link and correct after a long disconnect.
 */

import { useEffect, useRef, useState } from 'react';
import { useDeskmate } from '@/store/useDeskmate';

/** A value that changes on an interval, to drive time-based re-renders. */
export function useTicker(intervalMs = 500, enabled = true): number {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!enabled) return;

    let timer: number | null = null;

    const start = () => {
      if (timer !== null) return;
      timer = window.setInterval(() => setTick((value) => value + 1), intervalMs);
    };
    const stop = () => {
      if (timer === null) return;
      window.clearInterval(timer);
      timer = null;
    };

    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        // Re-render immediately so a backgrounded tab does not show stale time.
        setTick((value) => value + 1);
        start();
      } else {
        stop();
      }
    };

    if (document.visibilityState === 'visible') start();
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [intervalMs, enabled]);

  return tick;
}

/**
 * Seconds left until `endsAt`, corrected for client clock skew.
 * Falls back to `pausedSeconds` when the thing is not running.
 */
export function useCountdown(
  endsAt: string | null | undefined,
  pausedSeconds: number,
  running: boolean,
): number {
  const serverOffsetMs = useDeskmate((state) => state.serverOffsetMs);
  useTicker(250, running && Boolean(endsAt));

  if (!running || !endsAt) return Math.max(0, Math.floor(pausedSeconds));
  const endMs = Date.parse(endsAt);
  if (Number.isNaN(endMs)) return Math.max(0, Math.floor(pausedSeconds));
  const nowMs = Date.now() + serverOffsetMs;
  return Math.max(0, Math.round((endMs - nowMs) / 1000));
}

/** Elapsed milliseconds for the stopwatch, derived from `started_at`. */
export function useElapsedMs(
  startedAt: string | null | undefined,
  accumulatedMs: number,
  running: boolean,
): number {
  const serverOffsetMs = useDeskmate((state) => state.serverOffsetMs);
  useTicker(50, running && Boolean(startedAt));

  if (!running || !startedAt) return Math.max(0, accumulatedMs);
  const startMs = Date.parse(startedAt);
  if (Number.isNaN(startMs)) return Math.max(0, accumulatedMs);
  const nowMs = Date.now() + serverOffsetMs;
  return Math.max(0, accumulatedMs + (nowMs - startMs));
}

/** Current wall-clock time, refreshed once a second. */
export function useWallClock(): Date {
  const serverOffsetMs = useDeskmate((state) => state.serverOffsetMs);
  useTicker(1000, true);
  return new Date(Date.now() + serverOffsetMs);
}

/** Runs `handler` whenever `value` transitions to `target`. */
export function useTransition<T>(value: T, target: T, handler: () => void): void {
  const previous = useRef(value);
  useEffect(() => {
    if (previous.current !== target && value === target) handler();
    previous.current = value;
  }, [value, target, handler]);
}
