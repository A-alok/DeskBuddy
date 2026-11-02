import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Capacitor wraps the built Vite output (`dist/`) in a native shell.
 *
 * Important for the mobile demo: inside the native app there is no dev proxy,
 * so `VITE_API_BASE_URL` must point at your machine's LAN IP (not localhost —
 * on a phone that resolves to the phone itself). Example:
 *
 *   dashboard/.env.production
 *   VITE_API_BASE_URL=http://192.168.1.50:8000
 *
 * Android blocks cleartext HTTP by default. `androidScheme: 'http'` plus the
 * cleartext allowance below keeps a plain-HTTP LAN backend working for demos.
 * Use HTTPS and drop both once this is more than a demo.
 */
const config: CapacitorConfig = {
  appId: 'dev.deskmate.app',
  appName: 'AI DeskMate',
  webDir: 'dist',
  android: {
    // Lets the WebView reach an http:// backend on your LAN during demos.
    allowMixedContent: true,
  },
  server: {
    androidScheme: 'http',
    iosScheme: 'capacitor',
    // Hostnames the WebView may load over cleartext HTTP.
    cleartext: true,
  },
  plugins: {
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#09090b',
      overlaysWebView: false,
    },
  },
};

export default config;
