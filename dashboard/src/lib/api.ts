/**
 * Typed REST client.
 *
 * Every call goes through `request()`, which attaches the device id and the
 * optional API key and turns non-2xx responses into a single `ApiError` shape.
 * Mutations do not update local state directly: the backend echoes the change
 * back as a WebSocket event and the store applies it there. One code path for
 * "I did this" and "someone else did this" means the UI cannot drift.
 */

import { apiKey, apiUrl, storedUser } from './config';
import type {
  Alarm,
  Analytics,
  ChallengeResult,
  ChatMessage,
  ChatResponse,
  CompetitiveActivity,
  CompetitiveSummary,
  CompetitorAddResult,
  Device,
  FocusSession,
  Health,
  InviteActionResult,
  InvitesList,
  LeaderboardEntry,
  Note,
  Pomodoro,
  Priority,
  QuizSession,
  ReferralAccess,
  Reminder,
  Snapshot,
  Stopwatch,
  Task,
  Timer,
  UserAccount,
  VoiceCommand,
  WifiConfig,
} from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

interface RequestOptions {
  method?: Method;
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 12_000;

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, params, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  const headers: Record<string, string> = { Accept: 'application/json' };
  // For FormData, let the browser set Content-Type (it must include the
  // multipart boundary). Only JSON bodies get an explicit content type.
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (apiKey) headers['X-API-Key'] = apiKey;

  const currentStored = storedUser<UserAccount>();
  if (currentStored?.token) {
    headers['Authorization'] = `Bearer ${currentStored.token}`;
  }

  // Own AbortController so a hung LAN request cannot leave the UI spinning.
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path, params), {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ApiError(0, `Request timed out: ${method} ${path}`);
    }
    throw new ApiError(0, `Cannot reach the backend (${method} ${path}). Check the API base URL.`, error);
  } finally {
    window.clearTimeout(timeout);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    const detail =
      parsed && typeof parsed === 'object' && 'detail' in parsed
        ? (parsed as { detail: unknown }).detail
        : parsed;
    const message =
      typeof detail === 'string'
        ? detail
        : `${method} ${path} failed with ${response.status}`;
    throw new ApiError(response.status, message, detail);
  }

  return parsed as T;
}

// --------------------------------------------------------------------------- //
// Meta
// --------------------------------------------------------------------------- //

export const api = {
  health: () => request<Health>('/health'),
  snapshot: (rangeDays = 7) => request<Snapshot>('/api/snapshot', { params: { range_days: rangeDays } }),

  // ------------------------------------------------------------------ device //
  device: {
    status: () => request<Device>('/api/device/status'),
    setRelay: (on: boolean) =>
      request<Device>('/api/device/relay', { method: 'POST', body: { on, source: 'dashboard' } }),
    setScreen: (screen: string) =>
      request<Device>('/api/device/screen', { method: 'POST', body: { screen } }),
    ping: () => request<{ ok: boolean; detail: string | null }>('/api/device/ping', { method: 'POST' }),
    events: (limit = 50) =>
      request<
        Array<{ id: string; type: string; origin: string; payload: Record<string, unknown>; created_at: string }>
      >('/api/device/events', { params: { limit } }),
    getWifi: () => request<WifiConfig>('/api/device/wifi'),
    setWifi: (ssid: string, password?: string) =>
      request<WifiConfig>('/api/device/wifi', {
        method: 'POST',
        body: { ssid, password: password || '' },
      }),
  },

  // ------------------------------------------------------------------- timer //
  timer: {
    status: () => request<Timer | null>('/api/timer/status'),
    history: (limit = 20) => request<Timer[]>('/api/timer/history', { params: { limit } }),
    start: (input: { hours?: number; minutes?: number; seconds?: number; label?: string }) =>
      request<Timer>('/api/timer/start', {
        method: 'POST',
        body: {
          hours: input.hours ?? 0,
          minutes: input.minutes ?? 0,
          seconds: input.seconds ?? 0,
          label: input.label?.trim() || 'Timer',
          source: 'dashboard',
        },
      }),
    pause: () => request<Timer>('/api/timer/pause', { method: 'POST' }),
    resume: () => request<Timer>('/api/timer/resume', { method: 'POST' }),
    stop: () => request<Timer>('/api/timer/stop', { method: 'POST' }),
    extend: (seconds: number) =>
      request<Timer>('/api/timer/extend', { method: 'POST', body: { seconds } }),
  },

  // --------------------------------------------------------------- stopwatch //
  stopwatch: {
    status: () => request<Stopwatch>('/api/stopwatch/status'),
    start: () => request<Stopwatch>('/api/stopwatch/start', { method: 'POST' }),
    stop: () => request<Stopwatch>('/api/stopwatch/stop', { method: 'POST' }),
    lap: () => request<Stopwatch>('/api/stopwatch/lap', { method: 'POST' }),
    reset: () => request<Stopwatch>('/api/stopwatch/reset', { method: 'POST' }),
  },

  // ---------------------------------------------------------------- pomodoro //
  pomodoro: {
    status: () => request<Pomodoro>('/api/pomodoro/status'),
    start: (config?: Partial<Record<'focus_minutes' | 'short_break_minutes' | 'long_break_minutes' | 'cycles_before_long_break', number>>) =>
      request<Pomodoro>('/api/pomodoro/start', { method: 'POST', body: { ...config, source: 'dashboard' } }),
    pause: () => request<Pomodoro>('/api/pomodoro/pause', { method: 'POST' }),
    resume: () => request<Pomodoro>('/api/pomodoro/resume', { method: 'POST' }),
    stop: () => request<Pomodoro>('/api/pomodoro/stop', { method: 'POST' }),
    skip: () => request<Pomodoro>('/api/pomodoro/skip', { method: 'POST' }),
    updateConfig: (config: Partial<Record<'focus_minutes' | 'short_break_minutes' | 'long_break_minutes' | 'cycles_before_long_break', number>>) =>
      request<Pomodoro>('/api/pomodoro/config', { method: 'PATCH', body: config }),
    resetCycles: () => request<Pomodoro>('/api/pomodoro/reset-cycles', { method: 'POST' }),
    sessions: (limit = 50) => request<FocusSession[]>('/api/pomodoro/sessions', { params: { limit } }),
  },

  // ------------------------------------------------------------------ alarms //
  alarms: {
    list: () => request<Alarm[]>('/api/alarms'),
    create: (input: { label?: string; time_of_day: string; days_of_week?: number[]; enabled?: boolean }) =>
      request<Alarm>('/api/alarms', { method: 'POST', body: input }),
    update: (id: string, input: Partial<{ label: string; time_of_day: string; days_of_week: number[]; enabled: boolean }>) =>
      request<Alarm>(`/api/alarms/${id}`, { method: 'PATCH', body: input }),
    remove: (id: string) => request<{ ok: boolean }>(`/api/alarms/${id}`, { method: 'DELETE' }),
  },

  // ------------------------------------------------------------------- tasks //
  tasks: {
    list: (done?: boolean, list_type?: 'personal' | 'competitive') =>
      request<Task[]>('/api/tasks', { params: { done, list_type } }),
    create: (input: {
      title: string;
      notes?: string;
      priority?: Priority;
      due_at?: string;
      list_type?: 'personal' | 'competitive';
      xp?: number;
    }) => request<Task>('/api/tasks', { method: 'POST', body: { ...input, source: 'dashboard' } }),
    update: (
      id: string,
      input: Partial<{
        title: string;
        notes: string | null;
        priority: Priority;
        done: boolean;
        due_at: string | null;
        list_type: 'personal' | 'competitive';
        xp: number;
      }>,
    ) => request<Task>(`/api/tasks/${id}`, { method: 'PATCH', body: input }),
    remove: (id: string) => request<{ ok: boolean }>(`/api/tasks/${id}`, { method: 'DELETE' }),
  },

  // --------------------------------------------------------------- reminders //
  reminders: {
    list: (done?: boolean) => request<Reminder[]>('/api/reminders', { params: { done } }),
    create: (input: { text: string; remind_at?: string; in_minutes?: number }) =>
      request<Reminder>('/api/reminders', { method: 'POST', body: { ...input, source: 'dashboard' } }),
    update: (id: string, input: Partial<{ text: string; remind_at: string; done: boolean }>) =>
      request<Reminder>(`/api/reminders/${id}`, { method: 'PATCH', body: input }),
    remove: (id: string) => request<{ ok: boolean }>(`/api/reminders/${id}`, { method: 'DELETE' }),
  },

  // --------------------------------------------------------------- analytics //
  analytics: (rangeDays = 7) => request<Analytics>('/api/analytics', { params: { range_days: rangeDays } }),

  // -------------------------------------------------------------- chat/voice //
  chat: {
    send: (message: string, speak = false) =>
      request<ChatResponse>('/api/chat', { method: 'POST', body: { message, speak, source: 'dashboard' }, timeoutMs: 30_000 }),
    history: (limit = 50) => request<ChatMessage[]>('/api/chat/history', { params: { limit } }),
    clear: () => request<{ deleted: number }>('/api/chat/history', { method: 'DELETE' }),
  },
  voice: {
    commands: (limit = 25) => request<VoiceCommand[]>('/api/voice/commands', { params: { limit } }),
  },

  // ------------------------------------------------------------ study notes //
  study: {
    notes: () => request<Note[]>('/api/notes'),
    note: (id: string) => request<Note>(`/api/notes/${id}`),
    upload: (file: File) => {
      const form = new FormData();
      form.append('file', file, file.name);
      // Extraction + storage can take a moment for a big PDF.
      return request<Note>('/api/notes/upload', { method: 'POST', body: form, timeoutMs: 60_000 });
    },
    removeNote: (id: string) => request<{ ok: boolean }>(`/api/notes/${id}`, { method: 'DELETE' }),

    startQuiz: (input: { note_id: string; count?: number; difficulty?: string; style?: string }) =>
      request<QuizSession>('/api/quiz/start', { method: 'POST', body: input, timeoutMs: 60_000 }),
    quiz: (id: string) => request<QuizSession>(`/api/quiz/${id}`),
    answer: (id: string, answer: string) =>
      request<QuizSession>(`/api/quiz/${id}/answer`, { method: 'POST', body: { answer }, timeoutMs: 60_000 }),
  },

  // ---------------------------------------------------- user auth & accounts //
  auth: {
    me: (params?: { username?: string; device_id?: string }) => request<UserAccount>('/api/auth/me', { params }),
    accounts: () => request<UserAccount[]>('/api/auth/accounts'),
    login: (username: string, password?: string) =>
      request<UserAccount>('/api/auth/login', { method: 'POST', body: { username, password } }),
    register: (data: {
      username: string;
      password?: string;
      display_name?: string;
      avatar?: string;
      device_id?: string;
    }) => request<UserAccount>('/api/auth/register', { method: 'POST', body: data }),
  },

  // --------------------------------------------------- competitive learning //
  competitive: {
    access: () => request<ReferralAccess>('/api/competitive/access'),
    unlock: (referral_code: string) =>
      request<ReferralAccess>('/api/competitive/unlock', {
        method: 'POST',
        body: { referral_code },
      }),
    challenge: (competition_code: string) =>
      request<ChallengeResult>('/api/competitive/challenge', {
        method: 'POST',
        body: { competition_code },
      }),
    invites: () => request<InvitesList>('/api/competitive/invites'),
    acceptInvite: (invite_id: string) =>
      request<InviteActionResult>(`/api/competitive/invites/${invite_id}/accept`, {
        method: 'POST',
      }),
    declineInvite: (invite_id: string) =>
      request<InviteActionResult>(`/api/competitive/invites/${invite_id}/decline`, {
        method: 'POST',
      }),
    cancelInvite: (invite_id: string) =>
      request<InviteActionResult>(`/api/competitive/invites/${invite_id}/cancel`, {
        method: 'POST',
      }),
    addCompetitor: (competition_code: string) =>
      request<CompetitorAddResult>('/api/competitive/competitors', {
        method: 'POST',
        body: { competition_code },
      }),
    removeCompetitor: (competition_code: string) =>
      request<{ ok: boolean }>(`/api/competitive/competitors/${competition_code}`, {
        method: 'DELETE',
      }),
    summary: () => request<CompetitiveSummary>('/api/competitive/summary'),
    leaderboard: () => request<LeaderboardEntry[]>('/api/competitive/leaderboard'),
    activity: () => request<CompetitiveActivity[]>('/api/competitive/activity'),
  },

  // ---------------------------------------------------------------- settings //
  settings: {
    get: () => request<{ device_id: string; values: Record<string, unknown> }>('/api/settings'),
    update: (values: Record<string, unknown>) =>
      request<{ device_id: string; values: Record<string, unknown> }>('/api/settings', {
        method: 'PUT',
        body: { values },
      }),
    defaults: () => request<Record<string, unknown>>('/api/settings/defaults'),
  },
};

export type Api = typeof api;
