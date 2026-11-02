/**
 * Capacitor bridges, all optional.
 *
 * Every call is guarded by `isNative()` and wrapped in try/catch: the same build
 * runs in a plain browser, where these plugins are either unimplemented or
 * throw. Nothing here is required for the app to work.
 */

import { App } from '@capacitor/app';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { StatusBar, Style } from '@capacitor/status-bar';
import { isNative } from './config';

export async function initNative(): Promise<void> {
  if (!isNative()) return;
  try {
    await StatusBar.setStyle({ style: Style.Dark });
    await StatusBar.setBackgroundColor({ color: '#09090b' });
  } catch {
    /* iOS with overlay status bar, or plugin unavailable */
  }
}

/** Fires when the native app returns to the foreground — good time to resync. */
export function onAppResume(handler: () => void): () => void {
  if (!isNative()) return () => {};
  let remove: (() => void) | null = null;
  void App.addListener('appStateChange', ({ isActive }) => {
    if (isActive) handler();
  }).then((listener) => {
    remove = () => void listener.remove();
  });
  return () => remove?.();
}

/** Android hardware back button: let the shell exit instead of getting stuck. */
export function onHardwareBack(handler: () => boolean): () => void {
  if (!isNative()) return () => {};
  let remove: (() => void) | null = null;
  void App.addListener('backButton', () => {
    const handled = handler();
    if (!handled) void App.exitApp();
  }).then((listener) => {
    remove = () => void listener.remove();
  });
  return () => remove?.();
}

export function tap(): void {
  if (!isNative()) return;
  void Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
}

export function notifyBuzz(): void {
  if (!isNative()) return;
  void Haptics.impact({ style: ImpactStyle.Heavy }).catch(() => {});
}
