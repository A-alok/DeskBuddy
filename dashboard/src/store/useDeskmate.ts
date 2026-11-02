/**
 * The single source of truth for the UI.
 *
 * Two inputs feed it:
 *   1. `GET /api/snapshot` on load and on every WebSocket (re)connect. This is
 *      the reconciliation point — we never try to replay missed events.
 *   2. WebSocket events, applied by `applyFrame`, for everything after that.
 *
 * Mutations from this client go out over REST and come back as events, so a
 * change made here and a change made on the device travel the same code path.
 *
 * Clock offset: countdowns are derived from absolute server timestamps, so a
 * client whose clock is wrong would render the wrong remaining time. We measure
 * the offset against `server_time` on every snapshot and correct for it in
 * `serverNow()`.
 */

import { create } from 'zustand';
import { api, ApiError } from '@/lib/api';
import { setDeviceId, setStoredUser, storedUser } from '@/lib/config';
import { EV } from '@/lib/events';
import { RealtimeClient, type ConnectionStatus } from '@/lib/ws';
import { notifyBuzz } from '@/lib/native';
import type {
  Alarm,
  Analytics,
  ChatMessage,
  Device,
  Pomodoro,
  Reminder,
  Snapshot,
  Stopwatch,
  Task,
  Timer,
  UserAccount,
  VoiceCommand,
  WsEnvelope,
} from '@/lib/types';

export type ToastKind = 'info' | 'success' | 'warn' | 'error';

export interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  body?: string;
}

interface DeskmateState {
  // connection
  status: ConnectionStatus;
  attempt: number;
  loading: boolean;
  error: string | null;
  lastSyncAt: number | null;
  serverOffsetMs: number;

  // domain
  device: Device | null;
  timer: Timer | null;
  timers: Timer[];
  stopwatch: Stopwatch | null;
  pomodoro: Pomodoro | null;
  alarms: Alarm[];
  reminders: Reminder[];
  tasks: Task[];
  commands: VoiceCommand[];
  analytics: Analytics | null;
  settings: Record<string, unknown>;
  weather: import('@/lib/types').Weather | null;

  // chat
  chat: ChatMessage[];
  chatSending: boolean;
  aiProvider: string | null;

  // backend health. A reachable backend with an unreachable database is a real
  // state worth showing, not an error to swallow.
  databaseStatus: string | null;
  databaseDetail: string | null;

  // transient UI
  deviceListening: boolean;
  lastTouchGesture: { gesture: string; at: number } | null;
  toasts: Toast[];

  // user account
  currentUser: UserAccount | null;

  // actions
  setCurrentUser: (user: UserAccount | null) => void;
  logout: () => void;
  loadUser: () => Promise<void>;
  init: () => void;
  teardown: () => void;
  refresh: (rangeDays?: number) => Promise<void>;
  reconnect: () => void;
  loadChat: () => Promise<void>;
  sendChat: (message: string, speak?: boolean) => Promise<void>;
  run: <T>(label: string, action: () => Promise<T>) => Promise<T | null>;
  pushToast: (toast: Omit<Toast, 'id'>) => void;
  dismissToast: (id: number) => void;
  serverNow: () => number;
}

let client: RealtimeClient | null = null;
let toastId = 0;
let refreshTimer: number | null = null;

function upsert<T extends { id: string }>(list: T[], item: T): T[] {
  const index = list.findIndex((entry) => entry.id === item.id);
  if (index === -1) return [item, ...list];
  const copy = list.slice();
  copy[index] = item;
  return copy;
}

function sortAlarms(list: Alarm[]): Alarm[] {
  return list.slice().sort((a, b) => a.time_of_day.localeCompare(b.time_of_day));
}

function sortReminders(list: Reminder[]): Reminder[] {
  return list.slice().sort((a, b) => Date.parse(a.remind_at) - Date.parse(b.remind_at));
}

function sortTasks(list: Task[]): Task[] {
  const weight: Record<string, number> = { high: 0, normal: 1, low: 2 };
  return list.slice().sort((a, b) => {
    if (a.done !== b.done) return a.done ? 1 : -1;
    const byPriority = (weight[a.priority] ?? 1) - (weight[b.priority] ?? 1);
    if (byPriority !== 0) return byPriority;
    return Date.parse(b.created_at) - Date.parse(a.created_at);
  });
}

/** A timer that is finished/cancelled should stop being "the active timer". */
function activeOrNull(timer: Timer | null): Timer | null {
  if (!timer) return null;
  return timer.state === 'finished' || timer.state === 'cancelled' ? null : timer;
}

export const useDeskmate = create<DeskmateState>()((set, get) => ({
  status: 'closed',
  attempt: 0,
  loading: true,
  error: null,
  lastSyncAt: null,
  serverOffsetMs: 0,

  device: null,
  timer: null,
  timers: [],
  stopwatch: null,
  pomodoro: null,
  alarms: [],
  reminders: [],
  tasks: [],
  commands: [],
  analytics: null,
  settings: {},
  weather: null,

  chat: [],
  chatSending: false,
  aiProvider: null,
  databaseStatus: null,
  databaseDetail: null,

  deviceListening: false,
  lastTouchGesture: null,
  toasts: [],

  currentUser: storedUser<UserAccount>(),

  setCurrentUser: (user) => {
    set({ currentUser: user });
    setStoredUser(user);
    if (user?.device_id) {
      setDeviceId(user.device_id);
    }
    void get().refresh();
  },

  logout: () => {
    set({ currentUser: null });
    setStoredUser(null);
    get().pushToast({
      kind: 'info',
      title: 'Signed Out',
      body: 'You have been signed out. Dashboard access is now locked.',
    });
  },

  loadUser: async () => {
    try {
      const stored = storedUser<UserAccount>();
      const user = await api.auth.me(stored?.username ? { username: stored.username } : undefined);
      if (user) {
        set({ currentUser: user });
        setStoredUser(user);
        if (user.device_id) {
          setDeviceId(user.device_id);
        }
      }
    } catch {
      /* ignore */
    }
  },

  serverNow: () => Date.now() + get().serverOffsetMs,

  init: () => {
    if (client) return;

    void get().loadUser();

    client = new RealtimeClient({
      onStatus: (status, info) => set({ status, attempt: info?.attempt ?? 0 }),
      onConnected: () => {
        // Reconcile rather than replay: one snapshot fixes anything missed.
        void get().refresh();
      },
      onFrame: (frame) => applyFrame(set, get, frame),
    });
    client.start();

    void get().refresh();
    void get().loadChat();
    void api
      .health()
      .then((health) =>
        set({
          aiProvider: health.ai?.mode ?? null,
          databaseStatus: health.database?.status ?? null,
          databaseDetail: health.database?.detail ?? null,
        }),
      )
      .catch(() => {});

    // Safety net: if the socket is down, still poll slowly so the UI is not
    // frozen on stale data.
    refreshTimer = window.setInterval(() => {
      if (!client?.isOpen && document.visibilityState === 'visible') {
        void get().refresh();
      }
    }, 20_000);
  },

  teardown: () => {
    client?.stop();
    client = null;
    if (refreshTimer !== null) {
      window.clearInterval(refreshTimer);
      refreshTimer = null;
    }
  },

  reconnect: () => {
    client?.reconnectNow();
    void get().refresh();
  },

  refresh: async (rangeDays = 7) => {
    try {
      const requestedAt = Date.now();
      const snapshot: Snapshot = await api.snapshot(rangeDays);
      const receivedAt = Date.now();
      // Halve the round trip to approximate the moment the server read its clock.
      const serverMs = Date.parse(snapshot.server_time);
      const offset = Number.isNaN(serverMs)
        ? 0
        : serverMs - (requestedAt + (receivedAt - requestedAt) / 2);

      set({
        loading: false,
        error: null,
        lastSyncAt: receivedAt,
        serverOffsetMs: Math.abs(offset) < 1000 ? 0 : offset,
        device: snapshot.device,
        timer: activeOrNull(snapshot.timer),
        timers: snapshot.timers,
        stopwatch: snapshot.stopwatch,
        pomodoro: snapshot.pomodoro,
        alarms: sortAlarms(snapshot.alarms),
        reminders: sortReminders(snapshot.reminders),
        tasks: sortTasks(snapshot.tasks),
        commands: snapshot.recent_commands,
        analytics: snapshot.analytics,
        settings: snapshot.settings,
        weather: snapshot.weather || null,
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Could not load state';
      set({ loading: false, error: message });
    }
  },

  loadChat: async () => {
    try {
      const messages = await api.chat.history(60);
      set({ chat: messages });
    } catch {
      /* chat history is not critical for first paint */
    }
  },

  sendChat: async (message, speak = false) => {
    const trimmed = message.trim();
    if (!trimmed || get().chatSending) return;

    // Optimistic echo so the input feels instant. The real row replaces it when
    // the response (or the chat.message event) arrives.
    const optimistic: ChatMessage = {
      id: `pending-${Date.now()}`,
      device_id: get().device?.id ?? '',
      role: 'user',
      content: trimmed,
      source: 'dashboard',
      created_at: new Date().toISOString(),
    };
    set({ chat: [...get().chat, optimistic], chatSending: true });

    try {
      const response = await api.chat.send(trimmed, speak);
      set((state) => {
        const withoutPending = state.chat.filter((m) => m.id !== optimistic.id);
        const existing = new Set(withoutPending.map((m) => m.id));
        const added = response.messages.filter((m) => !existing.has(m.id));
        return {
          chat: [...withoutPending, ...added],
          aiProvider:
            response.provider === 'local' || !response.provider
              ? state.aiProvider
              : response.provider === 'mock'
              ? state.aiProvider ?? 'offline-mock'
              : state.aiProvider ?? response.provider,
        };
      });
      if (response.action_taken) void get().refresh();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Message failed';
      set((state) => ({
        chat: state.chat.filter((m) => m.id !== optimistic.id),
        chatSending: false,
      }));
      get().pushToast({ kind: 'error', title: 'Chat failed', body: message });
    }
  },

  run: async (label, action) => {
    try {
      return await action();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Request failed';
      get().pushToast({ kind: 'error', title: label, body: message });
      return null;
    }
  },

  pushToast: (toast) => {
    const id = ++toastId;
    set((state) => ({ toasts: [...state.toasts, { ...toast, id }] }));
    window.setTimeout(() => get().dismissToast(id), toast.kind === 'error' ? 6000 : 4000);
  },

  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

// --------------------------------------------------------------------------- //
// Event reducer
// --------------------------------------------------------------------------- //

type SetState = (partial: Partial<DeskmateState> | ((state: DeskmateState) => Partial<DeskmateState>)) => void;
type GetState = () => DeskmateState;

function applyFrame(set: SetState, get: GetState, frame: WsEnvelope): void {
  const payload = frame.payload as never;

  switch (frame.type) {
    case EV.hello: {
      const hello = frame.payload as { device?: Device };
      if (hello?.device) set({ device: hello.device });
      return;
    }

    case EV.deviceStatus:
    case EV.deviceOnline:
    case EV.deviceOffline: {
      set({ device: payload as Device });
      if (frame.type === EV.deviceOffline) {
        get().pushToast({ kind: 'warn', title: 'Device went offline' });
      }
      if (frame.type === EV.deviceOnline) {
        get().pushToast({ kind: 'success', title: 'Device online' });
      }
      return;
    }

    case EV.relaySet: {
      const relay = frame.payload as { on: boolean; device?: Device };
      if (relay.device) set({ device: relay.device });
      else set((state) => ({ device: state.device ? { ...state.device, relay_on: relay.on } : null }));
      return;
    }

    case EV.screenChanged: {
      const screen = (frame.payload as { screen?: string }).screen;
      if (screen) set((state) => ({ device: state.device ? { ...state.device, current_screen: screen } : null }));
      return;
    }

    case EV.touch: {
      const gesture = (frame.payload as { gesture?: string }).gesture ?? 'tap';
      set({ lastTouchGesture: { gesture, at: Date.now() } });
      return;
    }

    // --------------------------------------------------------------- timer //
    case EV.timerStarted:
    case EV.timerPaused:
    case EV.timerResumed: {
      const timer = payload as Timer;
      set((state) => ({ timer: activeOrNull(timer), timers: upsert(state.timers, timer) }));
      if (frame.type === EV.timerStarted && frame.origin !== 'dashboard') {
        get().pushToast({ kind: 'info', title: `Timer started on ${labelOrigin(frame.origin)}`, body: timer.label });
      }
      return;
    }

    case EV.timerCancelled: {
      const timer = payload as Timer;
      set((state) => ({ timer: null, timers: upsert(state.timers, timer) }));
      return;
    }

    case EV.timerFinished: {
      const timer = payload as Timer;
      set((state) => ({ timer: null, timers: upsert(state.timers, timer) }));
      notifyBuzz();
      get().pushToast({ kind: 'success', title: 'Timer finished', body: timer.label });
      return;
    }

    // ----------------------------------------------------------- stopwatch //
    case EV.stopwatchStarted:
    case EV.stopwatchStopped:
    case EV.stopwatchLapped:
    case EV.stopwatchReset: {
      set({ stopwatch: payload as Stopwatch });
      return;
    }

    // ------------------------------------------------------------ pomodoro //
    case EV.pomodoroStarted:
    case EV.pomodoroPaused:
    case EV.pomodoroResumed:
    case EV.pomodoroStopped:
    case EV.pomodoroSkipped: {
      set({ pomodoro: payload as Pomodoro });
      return;
    }

    case EV.pomodoroPhaseChanged: {
      const pomodoro = payload as Pomodoro;
      set({ pomodoro });
      notifyBuzz();
      get().pushToast({
        kind: 'success',
        title: pomodoro.phase === 'focus' ? 'Break over — focus time' : 'Focus block done',
        body: pomodoro.phase === 'focus' ? undefined : `Take a ${pomodoro.phase === 'long_break' ? 'long' : 'short'} break`,
      });
      void get().refresh();
      return;
    }

    // -------------------------------------------------------------- alarms //
    case EV.alarmCreated:
    case EV.alarmUpdated: {
      set((state) => ({ alarms: sortAlarms(upsert(state.alarms, payload as Alarm)) }));
      return;
    }

    case EV.alarmDeleted: {
      const id = (frame.payload as { id: string }).id;
      set((state) => ({ alarms: state.alarms.filter((a) => a.id !== id) }));
      return;
    }

    case EV.alarmTriggered: {
      const alarm = payload as Alarm;
      notifyBuzz();
      get().pushToast({ kind: 'success', title: 'Alarm', body: `${alarm.label} · ${alarm.time_of_day}` });
      void get().refresh();
      return;
    }

    // ------------------------------------------------------------ reminders //
    case EV.reminderCreated:
    case EV.reminderUpdated: {
      set((state) => ({ reminders: sortReminders(upsert(state.reminders, payload as Reminder)) }));
      return;
    }

    case EV.reminderDeleted: {
      const id = (frame.payload as { id: string }).id;
      set((state) => ({ reminders: state.reminders.filter((r) => r.id !== id) }));
      return;
    }

    case EV.reminderDue: {
      const reminder = payload as Reminder;
      set((state) => ({ reminders: sortReminders(upsert(state.reminders, reminder)) }));
      notifyBuzz();
      get().pushToast({ kind: 'info', title: 'Reminder', body: reminder.text });
      return;
    }

    // ---------------------------------------------------------------- tasks //
    case EV.taskCreated:
    case EV.taskUpdated: {
      set((state) => ({ tasks: sortTasks(upsert(state.tasks, payload as Task)) }));
      return;
    }

    case EV.taskDeleted: {
      const id = (frame.payload as { id: string }).id;
      set((state) => ({ tasks: state.tasks.filter((t) => t.id !== id) }));
      return;
    }

    // ------------------------------------------------------------ voice/AI //
    case EV.voiceCommand: {
      const command = payload as VoiceCommand;
      set((state) => ({ commands: [command, ...state.commands.filter((c) => c.id !== command.id)].slice(0, 30) }));
      return;
    }

    case EV.voiceListening: {
      set({ deviceListening: Boolean((frame.payload as { listening?: boolean }).listening) });
      return;
    }

    case EV.chatMessage: {
      const message = payload as ChatMessage;
      set((state) =>
        state.chat.some((m) => m.id === message.id) ? {} : { chat: [...state.chat, message] },
      );
      return;
    }

    // ------------------------------------------------------------- settings //
    case EV.settingsUpdated: {
      const values = (frame.payload as { values?: Record<string, unknown> }).values;
      if (values) set({ settings: values });
      return;
    }

    // -------------------------------------------------------------- weather //
    case EV.weatherUpdated: {
      const weather = payload as import('@/lib/types').Weather;
      set({ weather });
      return;
    }

    default:
      return;
  }
}

function labelOrigin(origin: string): string {
  switch (origin) {
    case 'device':
    case 'touch':
      return 'the device';
    case 'voice':
      return 'voice';
    case 'mobile':
      return 'mobile';
    case 'system':
      return 'schedule';
    default:
      return origin;
  }
}
