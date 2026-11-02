/**
 * Runtime configuration.
 *
 * Two very different environments have to work:
 *
 *  - Browser dev/prod: `VITE_API_BASE_URL` empty -> same-origin `/api` and
 *    `/ws`. Vite proxies them in dev, a reverse proxy does it in prod. No CORS.
 *  - Capacitor native: there is no origin to be same as, so the base URL must be
 *    an absolute `http://<lan-ip>:8000`. `localhost` would mean the phone.
 *
 * The base URL can also be overridden at runtime from the Settings page and is
 * persisted to localStorage, which is what makes the mobile demo practical — you
 * can retype your laptop's IP without rebuilding the app.
 */

const STORAGE_KEY = 'deskmate.apiBaseUrl';
const DEVICE_KEY = 'deskmate.deviceId';

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    if (value) window.localStorage.setItem(key, value);
    else window.localStorage.removeItem(key);
  } catch {
    /* private mode / storage disabled — fall back to env values */
  }
}

/** True when running inside the Capacitor native shell rather than a browser. */
export function isNative(): boolean {
  const cap = (window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } })
    .Capacitor;
  return Boolean(cap?.isNativePlatform?.());
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

const envBase = stripTrailingSlash(import.meta.env.VITE_API_BASE_URL ?? '');

/** Absolute backend origin, or '' meaning "same origin as this page". */
export function apiBaseUrl(): string {
  const override = readStored(STORAGE_KEY);
  if (override !== null) return stripTrailingSlash(override);
  return envBase;
}

export function setApiBaseUrl(value: string): void {
  writeStored(STORAGE_KEY, stripTrailingSlash(value.trim()));
}

export function deviceId(): string {
  return readStored(DEVICE_KEY) || import.meta.env.VITE_DEVICE_ID || 'deskmate-01';
}

export function setDeviceId(value: string): void {
  writeStored(DEVICE_KEY, value.trim());
}

const USER_KEY = 'deskmate.currentUser';

export function storedUser<T = any>(): T | null {
  try {
    const raw = readStored(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user: any | null): void {
  try {
    if (user) writeStored(USER_KEY, JSON.stringify(user));
    else writeStored(USER_KEY, '');
  } catch {
    /* ignore */
  }
}

export const apiKey = import.meta.env.VITE_API_KEY ?? '';

/** Build an absolute (or same-origin relative) REST URL. */
export function apiUrl(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const base = apiBaseUrl();
  const search = new URLSearchParams();
  search.set('device_id', deviceId());
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined) search.set(key, String(value));
  }
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalized}?${search.toString()}`;
}

/** WebSocket URL for the dashboard role. */
export function websocketUrl(): string {
  const base = apiBaseUrl();
  let origin: string;
  if (base) {
    origin = base.replace(/^http/i, 'ws');
  } else {
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    origin = `${scheme}//${window.location.host}`;
  }
  const params = new URLSearchParams({ role: 'dashboard', device_id: deviceId() });
  if (apiKey) params.set('token', apiKey);
  return `${origin}/ws?${params.toString()}`;
}

/** Shown on the Settings page so a misconfigured mobile build is obvious. */
export function connectionSummary(): { base: string; ws: string; native: boolean; device: string } {
  return {
    base: apiBaseUrl() || `${window.location.origin} (same origin)`,
    ws: websocketUrl(),
    native: isNative(),
    device: deviceId(),
  };
}
