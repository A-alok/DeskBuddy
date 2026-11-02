/** Formatting helpers. All inputs are UTC ISO strings or plain numbers. */

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** mm:ss, or h:mm:ss once it passes an hour. */
export function formatClock(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`;
}

/** mm:ss.cc — stopwatch precision. */
export function formatStopwatch(totalMs: number): string {
  const safe = Math.max(0, Math.floor(totalMs));
  const hours = Math.floor(safe / 3_600_000);
  const minutes = Math.floor((safe % 3_600_000) / 60_000);
  const seconds = Math.floor((safe % 60_000) / 1000);
  const hundredths = Math.floor((safe % 1000) / 10);
  const pad = (n: number) => String(n).padStart(2, '0');
  const head = hours > 0 ? `${hours}:${pad(minutes)}` : pad(minutes);
  return `${head}:${pad(seconds)}.${pad(hundredths)}`;
}

/** "1h 25m", "25m", "40s" — compact human duration. */
export function formatDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  if (hours) return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
  if (minutes) return `${minutes}m`;
  return `${seconds}s`;
}

export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

export function parseIso(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

/** Local wall-clock time, e.g. "14:32". */
export function formatTimeOfDay(value: string | null | undefined, use24h = true): string {
  const ms = parseIso(value);
  if (ms === null) return '--:--';
  return new Date(ms).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: !use24h,
  });
}

export function formatDateTime(value: string | null | undefined): string {
  const ms = parseIso(value);
  if (ms === null) return '—';
  return new Date(ms).toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatDayLabel(isoDate: string): string {
  const parts = isoDate.split('-').map(Number);
  if (parts.length !== 3) return isoDate;
  const date = new Date(parts[0]!, (parts[1] ?? 1) - 1, parts[2] ?? 1);
  return DAY_NAMES[(date.getDay() + 6) % 7] ?? isoDate;
}

/** "in 12m", "2h ago", "now". */
export function formatRelative(value: string | null | undefined): string {
  const ms = parseIso(value);
  if (ms === null) return '—';
  const deltaSeconds = Math.round((ms - Date.now()) / 1000);
  const abs = Math.abs(deltaSeconds);
  if (abs < 10) return 'now';
  const unit = abs < 60 ? `${abs}s` : abs < 3600 ? `${Math.round(abs / 60)}m` : abs < 86_400 ? `${Math.round(abs / 3600)}h` : `${Math.round(abs / 86_400)}d`;
  return deltaSeconds > 0 ? `in ${unit}` : `${unit} ago`;
}

export function formatDaysOfWeek(days: number[]): string {
  if (!days.length) return 'Once';
  if (days.length === 7) return 'Every day';
  const weekdays = [0, 1, 2, 3, 4];
  if (days.length === 5 && weekdays.every((d) => days.includes(d))) return 'Weekdays';
  if (days.length === 2 && days.includes(5) && days.includes(6)) return 'Weekends';
  return days
    .slice()
    .sort((a, b) => a - b)
    .map((d) => DAY_NAMES[d] ?? '?')
    .join(' ');
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatUptime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function signalLabel(rssi: number | null | undefined): string {
  if (rssi === null || rssi === undefined) return '—';
  if (rssi >= -55) return 'Excellent';
  if (rssi >= -67) return 'Good';
  if (rssi >= -80) return 'Fair';
  return 'Weak';
}

export const DAY_SHORT_NAMES = DAY_NAMES;
