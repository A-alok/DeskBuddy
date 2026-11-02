import { useEffect, useState } from 'react';
import { Badge, Button, Card, Field, Input, PageHeader, Select, Toggle } from '@/components/ui';
import { IconBluetooth, IconEye, IconEyeOff, IconWifi } from '@/components/icons';
import { BluetoothPairingModal } from '@/components/BluetoothPairingModal';
import { api } from '@/lib/api';
import { DEFAULT_LIGHT_LABEL } from '@/lib/device';
import type { WifiConfig } from '@/lib/types';
import {
  apiBaseUrl,
  connectionSummary,
  deviceId,
  isNative,
  setApiBaseUrl,
  setDeviceId,
} from '@/lib/config';
import { useDeskmate } from '@/store/useDeskmate';

/** Device-side settings the firmware reads. Backend defaults live in api/settings.py. */
interface DeviceSettings {
  tz_offset_minutes: number;
  clock_24h: boolean;
  oled_brightness: number;
  beep_volume: number;
  speaker_volume: number;
  touch_wake_voice: boolean;
  chime_on_timer_end: boolean;
  relay_label: string;
}

const TZ_CHOICES = [
  { label: 'UTC', minutes: 0 },
  { label: 'IST (+5:30)', minutes: 330 },
  { label: 'CET (+1:00)', minutes: 60 },
  { label: 'EST (−5:00)', minutes: -300 },
  { label: 'PST (−8:00)', minutes: -480 },
  { label: 'JST (+9:00)', minutes: 540 },
];

export function SettingsPage() {
  const stored = useDeskmate((state) => state.settings);
  const deviceData = useDeskmate((state) => state.device);
  const run = useDeskmate((state) => state.run);
  const reconnect = useDeskmate((state) => state.reconnect);
  const pushToast = useDeskmate((state) => state.pushToast);

  const [form, setForm] = useState<DeviceSettings>(() => coerce(stored));
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const [baseUrl, setBaseUrl] = useState(apiBaseUrl());
  const [device, setDevice] = useState(deviceId());

  // Database-backed Wi-Fi configuration state
  const [savedWifiConfig, setSavedWifiConfig] = useState<WifiConfig | null>(null);
  const [wifiSsid, setWifiSsid] = useState('');
  const [wifiPassword, setWifiPassword] = useState('');
  const [showWifiPassword, setShowWifiPassword] = useState(false);
  const [savingWifi, setSavingWifi] = useState(false);
  const [bleModalOpen, setBleModalOpen] = useState(false);

  useEffect(() => {
    api.device
      .getWifi()
      .then((config) => {
        setSavedWifiConfig(config);
        if (config.ssid) setWifiSsid(config.ssid);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (dirty) return;
    setForm(coerce(stored));
  }, [stored, dirty]);

  const update = <K extends keyof DeviceSettings>(key: K, value: DeviceSettings[K]) => {
    setDirty(true);
    setForm((current) => ({ ...current, [key]: value }));
  };

  const save = async () => {
    setSaving(true);
    const result = await run('Save settings', () => api.settings.update({ ...form }));
    setSaving(false);
    if (result) {
      setDirty(false);
      pushToast({ kind: 'success', title: 'Settings saved', body: 'The device picks these up on its next sync.' });
    }
  };

  const applyConnection = () => {
    setApiBaseUrl(baseUrl);
    setDeviceId(device);
    reconnect();
    pushToast({
      kind: 'info',
      title: 'Connection updated',
      body: baseUrl ? `Talking to ${baseUrl}` : 'Using this page’s own origin',
    });
  };

  const saveWifi = async () => {
    if (!wifiSsid.trim()) return;
    setSavingWifi(true);
    try {
      const config = await api.device.setWifi(wifiSsid.trim(), wifiPassword);
      setSavedWifiConfig(config);
      setWifiPassword('');
      pushToast({
        kind: 'success',
        title: 'Wi-Fi Saved in Database',
        body: `Network "${config.ssid}" saved in MongoDB Atlas & dispatched to device.`,
      });
    } catch (err: any) {
      pushToast({
        kind: 'error',
        title: 'Could Not Save Wi-Fi',
        body: err?.detail || err?.message || 'Database write failed.',
      });
    } finally {
      setSavingWifi(false);
    }
  };

  const summary = connectionSummary();
  const guessedOffset = -new Date().getTimezoneOffset();

  return (
    <>
      <PageHeader title="Device settings" subtitle="Shared configuration for the firmware and the dashboard." />

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ------------------------------------------------------ clock */}
        <Card title="Clock" subtitle="Alarms are wall-clock, so the offset has to be right.">
          <div className="flex flex-col gap-4">
            <Field
              label="Timezone offset"
              htmlFor="tz"
              hint={`Your browser is at ${guessedOffset >= 0 ? '+' : ''}${guessedOffset} minutes.`}
            >
              <Select
                id="tz"
                value={String(form.tz_offset_minutes)}
                onChange={(event) => update('tz_offset_minutes', Number(event.target.value))}
              >
                {TZ_CHOICES.some((choice) => choice.minutes === form.tz_offset_minutes) ? null : (
                  <option value={String(form.tz_offset_minutes)}>Custom ({form.tz_offset_minutes} min)</option>
                )}
                {TZ_CHOICES.map((choice) => (
                  <option key={choice.minutes} value={String(choice.minutes)}>
                    {choice.label}
                  </option>
                ))}
              </Select>
            </Field>

            {form.tz_offset_minutes !== guessedOffset && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => update('tz_offset_minutes', guessedOffset)}
              >
                Use this browser’s offset ({guessedOffset >= 0 ? '+' : ''}
                {guessedOffset})
              </Button>
            )}

            <SettingRow
              label="24-hour clock"
              hint="Affects the OLED home screen."
              control={
                <Toggle
                  checked={form.clock_24h}
                  label="Use a 24-hour clock"
                  onChange={(next) => update('clock_24h', next)}
                />
              }
            />
          </div>
        </Card>

        {/* --------------------------------------------------- hardware */}
        <Card title="Hardware" subtitle="Applied by the firmware.">
          <div className="flex flex-col gap-4">
            <Field label={`OLED brightness — ${form.oled_brightness}`} htmlFor="brightness">
              <input
                id="brightness"
                type="range"
                min={10}
                max={255}
                value={form.oled_brightness}
                onChange={(event) => update('oled_brightness', Number(event.target.value))}
                className="w-full accent-[var(--color-accent)]"
              />
            </Field>

            <Field label={`Beep volume — ${form.beep_volume}/10`} htmlFor="beep">
              <input
                id="beep"
                type="range"
                min={0}
                max={10}
                value={form.beep_volume}
                onChange={(event) => update('beep_volume', Number(event.target.value))}
                className="w-full accent-[var(--color-accent)]"
              />
            </Field>

            <Field label={`Speaker volume — ${form.speaker_volume}/10`} htmlFor="speaker">
              <input
                id="speaker"
                type="range"
                min={0}
                max={10}
                value={form.speaker_volume}
                onChange={(event) => update('speaker_volume', Number(event.target.value))}
                className="w-full accent-[var(--color-accent)]"
              />
            </Field>

            <Field
              label="Light name"
              htmlFor="relay-label"
              hint="What the relay-switched light is called in the header, Overview and Device page."
            >
              <Input
                id="relay-label"
                value={form.relay_label}
                maxLength={32}
                onChange={(event) => update('relay_label', event.target.value)}
              />
            </Field>
          </div>
        </Card>

        {/* ---------------------------------------------------- behaviour */}
        <Card title="Behaviour">
          <div className="flex flex-col divide-y divide-ink-800">
            <SettingRow
              label="Touch opens voice mode"
              hint="Tapping TTP223 starts listening. No wake word yet."
              control={
                <Toggle
                  checked={form.touch_wake_voice}
                  label="Touch opens voice mode"
                  onChange={(next) => update('touch_wake_voice', next)}
                />
              }
            />
            <SettingRow
              label="Chime when a timer ends"
              hint="Plays through the MAX98357."
              control={
                <Toggle
                  checked={form.chime_on_timer_end}
                  label="Chime when a timer ends"
                  onChange={(next) => update('chime_on_timer_end', next)}
                />
              }
            />
          </div>

          <div className="mt-4 flex gap-2">
            <Button variant="primary" className="flex-1" disabled={!dirty || saving} onClick={() => void save()}>
              {saving ? 'Saving…' : 'Save settings'}
            </Button>
            <Button
              variant="ghost"
              disabled={!dirty}
              onClick={() => {
                setDirty(false);
                setForm(coerce(stored));
              }}
            >
              Revert
            </Button>
          </div>
        </Card>

        {/* --------------------------------------------------- connection */}
        <Card
          title="Connection"
          subtitle="Where this app looks for the backend."
          actions={<Badge tone={isNative() ? 'info' : 'neutral'}>{isNative() ? 'native app' : 'browser'}</Badge>}
        >
          <div className="flex flex-col gap-4">
            <Field
              label="Backend base URL"
              htmlFor="base-url"
              hint={
                isNative()
                  ? 'Native builds need an absolute LAN address — “localhost” means the phone itself.'
                  : 'Leave empty to use this page’s origin (the Vite dev proxy handles it).'
              }
            >
              <Input
                id="base-url"
                value={baseUrl}
                inputMode="url"
                autoCapitalize="off"
                autoCorrect="off"
                spellCheck={false}
                placeholder="http://192.168.1.50:8000"
                onChange={(event) => setBaseUrl(event.target.value)}
              />
            </Field>

            <Field label="Device ID" htmlFor="device-id" hint="Must match the ESP32's configured id.">
              <Input
                id="device-id"
                value={device}
                autoCapitalize="off"
                spellCheck={false}
                onChange={(event) => setDevice(event.target.value)}
              />
            </Field>

            <div className="flex gap-2">
              <Button variant="primary" className="flex-1" onClick={applyConnection}>
                Apply and reconnect
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setApiBaseUrl('');
                  setBaseUrl('');
                  reconnect();
                }}
              >
                Reset
              </Button>
            </div>

            <dl className="rounded-lg bg-ink-950/60 p-3 text-[11px]">
              <div className="flex gap-2">
                <dt className="shrink-0 text-ink-400">REST</dt>
                <dd className="break-all text-ink-300">{summary.base}</dd>
              </div>
              <div className="mt-1 flex gap-2">
                <dt className="shrink-0 text-ink-400">WS</dt>
                <dd className="break-all text-ink-300">{summary.ws}</dd>
              </div>
              <div className="mt-1 flex gap-2">
                <dt className="shrink-0 text-ink-400">Device</dt>
                <dd className="text-ink-300">{summary.device}</dd>
              </div>
            </dl>
          </div>
        </Card>

        {/* Database-Backed Device Wi-Fi Setup */}
        <Card
          title="Device Wi-Fi Setup (MongoDB)"
          actions={
            deviceData?.wifi_connected ? (
              <Badge tone="good">Hardware Connected</Badge>
            ) : (
              <Badge tone="warn">Hardware Offline / No Wi-Fi</Badge>
            )
          }
        >
          <div className="space-y-4">
            <p className="text-xs text-ink-300 leading-relaxed">
              Configure the Wi-Fi network credentials for the IoT device. Credentials are saved directly to the
              database (MongoDB Atlas) and dispatched via WebSocket so the device can store them in flash (NVS).
            </p>

            <dl className="rounded-lg bg-ink-950/60 p-3 text-[11px] space-y-1.5">
              <div className="flex justify-between items-center">
                <dt className="text-ink-400">Database SSID:</dt>
                <dd className="font-mono font-medium text-amber-300">
                  {savedWifiConfig?.ssid ? savedWifiConfig.ssid : 'None saved'}
                </dd>
              </div>
              <div className="flex justify-between items-center">
                <dt className="text-ink-400">Database Password:</dt>
                <dd>
                  {savedWifiConfig?.password_set ? (
                    <Badge tone="good">Saved in DB</Badge>
                  ) : (
                    <Badge tone="neutral">Not set</Badge>
                  )}
                </dd>
              </div>
              {savedWifiConfig?.configured_at && (
                <div className="flex justify-between items-center">
                  <dt className="text-ink-400">Last Configured:</dt>
                  <dd className="text-ink-300">
                    {new Date(savedWifiConfig.configured_at).toLocaleString()}
                  </dd>
                </div>
              )}
              <div className="flex justify-between items-center border-t border-ink-800/60 pt-1.5">
                <dt className="text-ink-400">Live Device IP:</dt>
                <dd className="font-mono text-ink-200">
                  {deviceData?.ip_address || (deviceData?.wifi_connected ? 'Connected' : 'Not Connected')}
                </dd>
              </div>
            </dl>

            <div className="space-y-3">
              <Field
                label="Wi-Fi SSID (Network Name)"
                hint="Must be a 2.4 GHz network (ESP32-S3 does not support 5 GHz Wi-Fi)."
              >
                <Input
                  value={wifiSsid}
                  onChange={(e) => setWifiSsid(e.target.value)}
                  placeholder="e.g. MyHomeNetwork_2.4G"
                />
              </Field>

              <Field
                label="Wi-Fi Password"
                hint={
                  savedWifiConfig?.password_set
                    ? 'Leave empty to keep the currently stored database password.'
                    : 'WPA2/WPA3 Personal network password.'
                }
              >
                <div className="relative">
                  <Input
                    type={showWifiPassword ? 'text' : 'password'}
                    value={wifiPassword}
                    onChange={(e) => setWifiPassword(e.target.value)}
                    placeholder={
                      savedWifiConfig?.password_set
                        ? '•••••••• (Stored — enter new to replace)'
                        : 'Enter Wi-Fi password'
                    }
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowWifiPassword(!showWifiPassword)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-200"
                    title={showWifiPassword ? 'Hide password' : 'Show password'}
                  >
                    {showWifiPassword ? (
                      <IconEyeOff className="h-4 w-4" />
                    ) : (
                      <IconEye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </Field>

              <Button
                variant="primary"
                onClick={saveWifi}
                disabled={!wifiSsid.trim() || savingWifi}
                className="w-full flex items-center justify-center gap-2 cursor-pointer font-bold"
              >
                <IconWifi className="h-4 w-4" />
                {savingWifi ? 'Saving to Database...' : 'Save Wi-Fi to Database & Sync'}
              </Button>

              <div className="relative flex py-1 items-center">
                <div className="flex-grow border-t border-ink-800" />
                <span className="flex-shrink mx-2 text-[10px] text-ink-400 uppercase tracking-wider font-semibold">
                  Or Wearable-Style BLE
                </span>
                <div className="flex-grow border-t border-ink-800" />
              </div>

              <Button
                variant="outline"
                type="button"
                onClick={() => setBleModalOpen(true)}
                className="w-full flex items-center justify-center gap-2 border-blue-500/40 text-blue-400 hover:bg-blue-500/10 hover:border-blue-500/60 transition-all font-semibold cursor-pointer"
              >
                <IconBluetooth className="size-4" />
                <span>Pair & Send Wi-Fi via Bluetooth</span>
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {/* Bluetooth Low Energy Pairing & Wi-Fi Modal */}
      <BluetoothPairingModal
        open={bleModalOpen}
        onClose={() => setBleModalOpen(false)}
        defaultSsid={wifiSsid}
      />
    </>
  );
}

function SettingRow({
  label,
  hint,
  control,
}: {
  label: string;
  hint?: string;
  control: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div className="min-w-0">
        <p className="text-sm text-ink-200">{label}</p>
        {hint && <p className="mt-0.5 text-[11px] text-ink-400">{hint}</p>}
      </div>
      {control}
    </div>
  );
}

function coerce(values: Record<string, unknown>): DeviceSettings {
  const num = (key: string, fallback: number) => {
    const raw = values[key];
    const parsed = typeof raw === 'number' ? raw : Number(raw);
    return Number.isFinite(parsed) ? parsed : fallback;
  };
  const bool = (key: string, fallback: boolean) => {
    const raw = values[key];
    return typeof raw === 'boolean' ? raw : fallback;
  };
  const str = (key: string, fallback: string) => {
    const raw = values[key];
    return typeof raw === 'string' && raw ? raw : fallback;
  };

  return {
    tz_offset_minutes: num('tz_offset_minutes', 0),
    clock_24h: bool('clock_24h', true),
    oled_brightness: num('oled_brightness', 180),
    beep_volume: num('beep_volume', 6),
    speaker_volume: num('speaker_volume', 8),
    touch_wake_voice: bool('touch_wake_voice', true),
    chime_on_timer_end: bool('chime_on_timer_end', true),
    relay_label: (() => {
      // "Desk lamp" was the old built-in default; show the new one instead.
      const label = str('relay_label', DEFAULT_LIGHT_LABEL);
      return label === 'Desk lamp' ? DEFAULT_LIGHT_LABEL : label;
    })(),
  };
}
