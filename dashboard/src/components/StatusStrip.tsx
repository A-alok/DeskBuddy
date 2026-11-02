/**
 * The always-visible header strip: is the device there, is the socket up, and a
 * one-tap switch for the relay-driven LED light. Device presence and socket health are separate facts and
 * shown separately — the backend can be reachable while the ESP32 is unplugged.
 */

import { useState } from 'react';
import { api } from '@/lib/api';
import { useLightLabel } from '@/lib/device';
import { formatRelative } from '@/lib/format';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';
import { AccountModal } from './AccountModal';
import { IconBulb, IconRefresh } from './icons';
import { Badge, Button, Dot, Spinner, cx } from './ui';

export function StatusStrip() {
  const [accountModalOpen, setAccountModalOpen] = useState(false);
  const currentUser = useDeskmate((state) => state.currentUser);
  const device = useDeskmate((state) => state.device);
  const status = useDeskmate((state) => state.status);
  const attempt = useDeskmate((state) => state.attempt);
  const loading = useDeskmate((state) => state.loading);
  const error = useDeskmate((state) => state.error);
  const listening = useDeskmate((state) => state.deviceListening);
  const run = useDeskmate((state) => state.run);
  const reconnect = useDeskmate((state) => state.reconnect);
  const lightLabel = useLightLabel();

  const socketTone = status === 'open' ? 'good' : status === 'closed' ? 'bad' : 'warn';
  const batteryKnown = device?.battery_percent !== null && device?.battery_percent !== undefined;

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {/* Account Button */}
        <button
          type="button"
          onClick={() => {
            tap();
            setAccountModalOpen(true);
          }}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-ink-900 border border-ink-800 hover:border-amber-500/50 hover:bg-ink-850 text-xs text-ink-200 transition-all shadow-sm"
          title="Account Profile & Competition Code"
        >
          <span className="text-sm">{currentUser?.avatar || '👤'}</span>
          <span className="font-semibold text-ink-100 max-w-[90px] truncate sm:max-w-xs">
            {currentUser?.display_name || 'Login'}
          </span>
          {currentUser?.competition_code && (
            <span className="font-mono text-[10px] font-bold text-amber-400 bg-ink-950 px-1.5 py-0.2 rounded border border-ink-800">
              {currentUser.competition_code}
            </span>
          )}
        </button>

        {/* device presence */}
        <span className="flex items-center gap-1.5 text-xs text-ink-300">
          <Dot tone={device?.online ? 'good' : 'bad'} pulse={device?.online} />
          <span className="font-medium">{device?.name ?? 'Device'}</span>
          <span className="text-ink-400">{device?.online ? 'online' : 'offline'}</span>
        </span>

      {/* wifi */}
      {device?.wifi_connected && (
        <span className="hidden text-xs text-ink-400 sm:inline">
          {device.wifi_ssid ?? 'Wi-Fi'}
          {device.wifi_rssi !== null && device.wifi_rssi !== undefined ? ` ${device.wifi_rssi} dBm` : ''}
        </span>
      )}

      {/* battery */}
      <span className="tabular text-xs text-ink-400">
        {batteryKnown ? `${device?.battery_percent}%${device?.charging ? ' ⚡' : ''}` : 'USB power'}
      </span>

      {listening && <Badge tone="info">Listening</Badge>}

      <span className="grow" />

      {loading && <Spinner />}

      {error && (
        <Badge tone="bad" className="max-w-[45vw] truncate sm:max-w-xs">
          {error}
        </Badge>
      )}

      {/* LED light (relay) */}
      <Button
        size="sm"
        variant={device?.relay_on ? 'primary' : 'outline'}
        aria-pressed={device?.relay_on ?? false}
        aria-label={`${lightLabel} is ${device?.relay_on ? 'on' : 'off'}. Turn ${device?.relay_on ? 'off' : 'on'}.`}
        title={`Turn the ${lightLabel} ${device?.relay_on ? 'off' : 'on'}`}
        disabled={!device}
        onClick={() => {
          tap();
          void run(lightLabel, () => api.device.setRelay(!device?.relay_on));
        }}
      >
        <IconBulb className="size-4" />
        <span className="hidden sm:inline">
          {lightLabel} {device?.relay_on ? 'on' : 'off'}
        </span>
      </Button>

      {/* socket */}
      <button
        type="button"
        onClick={reconnect}
        title={
          status === 'open'
            ? 'Live connection to the backend'
            : `Reconnecting (attempt ${attempt}) — click to retry now`
        }
        aria-label={`WebSocket ${status}. Reconnect now.`}
        className={cx(
          'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
          socketTone === 'good' && 'border-accent/30 text-accent',
          socketTone === 'warn' && 'border-break/40 text-break',
          socketTone === 'bad' && 'border-danger/40 text-danger',
        )}
      >
        {status === 'open' ? <Dot tone="good" /> : <IconRefresh className="size-3.5" />}
        <span className="hidden sm:inline">{status === 'open' ? 'Live' : status}</span>
      </button>

      {device?.last_seen_at && !device.online && (
        <span className="text-[11px] text-ink-400">seen {formatRelative(device.last_seen_at)}</span>
      )}
    </div>

    <AccountModal open={accountModalOpen} onClose={() => setAccountModalOpen(false)} />
  </>
  );
}
