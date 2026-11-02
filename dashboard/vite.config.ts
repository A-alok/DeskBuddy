import { fileURLToPath, URL } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backend = env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:8000';

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      // host: true exposes the dev server on the LAN so a phone (or Capacitor
      // live-reload) can load it. Dev only.
      host: true,
      port: 5173,
      strictPort: false,
      proxy: {
        // In the browser during development we hit same-origin /api and /ws,
        // which sidesteps CORS entirely. The mobile build talks to the backend
        // directly using VITE_API_BASE_URL instead.
        '/api': { target: backend, changeOrigin: true },
        '/health': { target: backend, changeOrigin: true },
        '/ws': { target: backend, ws: true, changeOrigin: true },
      },
    },
    preview: {
      host: true,
      port: 4173,
      // Same proxy as dev, so `npm run preview` exercises the production bundle
      // against a local backend without needing CORS.
      proxy: {
        '/api': { target: backend, changeOrigin: true },
        '/health': { target: backend, changeOrigin: true },
        '/ws': { target: backend, ws: true, changeOrigin: true },
      },
    },
    build: {
      // Capacitor copies this directory into the native app.
      outDir: 'dist',
      sourcemap: mode !== 'production',
      target: 'es2022',
    },
  };
});
