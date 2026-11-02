/**
 * Device vocabulary shared by every page: what the relay is called, the device's
 * screen cycle, and human labels for command intents.
 *
 * Kept in one place so the header, Overview, Device page and OLED mirror can
 * never disagree with each other — or with the firmware.
 */

import { useDeskmate } from '@/store/useDeskmate';

/**
 * Fallback name for the relay. The relay switches an LED light, and the device
 * itself labels the screen "LED", so that is the default everywhere.
 */
export const DEFAULT_LIGHT_LABEL = 'LED light';

/**
 * The user-facing name of the relay-switched light: the `relay_label` setting
 * if one is saved, otherwise "LED light". "Desk lamp" was the old built-in
 * default and is treated as unset, so existing installs pick up the new name.
 */
export function useLightLabel(): string {
  const raw = useDeskmate((state) => state.settings.relay_label);
  const label = typeof raw === 'string' ? raw.trim() : '';
  return label && label !== 'Desk lamp' ? label : DEFAULT_LIGHT_LABEL;
}

/**
 * The firmware's screens, in the order a tap cycles through them on the device
 * (src/screens.cpp `next()`): Home → Timer → Stopwatch → Alarms → Pomodoro →
 * Tasks → Reminders → LED → Home. Network is not in the touch cycle; it is only
 * reachable from here.
 */
export const DEVICE_SCREENS: { name: string; label: string; inCycle: boolean }[] = [
  { name: 'home', label: 'Home', inCycle: true },
  { name: 'timer', label: 'Timer', inCycle: true },
  { name: 'stopwatch', label: 'Stopwatch', inCycle: true },
  { name: 'alarms', label: 'Alarms', inCycle: true },
  { name: 'pomodoro', label: 'Pomodoro', inCycle: true },
  { name: 'tasks', label: 'Tasks', inCycle: true },
  { name: 'reminders', label: 'Reminders', inCycle: true },
  { name: 'relay', label: 'LED', inCycle: true },
  { name: 'network', label: 'Network', inCycle: false },
];

/** "relay" -> "LED", unknown names pass through. */
export function screenLabel(name: string | null | undefined): string {
  if (!name) return '—';
  return DEVICE_SCREENS.find((screen) => screen.name === name)?.label ?? name;
}

const INTENT_LABELS: Record<string, string> = {
  'relay.on': 'light on',
  'relay.off': 'light off',
  'relay.toggle': 'light toggle',
  'timer.start': 'timer start',
  'timer.pause': 'timer pause',
  'timer.resume': 'timer resume',
  'timer.cancel': 'timer cancel',
  'timer.status': 'timer status',
  'weather.current': 'weather',
  'clock.time': 'time',
  'clock.date': 'date',
  'notes.quiz': 'notes quiz',
};

/** Badge text for a command's intent: "relay.on" -> "light on". */
export function intentLabel(intent: string | null | undefined): string {
  if (!intent) return 'chat';
  return INTENT_LABELS[intent] ?? intent.replace('.', ' ');
}
