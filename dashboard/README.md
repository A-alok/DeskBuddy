# AI DeskMate — Dashboard

React + Vite + TypeScript + Tailwind. One codebase serves the web dashboard and,
through Capacitor, an Android/iOS app for demos. No backend code lives here: it
talks to the FastAPI service over HTTP and one WebSocket.

## Run it (web)

Start the backend first (see `../backend/README.md`), then:

```powershell
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173.

In development the app calls same-origin `/api` and `/ws`, and Vite proxies both
to `http://127.0.0.1:8000`. That means **no CORS configuration and no API base
URL to set** for web development. Point the proxy somewhere else with
`VITE_DEV_PROXY_TARGET` in `.env`.

Other scripts:

| Script | Does |
|---|---|
| `npm run dev` | dev server, exposed on the LAN so a phone can load it |
| `npm run build` | typecheck (`tsc -b`) then bundle to `dist/` |
| `npm run preview` | serve the production bundle, same proxy as dev |
| `npm run typecheck` | types only |
| `npm run cap:sync` | build + copy into the native projects |
| `npm run cap:run:android` | build, sync, install and launch on a device |
| `npm run cap:live` | native shell pointed at the dev server, live reload |

## Run it (mobile)

The Android project is already generated in `android/`.

```powershell
# 1. Point the app at your computer, not at the phone.
#    Find your LAN IP with ipconfig, then:
#    dashboard/.env.production
#    VITE_API_BASE_URL=http://192.168.0.105:8000

# 2. Start the backend so the phone can reach it
cd ..\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. Build, sync and run
cd ..\dashboard
npm run cap:run:android      # or: npm run cap:sync; npx cap open android
```

Requires Android Studio with an SDK and a JDK. For iOS you need macOS and Xcode:
`npx cap add ios && npx cap open ios`.

Three things trip people up here, all handled:

- **`localhost` on a phone means the phone.** `VITE_API_BASE_URL` must be your
  computer's LAN IP. You can also retype it at runtime on the Settings page — it
  is stored in localStorage, so a demo does not need a rebuild to point at a
  different machine.
- **Android blocks cleartext HTTP** from API 28 on. `android/app/src/debug/AndroidManifest.xml`
  enables it for debug builds only; release builds keep the secure default and
  need an HTTPS backend.
- **Routing.** The native build uses `HashRouter` (a reload on a nested path has
  no server to fall back to `index.html`); the web build uses real paths.

## Pages

Overview · AI Chat · Timer · Stopwatch · Alarms · Pomodoro · Tasks · Reminders ·
Analytics · Device status · Device settings.

Desktop gets a sidebar; phones get a five-tab bottom bar (Home, Timer, Focus,
Tasks, Chat) plus a **More** sheet for the rest. Same bundle, different
breakpoint.

## How the live sync works

```
device ──┐                         ┌── this app (browser)
         ├── backend /ws (events) ─┤
ESP32 ───┘                         └── this app (phone)
```

`src/store/useDeskmate.ts` has exactly two inputs:

1. **`GET /api/snapshot`** on load, on every WebSocket (re)connect, and when the
   native app returns to the foreground.
2. **WebSocket events** for everything after that.

Reconnect triggers a full snapshot instead of trying to replay missed events, so
there is no gap to get wrong. Local mutations go out over REST and come back as
events like anyone else's — a timer started on the device and a timer started
here follow the same code path, so the two views cannot drift.

**Nothing ticks over the network.** A running timer is an absolute `ends_at`
timestamp; `src/hooks/useTicker.ts` derives the remaining time locally. This is
why the countdown stays smooth on a bad link and is still correct after the tab
was backgrounded for an hour. Client clock skew is measured against the server's
`server_time` on each snapshot and corrected for.

The WebSocket client (`src/lib/ws.ts`) handles what actually goes wrong in
practice: exponential backoff with jitter, an immediate retry on focus/online,
and an app-level ping/pong watchdog — because a suspended phone leaves a socket
in `OPEN` with no traffic, and `readyState` will happily lie to you.

## Layout

```
dashboard/
├── src/
│   ├── main.tsx            router choice (hash on native), error boundary
│   ├── App.tsx             routes, store init, resume handling
│   ├── index.css           Tailwind v4 theme tokens, safe-area helpers
│   ├── lib/
│   │   ├── config.ts       API base + device id, env then localStorage override
│   │   ├── types.ts        mirrors backend/app/schemas.py
│   │   ├── api.ts          typed REST client with timeouts and ApiError
│   │   ├── ws.ts           reconnecting WebSocket with heartbeat watchdog
│   │   ├── events.ts       mirrors backend/app/events.py
│   │   ├── format.ts       duration / clock / relative-time formatting
│   │   └── native.ts       Capacitor status bar, haptics, resume, back button
│   ├── store/useDeskmate.ts  state + event reducer
│   ├── hooks/useTicker.ts    local tickers derived from timestamps
│   ├── components/           shell, nav, UI kit, OLED mirror, chart, toasts
│   └── pages/                the eleven pages
├── android/                Capacitor Android project
├── capacitor.config.ts
└── vite.config.ts
```

Two files are contracts with the backend and must be kept in step with it:
`src/lib/types.ts` (schemas) and `src/lib/events.ts` (event names).

## A note on the API key

`VITE_API_KEY` exists for when the backend runs with `REQUIRE_AUTH=true`. Be
aware that anything in a `VITE_` variable is compiled into the bundle and
readable by anyone who has the app or the APK. It is a shared demo credential,
not a secret. Per-user auth would mean real tokens issued by the backend.

## Accessibility

Keyboard navigable with visible focus rings, a skip link, labelled form
controls, `role="switch"` toggles with `aria-checked`, the bar chart mirrored as
a screen-reader table, toasts in a polite live region, and motion suppressed
under `prefers-reduced-motion`. Full WCAG conformance still needs manual testing
with real assistive technology and an expert review — this is a sound
foundation, not a certification.
