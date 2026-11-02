# AI DeskMate

An offline-first desk assistant built on an ESP32-S3, with a FastAPI sync hub and
a React dashboard that also ships as a mobile app.

The guiding rule from the project plan: **local functions never depend on the
network.** Clock, timer, stopwatch, alarm, Pomodoro, touch, OLED and the LED
(relay) all work with Wi-Fi down. AI adds conversation, open-ended questions,
natural-language commands with memory, Hindi/Hinglish, and quizzing you on your
own uploaded study notes.

Voice is live on real hardware: push-to-talk → Whisper → an intent pipeline that
understands free-form speech ("it's dark in here" turns the light on) → the reply
is spoken back through the speaker. See the session log in `memory.md` for the
full build history.

## What is in this repository

| Directory | What it is | Status |
|---|---|---|
| `backend/` | FastAPI sync hub — REST + WebSocket, MongoDB Atlas, Groq | Built; needs your Atlas URI |
| `dashboard/` | React + Vite + Tailwind dashboard, Capacitor-wrapped for mobile | Built and verified |
| `src/`, `include/`, `platformio.ini` | ESP32-S3 firmware — Stages 1–7 + backend sync | Compiles clean, not yet run on hardware |
| `test/host/` | Host tests for the firmware's date maths | 29 checks passing |
| `docs/` | Project reference, wiring, firmware notes | See below |

The backend and the dashboard are fully independent: separate dependency trees,
separate processes, separate ports. They share only two contracts — the JSON
schemas and the WebSocket event names.

## Quick start

Two terminals.

```powershell
# Terminal 1 — backend on :8000
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Paste your MongoDB Atlas connection string into .env, then verify:
.\.venv\Scripts\python.exe scripts\selfcheck.py

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend starts without Atlas — `/health` reports `degraded` and data
endpoints return 503 with the reason — so a wrong connection string tells you
what is wrong instead of crashing.

```powershell
# Terminal 2 — dashboard on :5173
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173. The backend seeds a device (`deskmate-01`) and a few
tasks, so every page has something to show before any hardware exists. API docs
are at http://localhost:8000/docs.

For the mobile demo, see `dashboard/README.md` — the short version is: put your
LAN IP in `dashboard/.env.production`, then `npm run cap:run:android`.

## Architecture

```
   ESP32-S3                    FastAPI backend                 React app
 ┌───────────┐               ┌─────────────────┐            ┌──────────────┐
 │ OLED      │   REST +      │ REST /api/*     │  REST +    │ web browser  │
 │ mic/amp   │◄── WebSocket ─┤ WebSocket /ws   ├── WS ─────►│ Android/iOS  │
 │ touch     │               │ scheduler       │            │ (Capacitor)  │
 │ relay     │               │ intents + AI    │            └──────────────┘
 └───────────┘               │ MongoDB Atlas   │
                             │ GroqCloud       │
                             └─────────────────┘
```

The device and the dashboard never talk to each other. The backend is the sync
hub: it persists a change, then fans one event out to everyone else.

Three decisions do most of the work:

**Absolute timestamps, not countdowns.** A running timer is stored as a UTC
`ends_at`. The ESP32, the backend and every client compute `ends_at - now`
independently. Nothing streams per-second ticks, so a backend restart, a
suspended phone or a dropped socket costs you the notification, never the
schedule. The background scheduler asks "what is already due?" once a second
rather than counting anything down.

**Reconcile, don't replay.** On connect and reconnect, clients fetch
`GET /api/snapshot` — the whole state in one request — then follow events. There
is no missed-event replay to get subtly wrong.

**One command pipeline.** A spoken command, a dashboard chat message and a button
press all converge on the same intent parser and executor. "Set a timer for 10
minutes" behaves identically from any surface, and the rule-based parser means it
works with the AI service switched off entirely.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Firmware | ESP32-S3, Arduino, C++ | per the project plan |
| Backend | FastAPI + PyMongo async, MongoDB Atlas | async WebSocket, typed schemas, managed storage with no local server to run |
| AI | GroqCloud, `openai/gpt-oss-20b` | OpenAI-compatible, free tier, ~1000 tok/s; Whisper on the same key |
| Dashboard | React 19 + Vite + TypeScript + Tailwind v4 | Vite's static `dist/` is exactly what Capacitor wants |
| Mobile | Capacitor 8 (Android generated, iOS ready) | same bundle as the web app, no second codebase |
| AI | pluggable; `mock` by default | the demo runs with no API key and no internet |

React + Vite rather than Next.js, deliberately: Capacitor needs a static bundle,
and Next's server-side half would be dead weight next to a backend that already
exists.

## Verification status

Both halves were exercised end to end, not just built:

- Backend: 45 endpoints, full REST CRUD, timer lifecycle including the scheduler
  firing a real timer, stopwatch segment accumulation, the Pomodoro phase machine
  through a long-break rollover, the intent parser across 10 phrasings, and
  bidirectional WebSocket fan-out with ping/pong and connection cleanup.
- Dashboard: typechecks clean under TypeScript 7, production build succeeds
  (~109 kB gzipped), Capacitor sync succeeds, and a simulated device was driven
  over the WebSocket through the Vite proxy — device-started timer appeared on the
  dashboard channel with its `ends_at`, and a dashboard cancel reached the device.

Not yet verified, and honestly so: no real ESP32 has connected — the firmware
side of Stage 15 does not exist yet. The Android app was generated and synced but
not installed on a handset from here (that needs the Android SDK and a device).

## Security posture

The default configuration is **unauthenticated**, so a clean checkout runs with
zero setup. That is fine on localhost and not fine anywhere else. Before you
port-forward, tunnel, or deploy:

```env
# backend/.env
REQUIRE_AUTH=true
API_KEY=<python -c "import secrets; print(secrets.token_urlsafe(32))">
DEVICE_TOKEN=<another one>
```

The dashboard then sends `X-API-Key`, the firmware sends `X-Device-Token`, and
the WebSocket takes the same value as `?token=`. Two further things worth
knowing: any `VITE_` variable is compiled into the client bundle and is readable
by anyone holding the app, and the Android debug build permits cleartext HTTP so
a LAN demo works — release builds do not.

## Firmware

```powershell
copy include\secrets.h.example include\secrets.h   # Wi-Fi + backend LAN IP
pio run -t upload
pio device monitor
```

Set three things before flashing: `DESKMATE_TZ` and `RELAY_ACTIVE_LOW` in
`include/config.h`, and your Wi-Fi and backend IP in `include/secrets.h`. Touch
polarity auto-detects at boot.

One pad, three gestures: **tap** cycles screens, **double tap** is the primary
action (on the LED screen it toggles the relay-switched light), **hold** is
push-to-talk voice. The light also responds to voice ("turn on the light") and
the dashboard. Details, architecture and the full verification status are in
[`docs/FIRMWARE.md`](docs/FIRMWARE.md).

## Documentation

| File | Contents |
|---|---|
| [`docs/AI-DeskMate-Project-Reference.md`](docs/AI-DeskMate-Project-Reference.md) | The project plan: hardware, wiring, features, roadmap |
| [`docs/FIRMWARE.md`](docs/FIRMWARE.md) | Firmware architecture, gestures, time model, sync behaviour |
| [`backend/README.md`](backend/README.md) | Endpoints, WebSocket frame table, security |
| [`dashboard/README.md`](dashboard/README.md) | Web dev, mobile builds, Capacitor gotchas |

## Roadmap position

Implemented and running on real hardware: Stages 1–7 on the device (screen
manager, NTP clock, touch, timer, stopwatch, alarm, Pomodoro), Stage 8 mic
capture, Stage 9 audio out (chimes + TTS speech), Stage 10 voice commands,
Stage 11 AI assistant (LLM intent understanding with conversation memory, on
both chat and voice; English + Hindi/Hinglish), Stage 12 backend, Stage 13
database, Stage 14 dashboard, both halves of Stage 15 sync, and a Study Notes
feature (upload PDF/Word/Excel/text, AI quizzes you from them).

Still open: Stage 16 (battery) is unblocked — the MT3608 boost converter is on
hand; next is trimming its output to 5.0 V, wiring the rail, and fitting the
GPIO 1 battery divider. Stage 17 (enclosure) is untouched. Study-notes quizzing
is dashboard-only so far; a voice path ("quiz me on my biology notes") is a
planned follow-up.



"$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -t upload

cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

cd dashboard
npm run dev