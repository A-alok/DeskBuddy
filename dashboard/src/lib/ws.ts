/**
 * Reconnecting WebSocket client.
 *
 * Responsibilities, in order of importance:
 *  1. Never stay silently dead. Exponential backoff with jitter, plus an
 *     immediate retry when the tab regains focus or the network comes back.
 *  2. Detect a *half-open* socket (state OPEN, no traffic) with an app-level
 *     ping/pong watchdog. Phones suspend sockets without a close frame, so
 *     readyState alone is not trustworthy.
 *  3. Tell the caller when it reconnected, so state can be re-fetched. The
 *     store refetches /api/snapshot on every (re)connect — that, not replay,
 *     is what guarantees we did not miss an event while disconnected.
 */

import { websocketUrl } from './config';
import type { WsEnvelope } from './types';

export type ConnectionStatus = 'connecting' | 'open' | 'closed' | 'reconnecting';

interface ClientOptions {
  onFrame: (frame: WsEnvelope) => void;
  onStatus: (status: ConnectionStatus, info?: { attempt: number; nextRetryMs?: number }) => void;
  /** Called on every successful (re)connect, including the first. */
  onConnected: () => void;
}

const PING_INTERVAL_MS = 20_000;
const PONG_GRACE_MS = 10_000;
const MAX_BACKOFF_MS = 15_000;

export class RealtimeClient {
  private socket: WebSocket | null = null;
  private attempt = 0;
  private stopped = true;
  private reconnectTimer: number | null = null;
  private pingTimer: number | null = null;
  private watchdogTimer: number | null = null;
  private lastInboundAt = 0;
  private readonly options: ClientOptions;

  constructor(options: ClientOptions) {
    this.options = options;
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attachEnvironmentListeners();
    this.open();
  }

  stop(): void {
    this.stopped = true;
    this.clearTimers();
    this.detachEnvironmentListeners();
    if (this.socket) {
      const socket = this.socket;
      this.socket = null;
      socket.onopen = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      try {
        socket.close(1000, 'client stop');
      } catch {
        /* already closing */
      }
    }
    this.options.onStatus('closed', { attempt: this.attempt });
  }

  /** Force an immediate reconnect (used after changing the backend URL). */
  reconnectNow(): void {
    if (this.stopped) {
      this.start();
      return;
    }
    this.attempt = 0;
    this.clearTimers();
    if (this.socket) {
      try {
        this.socket.close(4001, 'manual reconnect');
      } catch {
        /* ignore */
      }
    } else {
      this.open();
    }
  }

  get isOpen(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  send(type: string, payload: Record<string, unknown> = {}): boolean {
    if (!this.isOpen || !this.socket) return false;
    try {
      this.socket.send(JSON.stringify({ type, payload }));
      return true;
    } catch {
      return false;
    }
  }

  // ------------------------------------------------------------------ internals
  private open(): void {
    if (this.stopped) return;
    this.clearTimers();

    let socket: WebSocket;
    try {
      socket = new WebSocket(websocketUrl());
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.socket = socket;
    this.options.onStatus(this.attempt === 0 ? 'connecting' : 'reconnecting', { attempt: this.attempt });

    socket.onopen = () => {
      if (this.socket !== socket) return;
      this.attempt = 0;
      this.lastInboundAt = Date.now();
      this.options.onStatus('open', { attempt: 0 });
      this.options.onConnected();
      this.startHeartbeat();
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      if (this.socket !== socket) return;
      this.lastInboundAt = Date.now();
      let frame: WsEnvelope;
      try {
        frame = JSON.parse(event.data) as WsEnvelope;
      } catch {
        return;
      }
      if (!frame || typeof frame.type !== 'string') return;
      // pong is bookkeeping only; the timestamp above already recorded it.
      if (frame.type === 'pong') return;
      this.options.onFrame(frame);
    };

    socket.onerror = () => {
      // onclose always follows; nothing useful to do here.
    };

    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.clearTimers();
      if (this.stopped) return;
      this.scheduleReconnect();
    };
  }

  private startHeartbeat(): void {
    this.pingTimer = window.setInterval(() => {
      if (!this.isOpen) return;
      this.send('ping');
    }, PING_INTERVAL_MS);

    this.watchdogTimer = window.setInterval(() => {
      if (!this.isOpen) return;
      const silentFor = Date.now() - this.lastInboundAt;
      if (silentFor > PING_INTERVAL_MS + PONG_GRACE_MS) {
        // Half-open socket: looks connected, is not. Tear it down.
        try {
          this.socket?.close(4000, 'heartbeat timeout');
        } catch {
          /* ignore */
        }
      }
    }, PONG_GRACE_MS / 2);
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.reconnectTimer !== null) return;
    this.attempt += 1;
    const base = Math.min(500 * 2 ** (this.attempt - 1), MAX_BACKOFF_MS);
    const delay = Math.round(base * (0.7 + Math.random() * 0.6));
    this.options.onStatus('reconnecting', { attempt: this.attempt, nextRetryMs: delay });
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
  }

  private clearTimers(): void {
    for (const timer of [this.reconnectTimer, this.pingTimer, this.watchdogTimer]) {
      if (timer !== null) window.clearTimeout(timer);
    }
    if (this.pingTimer !== null) window.clearInterval(this.pingTimer);
    if (this.watchdogTimer !== null) window.clearInterval(this.watchdogTimer);
    this.reconnectTimer = null;
    this.pingTimer = null;
    this.watchdogTimer = null;
  }

  private readonly wake = (): void => {
    if (this.stopped) return;
    if (this.isOpen) return;
    // Skip the remaining backoff — the user is looking at the screen now.
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.open();
  };

  private readonly onVisibility = (): void => {
    if (document.visibilityState === 'visible') this.wake();
  };

  private attachEnvironmentListeners(): void {
    window.addEventListener('online', this.wake);
    window.addEventListener('focus', this.wake);
    document.addEventListener('visibilitychange', this.onVisibility);
  }

  private detachEnvironmentListeners(): void {
    window.removeEventListener('online', this.wake);
    window.removeEventListener('focus', this.wake);
    document.removeEventListener('visibilitychange', this.onVisibility);
  }
}
