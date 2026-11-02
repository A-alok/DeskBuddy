import { useEffect, useState } from 'react';
import { OledPreview } from '@/components/OledPreview';
import { IconBluetooth, IconBulb, IconRefresh } from '@/components/icons';
import { BluetoothPairingModal } from '@/components/BluetoothPairingModal';
import { Badge, Button, Card, Dot, EmptyState, PageHeader, Stat, cx } from '@/components/ui';
import { api } from '@/lib/api';
import { DEVICE_SCREENS, screenLabel, useLightLabel } from '@/lib/device';
import {
  formatBytes,
  formatDateTime,
  formatRelative,
  formatUptime,
  signalLabel,
} from '@/lib/format';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';



interface EventRow {
  id: string;
  type: string;
  origin: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export function DevicePage() {
  const device = useDeskmate((state) => state.device);
  const status = useDeskmate((state) => state.status);
  const listening = useDeskmate((state) => state.deviceListening);
  const lastTouch = useDeskmate((state) => state.lastTouchGesture);
  const run = useDeskmate((state) => state.run);
  const lightLabel = useLightLabel();

  const [events, setEvents] = useState<EventRow[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [bleModalOpen, setBleModalOpen] = useState(false);

  const loadEvents = () => {
    setLoadingEvents(true);
    void api.device
      .events(40)
      .then(setEvents)
      .catch(() => {})
      .finally(() => setLoadingEvents(false));
  };

  useEffect(loadEvents, []);

  const batteryKnown = device?.battery_percent !== null && device?.battery_percent !== undefined;

  return (
    <>
      <PageHeader
        title="Device status"
        subtitle={device ? `${device.name} · ${device.id}` : 'No device registered'}
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setBleModalOpen(true)}
              className="text-blue-400 border-blue-500/30 hover:bg-blue-500/10 flex items-center gap-1.5 cursor-pointer"
            >
              <IconBluetooth className="size-3.5" />
              <span>Pair Bluetooth</span>
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                void run('Ping device', async () => {
                  const result = await api.device.ping();
                  useDeskmate.getState().pushToast({
                    kind: result.ok ? 'success' : 'warn',
                    title: result.ok ? 'Device answered' : 'No device connection',
                    body: result.detail ?? undefined,
                  });
                  return result;
                })
              }
            >
              Ping device
            </Button>
          </div>
        }
      />

      {!device ? (
        <div className="space-y-4">
          <EmptyState
            title="No device has checked in"
            body="The ESP32 registers itself on its first heartbeat. You can pair it over Bluetooth to beam your Wi-Fi credentials directly from this browser."
          />
          <div className="flex justify-center">
            <Button
              variant="primary"
              onClick={() => setBleModalOpen(true)}
              className="flex items-center gap-2 font-bold cursor-pointer"
            >
              <IconBluetooth className="size-4" />
              <span>Pair Device via Bluetooth (BLE)</span>
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat
              label="Presence"
              value={device.online ? 'Online' : 'Offline'}
              sub={device.last_seen_at ? `seen ${formatRelative(device.last_seen_at)}` : 'never seen'}
              tone={device.online ? 'accent' : undefined}
            />
            <Stat
              label="Battery"
              value={batteryKnown ? `${device.battery_percent}%` : 'USB'}
              sub={
                device.battery_voltage !== null && device.battery_voltage !== undefined
                  ? `${device.battery_voltage.toFixed(2)} V${device.charging ? ' · charging' : ''}`
                  : 'no cell connected'
              }
              tone={batteryKnown && (device.battery_percent ?? 0) < 20 ? 'break' : 'accent'}
            />
            <Stat
              label="Wi-Fi"
              value={device.wifi_connected ? signalLabel(device.wifi_rssi) : 'Down'}
              sub={device.wifi_ssid ?? '—'}
              tone={device.wifi_connected ? 'focus' : undefined}
            />
            <Stat label="Uptime" value={formatUptime(device.uptime_seconds)} sub={`heap ${formatBytes(device.free_heap_bytes)}`} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card title="Screen mirror" subtitle={`Active screen: ${screenLabel(device.current_screen)}`}>
              <OledPreview />

              <div className="mt-4">
                <p className="mb-2 text-xs font-medium text-ink-300">Show a screen on the device</p>
                <div className="flex flex-wrap gap-2">
                  {DEVICE_SCREENS.map((screen) => (
                    <Button
                      key={screen.name}
                      size="sm"
                      variant={device.current_screen === screen.name ? 'primary' : 'outline'}
                      aria-pressed={device.current_screen === screen.name}
                      onClick={() => {
                        tap();
                        void run('Set screen', () => api.device.setScreen(screen.name));
                      }}
                    >
                      {screen.label}
                    </Button>
                  ))}
                </div>
                <p className="mt-2 text-[11px] text-ink-400">
                  Same order as a tap on the device: Home → Timer → Stopwatch → Alarms → Pomodoro → Tasks →
                  Reminders → LED. Network is only reachable from here.
                </p>
              </div>
            </Card>

            <Card title="Hardware">
              <dl className="flex flex-col divide-y divide-ink-800 text-sm">
                <Row label={lightLabel}>
                  <div className="flex items-center gap-2">
                    <Badge tone={device.relay_on ? 'good' : 'neutral'}>{device.relay_on ? 'on' : 'off'}</Badge>
                    <Button
                      size="sm"
                      variant={device.relay_on ? 'danger' : 'primary'}
                      aria-label={`Turn the ${lightLabel} ${device.relay_on ? 'off' : 'on'}`}
                      onClick={() => {
                        tap();
                        void run(lightLabel, () => api.device.setRelay(!device.relay_on));
                      }}
                    >
                      <IconBulb className="size-4" />
                      {device.relay_on ? 'Turn off' : 'Turn on'}
                    </Button>
                  </div>
                </Row>
                <Row label="Microphone">
                  <Badge tone={listening ? 'info' : 'neutral'}>{listening ? 'listening' : 'idle'}</Badge>
                </Row>
                <Row label="Last touch">
                  <span className="text-ink-200">
                    {lastTouch ? `${lastTouch.gesture} · ${formatRelative(new Date(lastTouch.at).toISOString())}` : '—'}
                  </span>
                </Row>
                <Row label="Firmware">
                  <span className="text-ink-200">{device.firmware_version ?? 'unknown'}</span>
                </Row>
                <Row label="IP address">
                  <span className="tabular text-ink-200">{device.ip_address ?? '—'}</span>
                </Row>
                <Row label="Device WebSocket">
                  <span className="flex items-center gap-1.5 text-ink-200">
                    <Dot tone={device.websocket_connected ? 'good' : 'bad'} />
                    {device.websocket_connected ? 'connected' : 'not connected'}
                  </span>
                </Row>
                <Row label="Dashboard socket">
                  <span className="flex items-center gap-1.5 text-ink-200">
                    <Dot tone={status === 'open' ? 'good' : 'warn'} />
                    {status}
                  </span>
                </Row>
              </dl>
            </Card>

            <Card
              title="Event log"
              subtitle="Persisted server-side"
              actions={
                <Button size="sm" variant="ghost" aria-label="Reload event log" onClick={loadEvents}>
                  <IconRefresh className="size-4" />
                </Button>
              }
            >
              {loadingEvents && events.length === 0 ? (
                <p className="text-xs text-ink-400">Loading…</p>
              ) : events.length === 0 ? (
                <EmptyState title="No events yet" />
              ) : (
                <ol className="flex max-h-[420px] flex-col divide-y divide-ink-800 overflow-y-auto">
                  {events.map((event) => (
                    <li key={event.id} className="py-2">
                      <div className="flex items-baseline justify-between gap-2">
                        <code className={cx('text-xs', tone(event.type))}>{event.type}</code>
                        <span className="shrink-0 text-[10px] text-ink-400">{formatDateTime(event.created_at)}</span>
                      </div>
                      <p className="mt-0.5 text-[11px] text-ink-400">from {event.origin}</p>
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </div>
        </>
      )}

      {/* Bluetooth Low Energy Pairing & Wi-Fi Modal */}
      <BluetoothPairingModal
        open={bleModalOpen}
        onClose={() => setBleModalOpen(false)}
      />
    </>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="text-ink-400">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function tone(type: string): string {
  if (type.startsWith('timer')) return 'text-accent';
  if (type.startsWith('pomodoro')) return 'text-focus';
  if (type.startsWith('alarm') || type.startsWith('reminder')) return 'text-break';
  if (type.startsWith('device')) return 'text-ink-300';
  return 'text-ink-200';
}
