/**
 * A mirror of what the 1.3" 128x64 OLED is showing.
 *
 * Drawn from the same state the firmware renders from, using the screen layouts
 * in the project reference. It is a 2:1 mono panel, so the preview keeps that
 * aspect ratio and a monospace font rather than trying to look pretty.
 */

import { useCountdown, useElapsedMs, useWallClock } from '@/hooks/useTicker';
import { formatClock, formatStopwatch } from '@/lib/format';
import { useDeskmate } from '@/store/useDeskmate';
import { cx } from './ui';

export function OledPreview({ className }: { className?: string }) {
  const device = useDeskmate((state) => state.device);
  const timer = useDeskmate((state) => state.timer);
  const pomodoro = useDeskmate((state) => state.pomodoro);
  const stopwatch = useDeskmate((state) => state.stopwatch);
  const listening = useDeskmate((state) => state.deviceListening);
  const weather = useDeskmate((state) => state.weather);

  const clock = useWallClock();
  const timerRemaining = useCountdown(timer?.ends_at, timer?.remaining_seconds ?? 0, timer?.state === 'running');
  const pomodoroRemaining = useCountdown(
    pomodoro?.ends_at,
    pomodoro?.remaining_seconds ?? 0,
    pomodoro?.state === 'running',
  );
  const elapsedMs = useElapsedMs(
    stopwatch?.started_at,
    stopwatch?.accumulated_ms ?? 0,
    stopwatch?.state === 'running',
  );

  const screen = pickScreen({
    listening,
    currentScreen: device?.current_screen,
    timerRunning: timer?.state === 'running' || timer?.state === 'paused',
    pomodoroRunning: pomodoro?.state === 'running' || pomodoro?.state === 'paused',
    stopwatchRunning: stopwatch?.state === 'running',
  });
  const lightOn = device?.relay_on ?? false;

  return (
    <div className={cx('oled aspect-[2/1] w-full rounded-lg p-3 sm:p-4', className)}>
      <div className="flex h-full flex-col items-center justify-center gap-1 text-center leading-tight">
        {screen === 'voice' && (
          <>
            <p className="text-xs tracking-[0.2em]">LISTENING...</p>
            <p className="mt-1 text-[10px] text-oled/70">say a command</p>
          </>
        )}

        {screen === 'relay' && (
          // Mirrors drawRelay() in src/screens.cpp: "LED ON"/"LED OFF", a lamp
          // glyph (filled with rays when on, hollow when off) and the hint.
          <>
            <p className="text-[10px] tracking-[0.2em] text-oled/70">LED</p>
            <p className="text-lg font-semibold tracking-wide sm:text-xl">{lightOn ? 'LED ON' : 'LED OFF'}</p>
            <LampGlyph on={lightOn} />
            <p className="text-[10px] text-oled/70">2x tap to toggle</p>
          </>
        )}

        {screen === 'timer' && timer && (
          <>
            <p className="text-[10px] tracking-[0.2em] text-oled/70">TIMER</p>
            <p className="tabular text-2xl font-semibold sm:text-3xl">{formatClock(timerRemaining)}</p>
            <p className="text-[10px] tracking-[0.15em] text-oled/70">{timer.state.toUpperCase()}</p>
          </>
        )}

        {screen === 'pomodoro' && pomodoro && (
          <>
            <p className="text-[10px] tracking-[0.2em] text-oled/70">
              {pomodoro.phase === 'focus' ? 'FOCUS' : 'BREAK'}
            </p>
            <p className="tabular text-2xl font-semibold sm:text-3xl">{formatClock(pomodoroRemaining)}</p>
            <p className="text-[10px] text-oled/70">cycle {pomodoro.completed_focus_cycles + 1}</p>
          </>
        )}

        {screen === 'stopwatch' && (
          <>
            <p className="text-[10px] tracking-[0.2em] text-oled/70">STOPWATCH</p>
            <p className="tabular text-2xl font-semibold sm:text-3xl">{formatStopwatch(elapsedMs)}</p>
            <p className="text-[10px] text-oled/70">{stopwatch?.laps.length ?? 0} laps</p>
          </>
        )}

        {screen === 'home' && (
          <>
            <p className="tabular text-2xl font-semibold sm:text-3xl">
              {clock.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })}
            </p>
            <p className="text-[10px] tracking-[0.15em] text-oled/80">
              {clock
                .toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
                .toUpperCase()}
              {weather ? `   ${weather.temperature.toFixed(1)} C ${weather.short}` : ''}
            </p>

            <p className="mt-1 flex items-center gap-2 text-[10px] text-oled/70">
              <span>WiFi {device?.wifi_connected ? '●' : '○'}</span>
              <span>
                Batt {device?.battery_percent !== null && device?.battery_percent !== undefined
                  ? `${device.battery_percent}%`
                  : 'USB'}
              </span>
            </p>
          </>
        )}
      </div>
    </div>
  );
}

/** The device's lamp glyph: a disc with eight rays when on, a ring when off. */
function LampGlyph({ on }: { on: boolean }) {
  const rays = [0, 45, 90, 135, 180, 225, 270, 315];
  return (
    <svg viewBox="0 0 32 32" className="my-0.5 size-7 sm:size-8" aria-hidden="true">
      {on ? (
        <>
          <circle cx="16" cy="16" r="7" fill="currentColor" />
          {rays.map((angle) => (
            <line
              key={angle}
              x1="16"
              y1="5.5"
              x2="16"
              y2="2"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              transform={`rotate(${angle} 16 16)`}
            />
          ))}
        </>
      ) : (
        <circle cx="16" cy="16" r="7" fill="none" stroke="currentColor" strokeWidth="1.6" />
      )}
    </svg>
  );
}

type ScreenName = 'home' | 'timer' | 'pomodoro' | 'stopwatch' | 'voice' | 'relay';

function pickScreen(input: {
  listening: boolean;
  currentScreen: string | null | undefined;
  timerRunning: boolean;
  pomodoroRunning: boolean;
  stopwatchRunning: boolean;
}): ScreenName {
  if (input.listening) return 'voice';
  // The LED screen is shown whenever the device says it is on it — after a tap
  // to it, or after a light voice command, which the firmware routes there.
  if (input.currentScreen === 'relay') return 'relay';
  if (input.timerRunning) return 'timer';
  if (input.pomodoroRunning) return 'pomodoro';
  if (input.stopwatchRunning) return 'stopwatch';
  return 'home';
}
