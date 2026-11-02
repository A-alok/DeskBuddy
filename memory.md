# AI DeskMate — Project Memory

Working notes for this repository: what exists, why it was built that way, what is
verified, what is not, and what is still open. Written to be picked up cold.

**Workspace:** `c:\Users\alok2\OneDrive\Documents\PlatformIO\Projects\test`
**Last updated:** 22 September 2026 (voice + animation session)

> **State in one line:** weather, mic capture, the voice pipeline, a blinking-eye
> idle face and an eared listening face are all built and flashed. The eyes are a
> port of intellar/oled_eye_display (MIT). What remains unverified is physical:
> nobody has spoken into the mic on real hardware yet, and the panel has not been
> looked at. See §16 for the blow-by-blow and §15 for what to do next.

> **Chronology and current progress: see §16 — Session log & timeline.**
> Sections 1–15 describe the system as it stands; §16 is how it got there and
> what is being tested right now.

---

## 1. What this project is

A physical desktop assistant on an ESP32-S3, with a backend sync hub and a
dashboard that also ships as a mobile app.

The governing rule, from the original plan: **local functions never depend on the
network.** Clock, timer, stopwatch, alarm, Pomodoro, touch, OLED and relay all
work with Wi-Fi down. AI only adds conversation, open-ended questions and
multi-step commands. Every architectural decision below traces back to that
sentence.

---

## 2. Repository layout

```
test/
├── memory.md                 this file
├── README.md                 top-level orientation
├── platformio.ini            firmware build config
├── .gitignore                ignores .pio, include/secrets.h, *.exe
├── include/                  15 firmware headers
├── src/                      13 firmware sources
├── test/host/                host tests (not part of the firmware build)
├── lib/                      unused (PlatformIO default)
├── docs/
│   ├── AI-DeskMate-Project-Reference.md   the original plan, verbatim
│   └── FIRMWARE.md                        firmware architecture + status
├── vendor/
│   └── oled_eye_display/     MIT snapshot of the eye animation we ported (not built)
├── backend/                  FastAPI sync hub
│   ├── .venv/                Python 3.11.9 virtualenv
│   ├── app/                  application package
│   ├── requirements.txt      exact pins
│   ├── .env.example
│   ├── .gitignore
│   └── README.md
└── dashboard/                React + Vite + Capacitor
    ├── src/                  application source
    ├── android/              generated Capacitor Android project (tracked)
    ├── dist/                 build output (gitignored)
    ├── node_modules/
    ├── capacitor.config.ts
    ├── vite.config.ts
    ├── tsconfig{,.app,.node}.json
    ├── .env.example
    ├── .gitignore
    └── README.md
```

The three parts are independent: separate dependency trees, separate processes,
separate ports. They share exactly two contracts — the JSON schemas and the
WebSocket event names.

---

## 3. Toolchain on this machine

| Tool | Version | Note |
|---|---|---|
| Node | 24.11.1 | |
| npm | 11.6.2 | |
| Python | 3.11.9 | `python` on PATH |
| PlatformIO Core | 6.2.0 | **not on PATH** — use `$env:USERPROFILE\.platformio\penv\Scripts\pio.exe` |
| espressif32 platform | 6.12.0 | → Arduino core 2.0.17, so the **legacy `driver/i2s.h` API** applies |
| xtensa-esp32s3 toolchain | installed | |
| g++ (host tests) | msys64 | `C:\msys64\mingw64\bin\g++.exe` |

LAN IP of this machine when last checked: **192.168.1.103** (was 192.168.0.105 on
the `Alok` network; changed with the move to `sachin`). The phone and the ESP32
both need this, not `localhost`. The device sits at **192.168.1.105**.

---

## 4. Hardware

### Confirmed pin map (validated through Test 6)

| Peripheral | Signal | GPIO | Rail |
|---|---|---|---|
| OLED SH1106 (I2C 0x3C) | SDA | 8 | 3V3 |
| | SCL | 9 | |
| INMP441 mic (I2S-0 RX) | SCK/BCLK | 4 | 3V3 |
| | WS/LRCLK | 5 | |
| | SD/DOUT | 6 | |
| | L/R → GND | — | selects LEFT slot |
| MAX98357A amp (I2S-1 TX) | BCLK | 15 | **5V** |
| | LRC | 16 | |
| | DIN | 7 | |
| | SD (mute) | 10 | optional |
| TTP223 touch | OUT | 14 | 3V3 |
| Relay module (switches LED) | IN/SIG | 13 | **5V** coil, active-LOW |
| Battery sense (future) | ADC1 | 1 | not fitted |

**LED load side of the relay** (the switched light, isolated from the ESP32):
`+5V → COM`, `NO → LED anode (+)` via a ~220 Ω series resistor, `LED cathode (-) → source GND`.
NO (normally-open) keeps the LED off while idle and on when the coil energises;
wire to NC only if you want it inverted. A self-contained lamp module already has
its resistor — drive its + from COM/NO, its - to supply GND.

Free for later: GPIO 2, 11, 12, 17, 18, 21.
Avoid: 0/3/45/46 (strapping), 19/20 (USB), 43/44 (console), 35/36/37 (PSRAM),
26–32 (flash/PSRAM), 48 or 38 (RGB LED).

Mic and amp are on **separate I2S peripherals** deliberately — that is what makes
full-duplex voice possible in Stage 10 rather than half-duplex.

### Validation status

Tests 1–6 pass (ESP32-S3, OLED, mic, amp+speaker, touch, relay). Test 7
(18650 + TP4056 + MT3608 boost) in progress — the MT3608 is now on hand, so the
battery path is finally buildable.

### Power — the boost converter (MT3608) is now on hand

TP4056 `OUT+/OUT-` is **raw cell voltage through a protection IC, not regulated**:
4.2 V fresh, 3.0 V near empty. Into the 3V3 pin that exceeds the chip's ~3.6 V
absolute max; into the 5V pin the LDO browns out as the cell drops. The MT3608
boost converter bridges that gap: it steps the cell voltage **up** to a steady
5 V regardless of charge level.

```
18650 → TP4056 (B+/B-) → OUT+/OUT- → MT3608 boost (IN+/IN-) → OUT+/OUT- = 5 V rail
                                                                 ├── ESP32 5V/VIN → LDO → 3V3
                                                                 ├── MAX98357 VIN
                                                                 └── relay coil VCC
```

**MT3608 wiring (adjustable step-up):**

| MT3608 pin | Connects to | Note |
|---|---|---|
| IN+ | TP4056 `OUT+` | cell voltage in, 3.0–4.2 V |
| IN− | TP4056 `OUT−` | common ground |
| OUT+ | ESP32 `5V`/`VIN`, MAX98357 `VIN`, relay `VCC` | the regulated 5 V rail |
| OUT− | shared GND | tie to ESP32 GND and every other GND |

**Set the MT3608 output to 5.0 V with a multimeter BEFORE connecting OUT to
anything.** The module ships with its trim pot at an arbitrary position and can
output 20 V+ — enough to kill the ESP32, the amp and the OLED in one shot.
Procedure: power only IN+/IN− from the cell (or a bench supply at ~3.7 V), leave
OUT open, meter across OUT+/OUT−, turn the pot until it reads **5.00 V**, then
power down and wire OUT into the 5 V rail.

Peak current can exceed 1.5 A (Wi-Fi TX burst + audio transient + relay click).
From a 3.7 V cell that is ~2 A input, roughly 1.8 C on a 1200 mAh cell. Fit a
470–1000 µF electrolytic across the amp's VIN/GND and 100 µF + 100 nF at the
ESP32's 5 V pin, or expect random brownout resets that look like firmware bugs.

**Do not dual-source 5 V.** Check for a Schottky diode between the USB connector's
VBUS and the 5V header pin; if there isn't one, powering from the boost converter
with USB plugged in back-feeds the USB host. Charge through the TP4056's USB-C and
keep the ESP32's USB for flashing.

---

## 5. Backend — `backend/`

FastAPI sync hub. **48 OpenAPI paths.** Storage is **MongoDB Atlas**, AI is
**GroqCloud**. (Migrated off SQLite/SQLModel on 22 Sep 2026.) The two newest paths
are `GET /api/weather` and `POST /api/voice/transcribe` — both verified, see §16.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
.\.venv\Scripts\python.exe scripts\selfcheck.py   # verify against your cluster
```

`--host 0.0.0.0` is what lets the phone and the ESP32 reach it. Docs at `/docs`.

### Pinned versions (`requirements.txt`)

fastapi 0.141.1 · uvicorn[standard] 0.53.0 · pydantic 2.13.5 ·
pydantic-settings 2.15.0 · python-dotenv 1.2.3 · httpx 0.28.1 ·
python-multipart 0.0.32 · websockets 17.1 · **pymongo 4.18.1** ·
**dnspython 2.8.0**

SQLModel and SQLAlchemy are gone.

### Files

```
app/
├── main.py           app, CORS, lifespan, /health
├── config.py         env-driven settings (Atlas + Groq)
├── db.py             AsyncMongoClient, indexes, TTL, seed, health   ← was database.py
├── repo.py           thin document <-> model helpers                ← new
├── models.py         pydantic documents                             ← was SQLModel tables
├── schemas.py        request/response shapes (unchanged)
├── serializers.py    document → API, computes remaining_seconds
├── events.py         WebSocket event-name contract  ← mirrored by firmware + dashboard
├── realtime.py       connection hub, fan-out, event log
├── ws.py             /ws endpoint, inbound frame handling
├── security.py       X-API-Key / X-Device-Token dependencies
├── deps.py           device resolution, 503 when the DB is down
├── utils.py          UTC helpers, next-occurrence maths
├── api/              device, timers, stopwatch, alarms, pomodoro, tasks,
│                     reminders, analytics, chat (+ /api/ai/models), settings
└── services/         timers, stopwatch, pomodoro, alarms, analytics,
                      intents, ai (Groq), executor, scheduler
scripts/selfcheck.py  end-to-end verification against a real cluster
```

### Collections

`users` · `devices` · `timers` · `stopwatches` · `alarms` · `reminders` · `tasks` ·
`pomodoro_states` · `focus_sessions` · `voice_commands` · `device_events` ·
`settings` · `chat_messages`

Mongo conventions that matter:

- `_id` is our own uuid4 hex, exposed as `id`. **No ObjectId reaches the API**, so
  ids are unchanged from the SQLite era.
- Singletons (`stopwatches`, `pomodoro_states`) use the device id as `_id` → "get
  or create" is one idempotent upsert.
- `settings._id` is `"<device_id>:<key>"` → upsert with no read-modify-write.
- Enums stored as string values (`"running"`), readable in the Atlas UI. Models use
  `use_enum_values=True`, so **compare with `==`, never `is`** — the runtime value
  is a plain str.
- `tz_aware=True` on the client → datetimes come back aware. The naive-datetime
  bug class that SQLite forced us to handle is gone.
- **`device_events` has a TTL index** (`EVENT_RETENTION_DAYS`, default 14). It is
  the only unbounded collection and the free tier is 512 MB.
- Indexes created on every startup, idempotent, one per scheduler query.

### Behaviour worth remembering

- **Default device id** `deskmate-01`. Every endpoint takes optional `?device_id=`.
- **`GET /api/snapshot`** returns full state in one request. Clients call it on
  load and on every reconnect.
- **Scheduler** ticks once a second and asks "what is already due?" — never counts
  down. Each of those queries has a dedicated index.
- **Unknown devices self-register** on their first heartbeat.
- **Auth off by default** (`REQUIRE_AUTH=false`). Dashboard sends `X-API-Key`,
  firmware `X-Device-Token`, WebSocket `?token=`. `hmac.compare_digest`.
- **DB down is a first-class state**, not a crash: `connect()` returns False,
  `/health` says `status: degraded` with `database.detail` naming the likely fix,
  data endpoints return **503**. Error messages call out the two real causes —
  Atlas Network Access IP allowlisting, and un-percent-encoded passwords.
- **Async all the way down.** The SQLite-era tradeoff (sync sessions in async
  handlers) no longer exists.

### Groq

| Model | Speed | Note |
|---|---|---|
| `openai/gpt-oss-20b` | ~1000 tok/s | **default**, cheapest |
| `openai/gpt-oss-120b` | ~500 tok/s | stronger |
| `llama-3.3-70b-versatile` | — | **Enterprise-only, 404s on a free key** |
| `whisper-large-v3-turbo` | — | STT, **now wired** into `POST /api/voice/transcribe`. Returns a leading space + spelled digits ("ten"→"10"); 400-760 ms |

- `GROQ_REASONING_EFFORT=low` is **not** optional tuning. gpt-oss are reasoning
  models; measured on this key: default = 109 reasoning tokens / 220 ms,
  `low` = 5 tokens / 85 ms. We want two short spoken sentences.
- Valid efforts: `none default minimal low medium high xhigh max`. An invalid
  value is dropped rather than sent.
- If a model rejects `reasoning_effort`, the client retries once without it.
- Empty content (budget eaten by reasoning) is treated as an error → mock fallback
  with a message saying to raise the token budget or lower the effort.
- **`GET /api/ai/models`** lists what the key can actually use. First thing to
  check when chat starts returning the offline reply — GroqCloud retires models
  regularly.
- `AI_PROVIDER=mock`, no key, or Groq unreachable → local intent parser still runs
  every device command; open questions get a canned reply. Nothing breaks.

### Intent parser (`services/intents.py`)

Regex, not a model, on purpose: a spoken command and the same text typed into the
dashboard must behave identically. Handles timer, stopwatch, pomodoro, alarm,
reminder, task, relay, clock and device-status intents. Anything it can't classify
becomes `chat`, which is the only path that needs the network.

---

## 6. Dashboard — `dashboard/`

React 19 + Vite 8 + TypeScript 7 + Tailwind v4, Capacitor 8 for mobile.

```powershell
cd dashboard
npm run dev          # http://localhost:5173
```

In dev the app calls same-origin `/api` and `/ws`; Vite proxies both to
`http://127.0.0.1:8000`, so **no CORS setup and no API base URL for web dev**.

### Pinned versions

**deps:** react 19.3.0 · react-dom 19.3.0 · react-router-dom 7.18.4 ·
zustand 5.0.15 · @capacitor/core 8.5.2 · @capacitor/app 8.1.1 ·
@capacitor/haptics 8.0.2 · @capacitor/preferences 8.0.1 ·
@capacitor/status-bar 8.0.3

**dev:** vite 8.3.0 · typescript 7.0.2 · @vitejs/plugin-react 6.1.1 ·
tailwindcss 4.3.3 · @tailwindcss/vite 4.3.3 · @capacitor/cli 8.5.2 ·
@capacitor/android · @capacitor/ios · @types/react 19.3.0 ·
@types/react-dom 19.3.0 · @types/node

### Files

```
src/
├── main.tsx              router choice (Hash on native), error boundary
├── App.tsx               routes, store init, native resume handling
├── index.css             Tailwind v4 theme tokens, safe-area helpers
├── lib/
│   ├── config.ts         API base + device id; env, overridable at runtime
│   ├── types.ts          mirrors backend/app/schemas.py      ← contract
│   ├── api.ts            typed REST client, timeouts, ApiError
│   ├── ws.ts             reconnecting socket + heartbeat watchdog
│   ├── events.ts         mirrors backend/app/events.py       ← contract
│   ├── format.ts         duration / clock / relative time
│   └── native.ts         Capacitor status bar, haptics, resume, back button
├── store/useDeskmate.ts  state + event reducer
├── hooks/useTicker.ts    local tickers derived from timestamps
├── components/           AppShell, StatusStrip, Toasts, ui, icons,
│                         RingProgress, BarChart, OledPreview, ErrorBoundary
└── pages/                Overview, ChatPage, TimerPage, StopwatchPage,
                          AlarmsPage, PomodoroPage, TasksPage, RemindersPage,
                          AnalyticsPage, DevicePage, SettingsPage
```

Eleven pages, matching the plan. Desktop gets a sidebar; phones get a five-tab
bottom bar (Home, Timer, Focus, Tasks, Chat) plus a **More** sheet. Same bundle,
different breakpoint.

`OledPreview.tsx` mirrors the 128×64 panel from the same state the firmware
renders from — useful for demos when the hardware isn't present.

### Store behaviour

Two inputs only: `GET /api/snapshot` on load, on every WebSocket reconnect, and on
native app resume; then WebSocket events. Local mutations go out over REST and
come back as events like anyone else's, so a change made here and a change made on
the device travel the same code path.

Client clock skew is measured against `server_time` on each snapshot and corrected
for in `serverNow()` — otherwise a wrong device clock would render wrong
countdowns from correct absolute timestamps.

### Mobile

Android project generated at `dashboard/android/` and tracked in git (it carries a
patch that would be lost on regeneration). iOS is gitignored — needs macOS.

```powershell
# dashboard/.env.production
VITE_API_BASE_URL=http://192.168.0.105:8000
npm run cap:run:android
```

Three gotchas, all handled:

1. **`localhost` on a phone means the phone.** Must be a LAN IP. Also retypeable
   at runtime on the Settings page (persisted to localStorage), so a demo doesn't
   need a rebuild to point at a different machine.
2. **Android blocks cleartext HTTP** from API 28. `android/app/src/debug/AndroidManifest.xml`
   enables it for **debug builds only**; release keeps the secure default.
   *This file is hand-written and will be lost if you re-run `npx cap add android`.*
3. **Routing.** `HashRouter` on native (a reload on a nested path has no server to
   fall back to `index.html`), `BrowserRouter` on web.

---

## 7. Firmware — `src/` + `include/`

Arduino framework under PlatformIO. Stages 1–7 plus the device half of Stage 15,
chimes on the MAX98357, and now **Stage 8 mic capture + the device voice path**
(Stage 10) and a **blinking-eye idle/listening face** (Stage 9 visuals).

```powershell
copy include\secrets.h.example include\secrets.h
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -t upload
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" device monitor
```

**Footprint: RAM 15.6%** (51,024 / 327,680 B) · **Flash 15.6%** (1,021,601 / 6,553,600 B)
The +160 KB the mic needs lives in **PSRAM** (`ps_malloc`), not this internal-RAM figure.

### Libraries

olikraus/U8g2@^2.36.5 · bblanchon/ArduinoJson@^7.4.2 · links2004/WebSockets@^2.6.1

### Files

```
include/
├── config.h            pins, timings, timezone, mic + animation tunables — START HERE
├── secrets.h.example   copy to secrets.h (gitignored)
├── iso8601.h           header-only date maths, host-testable
├── eye_geometry.h      the eye/blink/listening-face maths, host-testable, no Arduino dep
├── clock_time.h        the two clocks
├── bus.h               event queue, two read cursors, RemoteScope
├── run_state.h         mirrors the backend's RunState enum
├── display.h           SH1106 + burn-in protection + draw helpers
├── animations.h        idle face (blinking eyes) + listening face (ears)
├── screens.h           screen state machine
├── mic.h               INMP441 capture on I2S-0 → PSRAM → multipart body
├── voice.h             push-to-talk state machine (Arming→Listening→Sending)
├── touch.h  relay.h  chime.h
├── timer_service.h  stopwatch_service.h  pomodoro_service.h  alarm_service.h
└── net_link.h          Wi-Fi + WebSocket + snapshot + postVoice()
src/                    one .cpp per header, plus main.cpp
test/host/
├── test_iso8601.cpp        date maths
└── test_eye_geometry.cpp   every frame of every eye animation, on the PC
```

### Three things to set before flashing

| Where | What | Why |
|---|---|---|
| `config.h` | `DESKMATE_TZ` | POSIX TZ, **sign inverted**: UTC+5:30 is `"IST-5:30"`. Currently `"UTC0"` → clock will be wrong. |
| `config.h` | `RELAY_ACTIVE_LOW` | 1 for most opto modules. Wrong = relay closed while idle. |
| `secrets.h` | Wi-Fi + `BACKEND_HOST` | Currently `CHANGE_ME`. Needs your LAN IP. |

Touch polarity **auto-detects** at boot and prints the result — that open question
from the hardware doc is resolved in code.

### Gestures — one pad, and push-to-talk changed the map

**Current map (after the voice session):**

| Gesture | Home | Every other screen |
|---|---|---|
| tap | next screen | next screen |
| double tap | **push to talk** | primary action (start / pause / toggle) |
| hold ≥900 ms | (unassigned) | **push to talk** |

Two gestures for one action because each screen had a different one spare: Home
has no secondary action worth a hold, and every other screen needs its double tap
for start/pause. This is exactly the layout the user specified: *"when on home mic
should turn on via 2x tap, other than home screen the mic should turn on via touch
and hold."*

**The cost, recorded plainly:** hold used to be the secondary action everywhere.
So **cancelling a running timer, lapping the stopwatch, skipping a Pomodoro phase,
toggling an alarm and resyncing the link are no longer reachable from the device.**
They are dashboard-only now, plus voice ("cancel the timer"). The dead switch
branches were removed rather than left unreachable. If local timer-cancel is
wanted back, the clean fix is a distinct longer hold (~2.5 s) for secondary.

Other gesture rules that still hold:
- A **blanked** panel's first touch only wakes (and dismisses the face); it does
  not act. A merely dimmed panel acts normally — it was still legible.
- The **idle face** is dismissed by any gesture, which lands you on Home with a
  confirm chime. That gesture is spent on the mode change.
- **Mid-recording, any gesture aborts** the recording.

Screens cycle: Home → Timer → Stopwatch → Alarms → Pomodoro → Tasks →
Reminders → LED (relay) → back to Home. Network is NOT in the cycle (reconnect is
a diagnostic, dashboard-only). The LED screen was brought into the cycle so the
relay-switched light can be toggled by touch alone (double tap). The screen shows
`LED ON`/`LED OFF` with a lamp glyph; the same light also responds to voice
("turn on the light") and the dashboard.
The idle face and the two voice faces are **not** in the cycle — they are modes,
not screens.

### Architecture

```
services ──► bus ──► net_link
    │                   │
    └────► screens ◄────┘
```

Single-threaded cooperative loop. No RTOS tasks, no mutexes. There are now **two**
blocking calls, both for the same reason (a request the user is actively waiting
on, not worth an async state machine): the snapshot HTTP GET at most once per
reconnect, and `netLink::postVoice()` once per voice command (430–1850 ms). The
"THINKING" frame is pushed to the panel *before* the upload starts, or it would sit
frozen on the last listening frame until the POST returns.

`mic::update()` and `voice::update()` sit in the input half of the loop: the mic
drains its DMA with a zero timeout every loop, so a slow frame drops audio rather
than stalling. `animations` owns the idle face (blinking eyes) and the listening
face (ears); `screens::render()` gives them the whole panel when they are up and
skips `sendBuffer()` between blinks so an idle face costs no I2C traffic.

Persisted in NVS (`Preferences`, namespace `deskmate`): alarms, relay state,
Pomodoro durations, brightness, volume.

---

## 8. The decisions that matter

These are the load-bearing ones. Changing any of them ripples.

### Absolute timestamps, never countdowns

A running timer is stored as an absolute instant. Device, backend and every client
compute `ends_at - now` independently. Nothing streams per-second ticks.

- A backend restart, a suspended phone or a dropped socket costs you the
  *notification*, never the *schedule*.
- A slow loop or Wi-Fi retry storm can't make the device drift.
- A client that reconnects after ten minutes lands on the correct value.

### Two clocks on the firmware

| | Source | Used for |
|---|---|---|
| `monotonicMs()` | `esp_timer`, µs since boot | **every local deadline** |
| `epochMs()` | NTP wall clock | talking to the backend, evaluating alarms |

Store deadlines as epoch values instead and the first NTP sync makes every running
timer jump. Storing them monotonically and converting only at the network boundary
means a clock correction changes what we *report*, never what we *count*. It also
means timers work before NTP has ever answered.

`millis()` is used for nothing time-critical — it wraps at 49.7 days.

Alarms are the deliberate exception: "07:00 on weekdays" is a calendar statement,
not elapsed time. They need NTP and each carries a one-per-minute fire guard so a
clock correction can't double-trigger.

### Reconcile, don't replay

On connect and reconnect, clients fetch the full snapshot. Events emitted while
disconnected are **dropped, not queued**. There is no missed-event replay to get
subtly wrong.

On reconnect the **backend wins** — it survives device reboots and is shared with
the dashboard and phone. One exception: a timer started on the device while
offline is pushed up rather than silently lost.

### Services never call the network

Firmware services mutate their own state and drop a note on the bus. Delete
`net_link.cpp` and the device still keeps time, runs timers, rings alarms,
switches the relay and drives the OLED. That is "works fully offline" expressed as
a dependency direction rather than a promise.

### The bus has two independent read cursors

One for the UI, one for the network. A single shared queue would mean whichever
consumer ran first swallowed the event — so a timer finishing while the socket was
busy would ring but not publish, or publish but not ring.

### Echo suppression via `bus::RemoteScope`

Inbound backend state is applied under an RAII guard that suppresses emission, so
a dashboard "start timer" doesn't bounce back as a device event. The backend does
echo its authoritative `timer.started` back to us and we adopt its `ends_at` —
that's the resync, not a loop.

### Two events deliberately not published by the firmware

`timer.finished` and `pomodoro.phase_changed`. The backend holds the same absolute
deadline and fires them from its own scheduler; publishing ours too would
double-notify every dashboard.

### Alarms are dual-owned

The backend owns the definition so the dashboard can edit it; the device keeps a
copy in NVS so it still rings with the network down. Both evaluate the same
"07:00 on weekdays" independently — nobody has to be told when.

### One command pipeline

Spoken command, dashboard chat and mobile chat all converge on the same intent
parser and executor. "Set a timer for 10 minutes" behaves identically from any
surface, and the rule-based parser means it works with the AI switched off.

### React + Vite, not Next.js

Capacitor needs a static bundle, and Next's server-side half would be dead weight
beside a backend that already exists.

### Animations are time-driven, and their maths is host-tested

Every animation derives its state from `monotonicMs()` on each frame, never from a
frame counter. A slow I2C write or a blocking HTTP call then drops frames rather
than slowing the motion, so the eyes always open in the same wall-clock time. All
the arithmetic lives in `include/eye_geometry.h` with no Arduino or U8g2
dependency, so `test/host/test_eye_geometry.cpp` checks every frame of every pose
on the PC. The failures worth catching are all arithmetic — a shape running off
the panel, a corner radius that breaks U8g2's `drawRBox` contract (which renders
corrupt rather than failing), an ear overlapping an eye — and finding those by
flashing and squinting at a 1.3" panel is a bad trade.

### The eyes are a port, not original — and attributed

The idle/listening faces are ported from **intellar/oled_eye_display** (MIT,
© 2024 Intellar). The geometry is theirs verbatim; their blocking `for`-loop drive
was rewritten for our cooperative loop. A snapshot of the original plus its licence
is kept in `vendor/oled_eye_display/`, and the port explains what changed. This is
a licensing obligation, not a courtesy.

### The mic builds its own HTTP body, in PSRAM

`mic.cpp` lays out the entire `multipart/form-data` request body — preamble, WAV
header, PCM, epilogue — in one `ps_malloc` buffer, so the DMA writes audio straight
to its final send address with no 160 KB copy. That framing is ours to get wrong
and independent of whether the mic works, so `backend/scripts/wireframecheck.py`
rebuilds it byte-for-byte and POSTs it to the real backend. Splitting "is the
envelope right" from "is the audio right" is what makes a failed voice command
diagnosable.

### The listening view is a face, not a waveform

An earlier scrolling bar waveform was a more faithful picture of the audio, and
that was the problem — it looked like an instrument, so the device read as
*measuring* you rather than *listening*. The eared face (same eyes, squinting, with
brows that lift and ears that fill with loudness) is less precise and reads
correctly from across a desk, which is the only distance that matters. The waveform
code was deleted, not left as a dead path.

---

## 9. WebSocket protocol

`backend/app/events.py` is the source of truth. Mirrored in
`dashboard/src/lib/events.ts` and handled in `src/net_link.cpp`. **Keep all three
in step.**

Connect:

```
ws://<host>:8000/ws?role=device&device_id=deskmate-01&token=<DEVICE_TOKEN>
ws://<host>:8000/ws?role=dashboard&device_id=deskmate-01&token=<API_KEY>
```

Envelope, both directions:

```json
{ "type": "timer.started", "device_id": "deskmate-01", "origin": "device",
  "ts": "2026-09-22T11:22:31.553Z", "payload": { "...": "..." } }
```

Frames a client may **send**: `device.heartbeat` · `timer.start|pause|resume|cancel` ·
`stopwatch.start|stop|lap|reset` · `pomodoro.start|pause|resume|stop|skip` ·
`alarm.set|cancel` · `reminder.create` · `task.create|complete` · `relay.set` ·
`screen.changed` · `touch` · `voice.command` · `voice.listening` · `ping`

Note the asymmetry: the device sends **commands** (`timer.start`), the backend
broadcasts **facts** (`timer.started`).

---

## 10. Verification status

### Verified

| What | How |
|---|---|
| Backend, 45 paths | Full smoke test: REST CRUD, timer lifecycle incl. the scheduler firing a real timer, stopwatch segment accumulation, Pomodoro phase machine through a long-break rollover, intent parser across 10 phrasings, bidirectional WebSocket fan-out, ping/pong, error frames, connection cleanup |
| Dashboard types | `tsc -b --force` clean under TypeScript 7 |
| Dashboard build | 366.21 kB raw / **109.49 kB gzipped** |
| Capacitor | `npx cap add android` + `npm run cap:sync` succeed |
| Dev proxy | Live uvicorn + vite: `/api/snapshot` 200 with seeded device + 3 tasks, `/health` 200, `/` 200, `/src/main.tsx` transformed 200 |
| WS through Vite proxy | Simulated ESP32: device→dashboard and dashboard→device both delivered, with `ends_at` intact |
| Firmware compile | **Zero warnings** under `-Wall` across all of `src/` |
| Firmware date maths | **29 host tests** — leap years (2024, 2000, 2100), every month length, `+05:30`/`-08:00` offsets, malformed-input rejection, 4000-day round trip |
| Firmware ↔ backend contract | **59 checks** against the live backend — every frame `net_link.cpp` sends replayed and accepted, heartbeat telemetry confirmed stored, every parsed field confirmed present in `timer.started` / `alarm.created` / `settings.updated` / `/api/snapshot`, `ends_at` confirmed to be the exact ISO-8601-Z shape `iso8601::parse` expects |
| Eye/face geometry | **54 host checks** (`test_eye_geometry.cpp`) — every frame of the open, blink, and listening-blink poses is on-panel, mirrored about the centre, and inside U8g2's `drawRBox` radius contract; ears clear the eyes; brows clear the eye tops and only ever lift; ripple has a rest beat; loudness fills ears inside-out. An ASCII `--render`/`--listening` mode to eyeball the motion |
| Weather feature | Live against Open-Meteo: Delhi 32.6 °C returned, cold-cache 2407 ms / warm-cache 15 ms, 4 weather intents pass. No API key needed (chose Open-Meteo over OpenWeatherMap for exactly this) |
| Voice pipeline (backend) | `voicecheck.py`: 4 real SAPI-speech WAVs through `POST /api/voice/transcribe` reach the right intent AND the action really happens — a spoken timer created a real 600 s timer, a spoken relay command physically switched the relay. Failure handling: empty upload → 502, garbage → ≥400 |
| Voice multipart framing | `wireframecheck.py`: the firmware's hand-built body, rebuilt byte-for-byte and POSTed raw to the real backend → HTTP 200, `transcript: 'Set a timer for 10 minutes.'`, `intent: timer.start`, server received exactly the bytes sent. **15 checks.** So a device-side voice failure is now provably the audio, not the envelope |

Host test commands:

```powershell
& "C:\msys64\mingw64\bin\g++.exe" -std=c++17 -Wall -Wextra -I include test/host/test_iso8601.cpp -o iso_test.exe
.\iso_test.exe
& "C:\msys64\mingw64\bin\g++.exe" -std=c++17 -Wall -Wextra -I include test/host/test_eye_geometry.cpp -o eye_test.exe
.\eye_test.exe                 # 54 checks
.\eye_test.exe --render        # watch the eyes open + blink as ASCII
.\eye_test.exe --listening     # watch the eared listening face
```

Backend test scripts (from `backend/`, venv python):

```powershell
.\.venv\Scripts\python.exe scripts\voicecheck.py       # STT + intent + action, real WAVs
.\.venv\Scripts\python.exe scripts\wireframecheck.py   # firmware multipart body vs real backend
powershell -ExecutionPolicy Bypass -File scripts\make_test_speech.ps1   # regenerate the WAV fixtures
```

### Hardware, as measured (first flash, 22 Sep 2026)

`esptool --chip esp32s3 flash_id`:

```
Chip is ESP32-S3 (QFN56) (revision v0.2)
Features: WiFi, BLE, Embedded PSRAM 8MB (AP_3v3)
Crystal is 40MHz      MAC: ac:a7:04:12:66:74
Flash: 16MB (manufacturer 68, device 4018)
```

- Confirmed **N16R8**: 16 MB flash + 8 MB **octal** PSRAM. The doc's Test 1 claim
  was right.
- Serial bridge: **WCH CH343, `VID:PID=1A86:55D3`, on COM5.** A separate USB-UART
  chip, not native USB — so `ARDUINO_USB_MODE` / `ARDUINO_USB_CDC_ON_BOOT` must
  stay commented out in `platformio.ini`.
- Upload: `pio run -t upload --upload-port COM5`. Writes ~1.0 MB in ~15 s.
- **Firmware boots clean**, 30-second soak with no watchdog reset or panic under
  the continuous 10 fps I2C refresh.
- OLED acknowledges at 0x3C, I2S TX initialises, PSRAM reports 8189 KB.

### Full stack verified end to end (22 Sep 2026)

Real ESP32 ↔ real FastAPI ↔ real MongoDB Atlas ↔ real Groq. Network config:

| | |
|---|---|
| Wi-Fi SSID | `Alok` (credentials in `include/secrets.h`, gitignored) |
| Backend host | **192.168.0.105**:8000 (this machine, DHCP) |
| Device | **192.168.0.110**, RSSI −40 to −60 |
| Timezone | `IST-5:30` — read from `Get-TimeZone` |
| Atlas | `cluster0.5fmzadc.mongodb.net`, database **`deskmate`**, MongoDB 8.0.32 |

**Backend against live Atlas: `scripts/selfcheck.py` → ALL 72 CHECKS PASSED.**
Connection, indexes, TTL, CRUD on every collection, timer/stopwatch/Pomodoro
state machines, analytics aggregations, the scheduler firing a real timer, the
HTTP surface, and Groq falling through.

**Device round trip**, serial and API interleaved in one process:

```
  0.4s dev | boot, PSRAM 8189 KB
  2.5s dev | [net] Wi-Fi up, IP 192.168.0.110, RSSI -45
  4.5s dev | [net] websocket connected
  5.0s dev | [net] snapshot adopted
  6.8s dev | [net] <- relay.set (from dashboard)
  9.4s dev | [net] <- pomodoro.started (from dashboard)
 12.0s dev | [net] <- pomodoro.stopped (from dashboard)
 15.9s dev | [net] <- speak (from server)          <- Groq reply, 1.7s round trip
 18.4s dev | [net] <- timer.started (from dashboard)
 24.5s dev | [net] <- timer.finished (from system) <- backend scheduler fired it
```

Worth noting: relay ON was sent at 3.0s while the socket was still down, and the
device picked it up at 5.0s via `snapshot adopted`. Reconcile-on-reconnect works.

**Persisted in Atlas** after the run: 13 collections, `devices` carrying live
telemetry (fw 0.1.0, ip, ssid, rssi, heap, uptime, screen), 29 `device_events`,
6 `chat_messages`, 3 `voice_commands`, TTL index confirmed at 14 days.

### Still not verified — needs eyes and ears on the device

- **Nobody has spoken into the mic on hardware.** The I2S-0 driver installs
  cleanly (`[mic] I2S RX ready on GPIO 4/5/6, 16000 Hz, left slot, 156 KB in
  PSRAM`) and the whole path is proven in pieces — mic framing (`wireframecheck`),
  backend transcription (`voicecheck`), upload (`postVoice`) — but no real capture
  has run end to end. **The single most likely thing to be wrong is
  `MIC_USE_RIGHT_SLOT` in `config.h`:** the ESP32 I2S phase quirk means
  `ONLY_LEFT` sometimes reads the right slot, and picking wrong gives perfect
  silence with no error. `mic.cpp` prints peak + RMS after every capture and warns
  when RMS < 200 to flip the flag. `MIC_GAIN_SHIFT` is the loudness dial after that.
- **Nobody has watched the animations.** The blinking idle face, the open-on-wake
  animation and the eared listening face are flashed and their geometry is
  host-tested, but the actual pixels on the panel are unconfirmed. Needs: does it
  open + blink at random intervals, does a touch drop into the menu, does the
  listening face's brows/ears react to speech.
- **Nobody has looked at the OLED at all.** It acknowledges at 0x3C and U8g2
  initialises, but glyphs, layout and the dim/blank policy are unconfirmed.
- **Nobody has touched the pad or heard the relay/chime.** Polarity is detected,
  I2S is up, and `speak` + `timer.finished` frames arrived (so the chime *should*
  have sounded), but that is inference, not observation. Gestures log to serial as
  `[touch] <gesture> -> screen <name>`.
- **Alarms have not fired.** They need NTP, which now works, but no alarm has been
  scheduled and waited on.
- The dashboard has not been driven against the live Atlas backend in a browser.
- **The Android app was generated and synced but never installed on a handset**
  (needs the SDK and a device).
- Analytics numbers, Pomodoro long-break behaviour over many hours, and NVS wear
  over months are untested by nature.

### Worth remembering from the verification itself

The host tests caught **four wrong expected constants of mine**, not bugs in the
implementation — I'd computed the epoch for `2026-09-22T11:47:31Z` by hand and got
Sep 10. Re-anchored against Python's `datetime`. Lesson: cross-check date
constants against an independent implementation, never derive them by hand.

---

## 11. Open items

### Unresolved user request — the oldest open item

**"keep mobile different and web different"** — the user asked to split the single
dashboard into two separate frontends. A task list was started and then aborted
when the conversation moved to hardware. **Still outstanding**, now the oldest
unfinished request by a wide margin — it has survived the whole firmware, Atlas,
voice and animation work.

The proposed shape, for reference:

- `web/` — desktop-first dashboard
- `mobile/` — phone-first Capacitor app, its own UI
- `shared/` — **protocol only**: `types.ts`, `api.ts`, `ws.ts`, `events.ts`, store.
  Not UI.

The reason for keeping `shared/`: two hand-maintained copies of the sync logic
would drift, and drift there means the device and the app disagree about a timer —
the exact bug this architecture exists to prevent. Everything visible and
touchable would be separate. This was flagged to the user but never confirmed.

### Hardware questions still open

1. **Amp VIN — 5 V or 3V3?** Firmware assumes the 5 V rail. Output power scales
   with the square of supply voltage, so 3.3 V gives ~40%.
2. **Amp SD pin.** Firmware defaults to `AMP_HAS_SD_PIN 1` on GPIO 10 (firmware
   mute). Set to 0 if SD is tied to 3V3.
3. **Battery readings** from B+/B− and OUT+/OUT−, and TP4056 LED behaviour.
4. **MT3608 boost converter now on hand** — Stage 16 unblocked. Still to do:
   trim OUT to 5.0 V on the bench, wire the rail, fit the GPIO 1 divider.
5. **Two-battery goal unresolved.** Series (7.4 V) is unsafe with a single-cell
   TP4056 — it will overcharge the pack. Parallel keeps 3.7 V and the same charger
   works, but needs a holder actually wired parallel and similarly-charged cells
   before first joining them. The choice depends on whether you want runtime or
   peak current.

Resolved since the plan was written:

- **Touch polarity (#4): active-HIGH, factory default.** Measured on the real
  board — idle reads LOW. The firmware auto-detects either way.
- Arduino core version: 2.0.17 via espressif32 6.12.0.
- PSRAM: 8 MB octal confirmed present *and now working* (needed
  `-DBOARD_HAS_PSRAM`).

### "make colour white" — resolved, and why it could not mean the panel

The user asked to "make colour white for all display work." The SH1106 is a
**one-bit monochrome panel**: a pixel is lit or dark, and the module's emission
colour (yours is white) is fixed in the glass. Software cannot change it. So:

- Firmware already draws every pixel white — all rendering is `setDrawColor(1)`.
  A defensive `setDrawColor(1)` was added after every `clearBuffer()` so a screen
  that flips to colour 0 for a knockout effect can't leave the next frame blank.
- The one place that *was* the wrong colour: the **dashboard's OLED mirror**
  (`OledPreview.tsx`) rendered in the green UI accent. Changed to white via a new
  `--color-oled` token in `index.css`. That is the actionable half of the request.

### Config — all set, one fragile bit

Done: `backend/.env` (Atlas URI + Groq key), `include/secrets.h` (Wi-Fi `sachin` +
`BACKEND_HOST=192.168.1.103`), `include/config.h` (`DESKMATE_TZ="IST-5:30"`, plus
the mic + animation tunables added this session).

Still to do: `dashboard/.env.production` → `VITE_API_BASE_URL` for mobile builds.

**Fragile:** `BACKEND_HOST` is hardcoded to a DHCP address. If the router
reassigns 192.168.0.105 the device silently stops linking. A static lease on the
router fixes it permanently; otherwise re-check `ipconfig` and reflash. Symptom in
the serial log: `snapshot HTTP -1`, or `websocket connected` never appearing.

### Secret hygiene — action needed

All three were pasted in plaintext into a chat conversation on 22 Sep 2026 and now
live in gitignored files. **Rotate them:**

| Secret | Where it is | Rotate at |
|---|---|---|
| Groq API key | `backend/.env` | console.groq.com > API Keys |
| Atlas DB password (`23102180_db_user`) | `backend/.env` | Atlas > Database Access |
| Wi-Fi password | `include/secrets.h` | router admin |

A starter task in the DB seed is a reminder about the Groq key.

### Feature gaps

| Gap | Why |
|---|---|
| **TTS (spoken replies)** | The device *shows* the reply and chimes; it does not speak. `POST /api/voice/transcribe` returns the text and the firmware puts it in a notice. Real speech synthesis is still unimplemented — the last piece of Stage 11. |
| **Mic not yet spoken into on hardware** | Capture (Stage 8) and the device voice path (Stage 10) are **built and flashed**; STT via `whisper-large-v3-turbo` is wired. What is missing is one real end-to-end capture — see §10 "not verified" and the `MIC_USE_RIGHT_SLOT` caveat. |
| Alarms can't be created on the device | One button makes time entry impractical. Create on the dashboard; the device mirrors and rings them. |
| Tasks/reminders not listed on the OLED | 128×64 is the wrong surface for a list. Reminders announce themselves as a notice when due. |
| `BATTERY_SENSE_ENABLED 0` | Divider not fitted (Stage 16). |
| On-device timer limited to presets | 5/10/15/25/45 min. Arbitrary durations come from the dashboard. |
| No Alembic migrations | Tables created via `create_all`. Add Alembic before there is data worth keeping. |

---

## 12. Security posture

**The default configuration is unauthenticated** so a clean checkout runs with zero
setup. Fine on localhost, not fine anywhere else. Before port-forwarding,
tunnelling or deploying:

```env
# backend/.env
REQUIRE_AUTH=true
API_KEY=<python -c "import secrets; print(secrets.token_urlsafe(32))">
DEVICE_TOKEN=<another one>
```

Also know:

- Any `VITE_` variable is compiled into the client bundle and readable by anyone
  holding the app or the APK. `VITE_API_KEY` is a shared demo credential, not a
  secret. Per-user auth would need real tokens issued by the backend.
- The Android **debug** build permits cleartext HTTP. Release builds don't.
- `CORS_ALLOW_ALL=true` exists for LAN demos and disables credentialed requests as
  a consequence.
- Gitignored: `backend/.env`, `include/secrets.h`, `dashboard/.env*` (except
  `.env.example`).

---

## 13. Gotchas hit while building this

Recorded so they don't cost time twice.

| Gotcha | Resolution |
|---|---|
| **Backend `tz_offset_minutes` must match firmware `DESKMATE_TZ`** | Alarms are wall-clock and both sides resolve them independently. Mismatch = same alarm fires hours apart. Nothing enforces it. `devtool.py tz 330` for IST |
| **A PlatformIO serial monitor in VS Code holds COM5** | Every upload fails with `PermissionError(13)`. Close the monitor before flashing |
| PowerShell mangles multi-line commands with backticks / nested quotes | Happened 3×. Write a `.py` file and run that — see `scripts/devtool.py` |
| **U8g2 `panel.begin()` hung forever, no output** | The constructor was given clock/data pins, so U8g2 calls `Wire.begin()` itself — and we had already called it to probe. Double-init deadlocks the ESP32 I2C driver. Call `Wire.end()` before `panel.begin()` |
| A stable pin reading does **not** prove a wire is connected | The pull-up test cannot tell "peripheral driving LOW" from "wire shorted to GND". Both read solid LOW |
| **PSRAM reported 0 KB on a chip that has 8 MB** | `memory_type = qio_opi` is necessary but **not sufficient**: Arduino needs `-DBOARD_HAS_PSRAM` too. No error, no warning, just 0 |
| NVS logged `nvs_open failed: NOT_FOUND` twice per boot | Modules opened the shared namespace read-only before anything created it. `storage::begin()` creates it first |
| `getBytesLength()` on a missing blob logs an error | Guard with `prefs.isKey()` first |
| Motor (async Mongo driver) is **EOL since May 2026** | Use PyMongo's `AsyncMongoClient`. `pymongo[srv]` extra no longer exists — install `dnspython` explicitly for `mongodb+srv://` |
| PyMongo async: `find()` returns a cursor, everything else is a coroutine | `find()` is NOT awaited; `aggregate()` and `list_indexes()` ARE. Verified by introspection |
| Pydantic `use_enum_values=True` means fields hold plain strings | Compare enums with `==`, never `is` |
| `llama-3.3-70b-versatile` 404s on a free Groq key | Enterprise-only since mid-2026. Use `openai/gpt-oss-20b`; check `GET /api/ai/models` |
| gpt-oss burns the token budget on reasoning | `reasoning_effort=low` — 5 tokens instead of 109 |
| PowerShell here-strings (`@"..."@`) mangled a multi-line Python command | Write a temp `.py` file and run it instead |
| `npm create vite` hangs on interactive prompts | Scaffolded `package.json` and configs by hand |
| **TypeScript 7 removed `baseUrl`** | Use `paths` only, resolved relative to the tsconfig |
| `pio` not on PATH | `& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe"` |
| FastAPI 0.141 nests routers (`_IncludedRouter`) | `len(app.routes)` shows 8; count `app.openapi()["paths"]` instead |
| SQLite doesn't persist tzinfo | `utils.as_utc()` re-attaches UTC before any comparison — the classic "timer finished instantly" bug |
| Vite `preview` ignores `server.proxy` | Needs its own `preview.proxy` block |
| U8g2 HW I2C pin config on ESP32 | Constructor takes `(rotation, reset, clock, data)`; also `setI2CAddress(0x3C << 1)` |
| Arduino core 2.0.17 = **legacy** `driver/i2s.h` | `i2s_driver_install` / `i2s_write`; assign `i2s_config_t` fields individually rather than using designated initializers |
| Relay clicks on every boot | Write the de-energised level **before** `pinMode(OUTPUT)`, not after |
| Backend broadcasts to the originating client too | Intentional (confirmation + multi-dashboard sync). Test code must drain frames, not assume the next one |
| Hand-computed epoch constants were wrong | Cross-check against Python `datetime` |
| Starlette 1.6 deprecations | `HTTP_422_UNPROCESSABLE_ENTITY` → `..._CONTENT`; `httpx` in testclient wants `httpx2`. Cosmetic only. |
| **edge-tts 403 → TTS silent** | Microsoft periodically changes the `Sec-MS-GEC` token; old `edge-tts` versions break. Fix: `pip install --upgrade edge-tts` (7.2.8 → 7.3.1 this time) |
| **Speaker silent though code ran** | The DIN wire was unplugged. The firmware can't see past the I2S bus — prove the amp with a standalone tone sketch before suspecting code |
| MAX98357 very quiet | VIN on 3V3 instead of 5V. It needs ~5V to drive a speaker |
| **Opening COM5 rebooted the ESP32 mid-command** | The CH343's DTR/RTS are wired to EN/BOOT; asserting them on port-open resets the board. A passive reader must leave both lines de-asserted (`wifi_watch.ps1` does) |
| **Silence auto-stop ran the full ceiling** | A fixed threshold on per-chunk PEAK trips on the INMP441 noise floor. Use smoothed RMS vs a min-follower noise floor instead |
| Mic clipping (peak 32768) garbled Whisper | Gain too high. `MIC_GAIN_SHIFT` 11 → 15. Also discard the first ~150 ms (INMP441 settling burst) |
| **Forcing Whisper `language=en` garbled Hindi** | Leave it empty (auto-detect). Forcing `hi` breaks English the other way |
| Whisper invents words for silence | "Thank you.", "you", "." — reject these stock phrases or they run as commands |
| **`BACKEND_HOST` goes stale on every network change** | 3rd time it killed voice. The device joins Wi-Fi fine then can't reach the backend — looks like firmware, isn't. Needs a static DHCP lease or mDNS |
| Groq JSON mode on small models | `response_format={"type":"json_object"}` can 400 on some models; retry without it (quiz.py does) |

---

## 14. Roadmap position

| Phase | Stage | Status |
|---|---|---|
| A | Hardware validation 1–7 | 6/7 — battery in progress |
| B | 1 OLED foundation | **Done** (screen manager, 7 screens) |
| B | 2 Wi-Fi + NTP clock | **Done** |
| B | 3 Touch interaction | **Done** (3 gestures, auto polarity) |
| B | 4 Timer | **Done** |
| B | 5 Stopwatch | **Done** (with laps) |
| B | 6 Alarm | **Done** (NVS-persisted, dual-owned) |
| B | 7 Pomodoro | **Done** (long-break cycles) |
| C | 8 Audio input (mic) | **Built & flashed** — I2S-0, PSRAM buffer, WAV header, multipart body. Needs first real capture |
| C | 9 Audio output | Partial — chimes work, no TTS speech |
| D | 12 Backend | **Done** |
| D | 13 Database | **Done** |
| D | 15 ESP32 ↔ backend sync | **Done both halves** |
| E | 10 Voice command system | **Built & flashed** — push-to-talk, Arming→Listening→Sending→notice. Needs first real capture |
| E | 11 AI assistant | **Done** — LLM intent understanding with chat memory on both chat and voice; TTS speech working (edge-tts) |
| F | 14 Web dashboard | **Done** (+ mobile app; OLED mirror shows LED screen; Study Notes page) |
| F | 18 Study notes + quiz | **Done (dashboard)** — upload PDF/Word/Excel/text, AI quizzes from the notes. Voice quizzing not wired |
| G | 16 Battery/power | **Unblocked** — MT3608 on hand; trim to 5.0 V, wire rail, fit GPIO 1 divider |
| G | 17 Enclosure | Not started |

---

## 15. Next actions, in order

**Physical verification first — everything unconfirmed is unconfirmed because nobody has looked.**

1. **Look at the device right now.** Touch the pad once to dismiss the face and
   land on Home. You should have seen the eyes open from a 2 px slit and then blink
   irregularly. Confirm: does it open, do the eyes blink, does a touch land on Home
   with a chime?

2. **Test voice — double tap on Home.** You should hear a confirm beep, then see
   the listening face (squinting eyes, brows, ear arcs). Say "set a timer for two
   minutes". Watch for `[mic] captured N bytes, peak P, rms R` in the serial log.
   - **If RMS < 200:** flip `MIC_USE_RIGHT_SLOT` in `include/config.h` (0 → 1),
     reflash, try again. That is the ESP32 I2S slot quirk and the single most
     likely hardware failure.
   - **If RMS is healthy but transcript is empty or wrong:** lower `MIC_GAIN_SHIFT`
     by 1 (more gain) or raise it (less). Currently 11 = 32× gain.
   - **If it works:** a notice should show the transcript and the timer should
     start. Verify in the serial log: `[voice] heard "..." -> intent timer.start`.

3. **Test voice on a non-Home screen.** Tap to Timer, then **hold** the pad. Same
   flow — beep, listening face, speak, THINKING, notice.

4. **Run the serial-log watch tool non-destructively** to see what the animations
   and the mic actually put out without rebooting the device:
   ```powershell
   & "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" tools\boot_log.py COM5 120 --no-reset
   ```

5. **Rotate the three secrets** — they were pasted into a chat conversation and
   live in gitignored files. See §11 "Secret hygiene".

6. **Split web and mobile** into separate frontends — the oldest outstanding
   request. Confirm the `shared/` protocol-core approach or say what shape you want
   instead.

7. **TTS** — the device shows the AI reply as text and chimes; it does not speak.
   That is the last unimplemented piece of Stage 11. Needs either a local I2S audio
   pipeline from a TTS service or espeak on-device.

8. Give this machine a static DHCP lease so `BACKEND_HOST` stops being fragile.

9. Run the dashboard in a browser against the live Atlas backend — the React app
   has not been driven against real data in a browser yet.

10. Confirm the amp VIN rail (5 V or 3V3?) and SD wiring, then set the two
    `config.h` flags.

11. MT3608 on hand — set it to 5.0 V on the bench (IN from the cell, OUT open,
    meter OUT+/OUT−, trim the pot), then wire OUT into the 5 V rail. Stage 16
    unblocked.

12. Fit the battery divider on GPIO 1 and set `BATTERY_SENSE_ENABLED 1`.

---

## 16. Session log & timeline

Chronological record so progress is trackable and nothing has to be rediscovered.
Newest last.

### 22 Sep 2026 — planning and the software stack

| # | What | Outcome |
|---|---|---|
| 1 | Saved the project plan verbatim | `docs/AI-DeskMate-Project-Reference.md` |
| 2 | Built the backend (FastAPI, SQLite at the time) | 45 endpoints, full smoke test passed |
| 3 | Built the dashboard (React 19 + Vite + Tailwind v4) | 11 pages, typechecks clean, 109 kB gzipped |
| 4 | Added Capacitor 8, generated the Android project | `cap sync` clean; APK never installed on a handset |
| 5 | Wrote `memory.md` | this file |
| 6 | Documented complete hardware wiring + SVG diagram | 24 wires, power topology, current budget |

**Deferred and still open from this day:** the user asked to *"keep mobile
different and web different"* — split the single dashboard into separate `web/` and
`mobile/` apps over a protocol-only `shared/` core. Work was started, then the
conversation moved to hardware. **Never completed.** See §11.

### 22 Sep 2026 — firmware written

| # | What | Outcome |
|---|---|---|
| 7 | ESP32-S3 firmware, Stages 1–7 + Stage 15 sync | 13 sources, 15 headers, 0 warnings under `-Wall` |
| 8 | Extracted ISO-8601 date maths to a host-testable header | 29 host tests pass |
| 9 | Replayed every firmware frame against the backend | 59 contract checks pass |

Note from step 8: the host tests caught **four wrong expected constants of mine**,
not bugs in the code. I had computed the epoch for 2026-09-22 by hand and got
Sep 10. Lesson recorded in §13 — cross-check date constants against an
independent implementation.

### 22 Sep 2026 — backend migrated to MongoDB Atlas + Groq

| # | What | Outcome |
|---|---|---|
| 10 | Replaced SQLite/SQLModel with MongoDB Atlas (PyMongo async) | Motor is EOL since May 2026 |
| 11 | Replaced the OpenAI path with GroqCloud | `openai/gpt-oss-20b` |
| 12 | Probed the live Groq API before committing to a model | Found Llama 3.3 70B is Enterprise-only and would 404 |
| 13 | Measured `reasoning_effort` | default = 109 reasoning tokens / 220 ms; `low` = 5 / 85 ms |
| 14 | Wrote `scripts/selfcheck.py` | because no Mongo server was available to test against |

### 22 Sep 2026 — first flash to real hardware

Board confirmed as **N16R8** via esptool: ESP32-S3 QFN56 rev v0.2, 16 MB flash,
8 MB embedded octal PSRAM, MAC `ac:a7:04:12:66:74`. Serial is a **WCH CH343 on
COM5**, a separate USB-UART chip — so the `ARDUINO_USB_MODE` flags stay off.

Three bugs that only hardware could reveal:

1. **Hung in `setup()` with no output.** U8g2's constructor takes the I2C pins, so
   `panel.begin()` calls `Wire.begin()` — on a bus `display::begin()` had already
   initialised to probe for the panel. Double-init deadlocks the ESP32 I2C driver.
   Fixed with `Wire.end()` before handing the bus over. `display::begin()` now
   returns bool and the firmware runs headless if no panel answers.
2. **PSRAM reported 0 KB.** `memory_type = qio_opi` is necessary but not
   sufficient — Arduino only brings PSRAM up with `-DBOARD_HAS_PSRAM`. No error,
   no warning. Now reports 8189 KB.
3. **NVS logged `nvs_open failed: NOT_FOUND` twice per boot.** Modules opened the
   shared namespace read-only before anything created it. Added `storage::begin()`.

Also resolved outstanding hardware question #4: **touch is active-HIGH, factory
default** (idle reads LOW).

### 22 Sep 2026 — full stack live

Wi-Fi (`Alok`), Atlas URI and Groq key all wired in. Results:

- `scripts/selfcheck.py` against live Atlas: **all 72 checks passed**
- Device round trip verified with serial and API interleaved — see §10
- Reconcile-on-reconnect proven: a relay command sent while the socket was down
  was picked up via `snapshot adopted`
- `timer.finished` arrived `from system`, i.e. the backend scheduler fired it
  independently from the stored `ends_at` while the firmware stayed quiet
- Found and fixed: `CommandSource` had no `device` member, so device-originated
  events were logged as `system`

### 25 Sep 2026 — network change, then the touch saga

**Wi-Fi moved from `Alok` to `sachin`.** Two things were wrong, not one:

1. Password had a stray `@` (`popper@99300` → `popper99300`)
2. **The subnet changed too**: this machine went `192.168.0.105` → `192.168.1.103`,
   so `BACKEND_HOST` was stale. The device would have joined Wi-Fi perfectly and
   then silently never reached the backend — looks like a firmware fault, isn't.

Added Wi-Fi disconnect-reason logging rather than guessing at the cause:

```
[net] association failed: reason 15 — 4WAY_HANDSHAKE_TIMEOUT (wrong password)
```

This separates a wrong key (`15`, `202`, `204`) from an SSID that cannot be seen
(`201 NO_AP_FOUND`), which are indistinguishable from the outside.

**Touch not working.** Diagnosed in stages rather than guessing:

| Step | Finding |
|---|---|
| Traced the raw pin | Rock-stable LOW, not floating, not noisy |
| Pull-up / pull-down test | Something actively drives it LOW — so powered and connected |
| Built `DIAGNOSTIC_MODE` | Separates "OLED not drawing" from "pad not sensing" from "gesture logic wrong" |
| Root cause | **Resolved by the user.** Touch now works. |

Correction recorded: the pull-up test is weaker than I first claimed — it cannot
distinguish the TTP223 driving low from the OUT wire being **shorted to GND**.
Both read a solid LOW.

Also learned: **a PlatformIO serial monitor open in VS Code holds COM5 and blocks
every upload** with `PermissionError(13)`. Close it before flashing.

### 25 Sep 2026 — touch mode testing (current)

- `DIAGNOSTIC_MODE 0`, `TOUCH_DEBUG 0` — back to the normal UI
- **Fixed a real UX flaw I had flagged:** `display::wake()` used to swallow the
  gesture whenever the panel was dimmed *or* blanked. Now only a **blanked** panel
  swallows it. A dimmed panel is still legible, so swallowing there just made the
  device feel broken — you tap and nothing happens for no visible reason.
- Added a one-line-per-gesture **test transcript** to serial: screen, timer,
  Pomodoro, stopwatch, relay and alarm count in a single line, so every mode is
  verifiable without reading the 128×64 panel.

**Confirmed working:** tap cycles screens.

```
[touch] tap  screen=timer      | timer=idle 600s | pomo=idle/idle 1500s | sw=idle 0ms/0 | relay=off
[touch] tap  screen=stopwatch  | ...
[touch] tap  screen=pomodoro   | ...
[touch] tap  screen=alarms     | ...
```

**Added `backend/scripts/devtool.py`** — a CLI for driving the backend during
testing, because PowerShell quoting mangled multi-line `Invoke-WebRequest` calls
three times in a row. It reads `BACKEND_HOST` from the firmware's own
`include/secrets.h`, so the tool and the device can never disagree about where
the backend is:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\devtool.py status
.\.venv\Scripts\python.exe scripts\devtool.py alarms --clear --seed
.\.venv\Scripts\python.exe scripts\devtool.py timer 10
.\.venv\Scripts\python.exe scripts\devtool.py relay on
.\.venv\Scripts\python.exe scripts\devtool.py watch 60     # stream device events
```

**Found a real config bug while seeding alarms.** The backend's
`tz_offset_minutes` setting still defaulted to **0 (UTC)** while the firmware runs
`DESKMATE_TZ="IST-5:30"`. Alarms are wall-clock, and the backend and the device
each resolve "07:30" to an absolute instant *independently* — so the same alarm
would have fired **5.5 hours apart** on the two sides. That would have looked like
a scheduling bug and been a config mismatch.

Fixed with `devtool.py tz 330`. Verify by checking `next_trigger_at`:
07:30 IST must resolve to `02:00Z`, and 21:15 IST to `15:45Z`.

**This is a standing trap:** `DESKMATE_TZ` in `config.h` and
`tz_offset_minutes` in the backend settings must always agree. Nothing enforces
it. Changing one without the other silently desynchronises every alarm.

Alarm sync to the device confirmed on reconnect:

```
[net] snapshot adopted: timer=running alarms=2 relay=on
```

### Touch mode test checklist — fill in as verified

Gesture model: **tap** = next screen · **double tap** = primary action ·
**hold ≥900 ms** = secondary action.

| Screen | Gesture | Expected | Status |
|---|---|---|---|
| any | tap | next screen in the cycle | ✅ confirmed |
| Home | double tap | jump to Timer | ☐ |
| Timer | double tap | start the 10 min preset, then pause/resume | ☐ |
| Timer | hold (idle) | cycle preset 5→10→15→25→45 min | ☐ |
| Timer | hold (running) | cancel the timer | ☐ |
| Stopwatch | double tap | start, then stop | ☐ |
| Stopwatch | hold (running) | record a lap | ☐ |
| Stopwatch | hold (stopped) | reset to zero | ☐ |
| Pomodoro | double tap | start focus, then pause/resume | ☐ |
| Pomodoro | hold (running) | skip to the next phase | ☐ |
| Pomodoro | hold (idle) | reset the cycle count | ☐ |
| Alarms | double tap | move the cursor to the next alarm | ☐ |
| Alarms | hold | toggle the selected alarm on/off | ☐ |
| LED (relay) | double tap | relay clicks, LED toggles, screen shows LED ON/OFF | ☐ |
| any | voice "turn on/off the light" | relay + LED follow the command | ☐ |
| Network | double tap | force a reconnect | ☐ |
| Network | hold | re-fetch the snapshot | ☐ |
| — | timer reaching 00:00 | chime + `TIMER DONE` notice | ☐ |
| — | blanked panel (10 min idle) | first tap wakes only, does not act | ☐ |

Alarms need at least one alarm to exist — create it from the dashboard or the API,
since one button cannot practically enter a time.

### Next up after touch: voice control

This section is superseded. The voice work happened — see the entries below.

### Session — weather, voice backend, animations, mic capture, listening face

This is a single long session that ran across multiple conversation windows. The
context summary at the top of each window gave a starting point; the work is
recorded here in the order it happened.

#### Task list agreed at the start

Nine tasks were written before touching any code:

| # | Task |
|---|---|
| 1 | Remove all test/diagnostic scaffolding from `main.cpp` and `touch.cpp` |
| 2 | Weather: backend endpoint + firmware display screen |
| 3 | Voice pipeline: backend STT endpoint + `voicecheck.py` verification |
| 4 | Firmware animations module: eye-open wake, waveform |
| 5 | White rendering (OLED mirror on dashboard) |
| 6 | Firmware weather screen |
| 7 | Mic capture: I2S-0, PSRAM, WAV, multipart upload |
| 8 | Voice screen: listening/thinking faces + push-to-talk gesture map |
| 9 | Flash, verify, update `memory.md` |

#### Task 1 — test scaffolding removed

Removed the three-phase gesture test transcript from `main.cpp` and the raw-touch
debug block from `touch.cpp`. The per-gesture `[touch]` serial line stays; the
bulk transcript of every service state on every tap was the test code.

#### Task 2 — weather feature verified live

| What | Detail |
|---|---|
| Weather provider | **Open-Meteo** (no API key, no account). Rejected OpenWeatherMap — the user has no key for it |
| Backend files | `app/services/weather.py`, `app/api/weather.py`, `WeatherRead` in `schemas.py`, `WEATHER_UPDATED` in `events.py` |
| Backend behaviour | Stale-on-failure: if Open-Meteo is unreachable, the last reading is returned with `stale: true` rather than a 502 |
| Verified live | Delhi 32.6 °C, `description: "Clear sky"`. Cold-cache round trip 2407 ms, warm-cache 15 ms |
| Intent coverage | 4 weather phrasings all route to `weather.query` intent |

Open-Meteo returns **local wall-clock times** plus `utc_offset_seconds` (not UTC).
Errors come as `{"reason": "...", "error": true}` with HTTP 400.

#### Task 3 — voice backend pipeline verified live

| What | Detail |
|---|---|
| Backend path | `POST /api/voice/transcribe` in `app/api/chat.py` |
| Transcription | `ai_service.transcribe()` using `whisper-large-v3-turbo` on the existing Groq key |
| Whisper quirks | Returns text with a **leading space** on almost every result; digits spelled out ("ten"→"10"); `response_format=verbose_json` gives `{text, duration, language, segments}`. Errors: 404 `model_not_found`, 400 `empty_audio_file`. Latency 400–760 ms |
| End-to-end latency | Total 430–1850 ms |
| Fixture tool | `backend/scripts/make_test_speech.ps1` — uses Windows SAPI to synthesise the 4 test sentences into 16 kHz mono WAVs |
| Verification | `backend/scripts/voicecheck.py` — 4 SAPI-speech WAVs, each reaching the right intent AND the action really happening. A spoken timer created a real 600 s timer. A spoken relay command physically switched the relay. `voicecheck.py` passes from `scripts/` |
| Schema | `TranscriptionRead`, `VOICE_TRANSCRIBED` event |

The Arming stage exists for one reason: the confirm chime plays through a speaker
~4 cm from the mic. Recording through it puts a 1.4 kHz beep at the front of every
clip which Whisper occasionally transcribes as a word. A ~35 ms wait for the chime
to finish is invisible to the user and keeps the audible cue.

#### Task 4 — animations module (eye geometry)

Wrote `include/animations.h`, `src/animations.cpp`, `include/eye_geometry.h`.

**The idle face** (blinking eyes) is a port of
[intellar/oled_eye_display](https://github.com/intellar/oled_eye_display)
(MIT, © 2024 Intellar). A snapshot of the upstream sketch and its licence lives in
`vendor/oled_eye_display/`. What was taken verbatim: the geometry — twin 40×40
rounded rects, 10 px apart, corner radius shrinking as the lid closes so a nearly
shut eye is a flat bar rather than a lozenge, and the blink that squeezes the eyes
to 4 px tall while bulging them to 49 px wide. What was rewritten: their
`wakeup()` and `blink()` are blocking `for`-loops paced by the I2C write. The
firmware's loop also services the WebSocket, fires timer deadlines and clocks out
chime samples, so every pose is derived from `monotonicMs()` and each call returns
immediately.

The pure arithmetic was extracted to `include/eye_geometry.h` (no Arduino, no
U8g2) so `test/host/test_eye_geometry.cpp` can check every frame on the PC. That
test now covers opening, blinking, and the listening-face poses — 54 checks total.

**The blink clock** is shared between the idle and listening faces. One clock, two
poses, so the blink looks the same in both rather than being two slightly different
animations.

**The idle face is a resting state**, not a transition. It persists until any
touch. Any touch spends itself dismissing the face and landing on Home — a double
tap that dismissed the face *and* started a timer would fire something the user
couldn't see the state of when they touched.

**`show()` and `showByName()` both dismiss the face** — otherwise a screen pushed
from the dashboard to a resting device changes nothing visible and looks like a
dropped command.

**`drawFace()` skips `sendBuffer()` when the frame has not changed.** Height and
width fully determine a pose; between blinks the comparison is exact, so an idle
face costs no I2C traffic for the ~4 seconds between blinks.

**The `animating()` flag** tells the main loop to poll at `ANIMATION_FPS` (25)
instead of `DISPLAY_FPS` (10) while a face is up. Paying for the faster rate only
while it buys something keeps the idle case cheap.

Config constants added to `include/config.h`:

| Constant | Value | What it is |
|---|---|---|
| `WAKE_OPEN_MS` | 420 | lid ramp from 2 px to 40 px |
| `BLINK_DURATION_MS` | 180 | one blink, lid down and back |
| `BLINK_MIN_GAP_MS` | 2200 | shortest inter-blink pause |
| `BLINK_MAX_GAP_MS` | 5200 | longest inter-blink pause |
| `ANIMATION_FPS` | 25 | panel maximum (a 1 KB I2C frame costs ~23 ms) |
| `WAVEFORM_BARS` | 24 → removed | replaced by the eared face |
| `EAR_RIPPLE_STEP_MS` | 120 | how fast the ear arcs walk outward |

#### Task 5 — white rendering (dashboard OLED mirror)

The SH1106 is a one-bit panel; software cannot change its emission colour. All
firmware rendering already uses `setDrawColor(1)`.

The actionable half: `dashboard/src/components/OledPreview.tsx` was rendering
in the green UI accent (`--color-accent`). Changed to a new `--color-oled: #ffffff`
token in `index.css`. Every `text-accent/` class in `OledPreview.tsx` was
replaced with `text-oled/`. The rest of the dashboard keeps its green accent.

#### Task 6 — weather screen (not built as a separate screen)

Weather data is accessible via voice command ("what's the weather?") and surfaced
as a notice on the existing Home screen. A dedicated 8th screen was discussed but
deferred — the current screen cycle is already 7 deep, and weather changes slowly
enough that a voice query is a better fit than a persistent tile.

If a dedicated screen is wanted later: `GET /api/weather` is ready, and the
firmware HTTP pattern (`HTTPClient`, same as `fetchSnapshot`) is established.

#### Task 7 — mic capture (`include/mic.h`, `src/mic.cpp`)

| What | Detail |
|---|---|
| Hardware | INMP441, I2S peripheral 0, GPIO 4 BCLK / 5 WS / 6 DOUT |
| Format | 16 kHz mono 16-bit PCM, matching what Whisper documents |
| I2S bus width | 32-bit (INMP441 is 24-bit left-justified in a 32-bit slot) |
| Slot | `MIC_USE_RIGHT_SLOT 0` → `ONLY_LEFT`. **Flip to 1 if RMS < 200** (ESP32 I2S phase quirk) |
| Gain | `MIC_GAIN_SHIFT 11` = right-shift from 32 to 16, net 32× headroom gain. Clamp rather than wrap to prevent sign-flip clicks |
| DC blocker | One-pole IIR high-pass, τ ≈ 40 ms at 16 kHz, removes INMP441 standing offset |
| PSRAM | 156 KB `ps_malloc` for the entire request body. Internal RAM would be ~half the heap |
| Buffer layout | `[preamble][44-byte WAV header][PCM ...][epilogue]` in one allocation so the DMA writes PCM straight to its final address — no 160 KB copy |
| WAV header | Written at capture end (two fields are byte counts not known until then). Getting those wrong is the classic way to make a file that plays locally but a stricter decoder rejects |
| Duration | 5 s (`VOICE_RECORD_SECONDS`). Non-blocking: `update()` drains DMA with zero timeout every loop |
| Level feed | `animations::pushAudioLevel()` once per DMA drain chunk (~16 ms), feeding the listening face |

Two bugs caught before flashing:
- `snprintf` was planting a NUL one byte past the allocation at full recording length.
- The RMS accumulator was `uint32_t` summing 16-bit squares over 80,000 samples — overflows by 4 orders of magnitude. Changed to `uint64_t`.

Verification: `backend/scripts/wireframecheck.py` rebuilds the firmware's
multipart body byte-for-byte, wraps a known-good WAV in it, and POSTs it as a raw
body so FastAPI sees exactly what the ESP32 sends. **15 checks pass.** HTTP 200,
`transcript: 'Set a timer for 10 minutes.'`, `intent: timer.start`, server
received exactly the bytes sent. A voice failure on device is now provably the
audio, not the envelope.

The script also reads `BOUNDARY` and `MIC_SAMPLE_RATE` directly from the firmware
source so it can never drift from what the device actually sends.

#### Task 8 — voice state machine and listening face

**`include/voice.h`, `src/voice.cpp`** — the push-to-talk orchestrator:

```
start() → Arming → Listening → Sending → (shows notice)
                                            │
                                            └→ Idle
```

- **Arming**: waits for the confirm chime to stop (~35 ms) so the beep is not
  recorded. Falls back after `ARM_TIMEOUT_MS` if the chime driver is stuck.
- **Listening**: calls `mic::update()` every loop. When `mic::capturing()` goes
  false it pushes the THINKING frame to the panel and blocks on `postVoice()`.
- **Sending**: `netLink::postVoice()` is the blocking call (430–1850 ms). Draws
  THINKING *before* it starts.

Any touch mid-recording aborts with an error chime. The gesture is consumed.

**`netLink::postVoice()`** added to `src/net_link.cpp` and `include/net_link.h`.
Returns a `VoiceResult` struct. Strips the leading space from Whisper's transcript.
Logs the heard text, intent and action. Times out at 20 s (generous: Whisper +
LLM is the slowest thing on the device).

**Gesture map** (user specified: 2x tap on Home, hold everywhere else):

| Gesture | Home | Other screens |
|---|---|---|
| tap | next screen | next screen |
| double tap | **mic start** | primary action |
| hold | (unassigned) | **mic start** |

Cost recorded: hold was previously the secondary action on every screen.
Timer-cancel, stopwatch-lap, Pomodoro-skip, alarm-toggle and network-resync are
now dashboard-only and reachable by voice.

**The listening face** replaced the bar waveform. Reasoning: a waveform is an
instrument; the device needs to look like it's paying attention, not measuring.
The eared face (squinting eyes sitting 4 px lower, brows that lift with loudness,
concentric arc ears that fill inside-out) reads correctly from across a desk.

Ear design: two independent reasons OR'd together. A ripple index walks outward on
a 120 ms timer with a rest beat (so a silent room still moves); loudness fills from
the inside out (so speaking actually changes the display). Without the ripple,
silence looks frozen. Without loudness, the ears ignore what they're showing.

Level smoothing: fast attack (α=0.55), slow release (α=0.08). Raw per-chunk peaks
jitter hard enough to make brows buzz; this tracks syllables without vibrating.

The bottom edge carries a bare 2 px shrinking rule as the 5 seconds run out — no
frame, no digits, just "how much longer".

**Host test additions** (`test_eye_geometry.cpp`):
- `eyesListening()` and `eyesBlinking()` at the listening height are swept across
  512 t values, every frame checked on-panel, mirrored, and inside U8g2's contract.
- Ear/eye clearance asserted: the ears' widest arc must not reach the eye box.
  Without this check, a geometry tweak silently merges them into a blob.
- Brow baseline, lift, top-of-eye clearance, width vs. eye width.
- Silence animates the ears (ripple). Rest beat is genuinely empty. Loud fills all.
- Listening-blink starts and ends on the open listening pose (no jump in or out).

ASCII `--listening` renderer added so the composition can be judged before
flashing. Frames are printed two panel rows per terminal line to preserve the 2:1
aspect.

#### Build and flash state at the end of this session

```
[boot] [mic] I2S RX ready on GPIO 4/5/6, 16000 Hz, left slot, 156 KB in PSRAM
[net] Wi-Fi up, IP 192.168.1.105, RSSI -43/-46
[net] websocket connected
[net] snapshot adopted: timer=none alarms=2 relay=on/off
```

RAM: **15.6%** (51,024 / 327,680 B)  
Flash: **15.6%** (1,021,601 / 6,553,600 B)  
The +156 KB for the recording lives in PSRAM; internal RAM grew by only ~1.3 KB.

#### What was NOT done / still open from this session

| Item | Status |
|---|---|
| Nobody has spoken into the mic on real hardware | The whole pipeline is code-proven, but `[mic] captured` has never been printed from a real voice |
| Nobody has watched the animations | Flashed, geometry-tested, ASCII-rendered, but the real panel is unobserved |
| Firmware weather screen as a dedicated 8th screen | Deferred — voice query works, a tile seems unnecessary |
| TTS (device speaks the reply) | Still shows text + chimes |
| Web/mobile dashboard split | Still the oldest outstanding request |
| Touch mode checklist from the previous session | Still mostly unchecked |


### Session — LED light on the relay + on-screen button

The relay now drives an **LED light**, and the device grew a proper on-screen
button for it.

| # | What | Detail |
|---|---|---|
| 1 | Verified relay hardware with a throwaway test | A standalone `test_relay/relay_test.cpp` + `[env:relay-test]` was flashed; serial confirmed GPIO 13 toggling (ON→LOW, OFF→HIGH) once a second, active-LOW as configured. **Both the test file and the env were deleted afterward** — they were scaffolding, not part of the firmware. |
| 2 | LED is the relay's switched load | Wiring documented across all four MD files: `+5V → COM`, `NO → LED(+)` via ~220 Ω, `LED(-) → GND`. NO keeps the LED off while idle. |
| 3 | Brought the LED (relay) screen into the tap cycle | `screens.cpp next()` previously skipped from Reminders straight past Relay and Network (`index >= Relay → 0`). Changed to `index >= Network → 0`, so Relay is now reachable by touch and Network stays dashboard-only. Without this the on-screen toggle was unreachable by finger — only the dashboard could switch it. |
| 4 | Redrew the screen as a light button | `drawRelay()` now shows `LED ON`/`LED OFF` with a lamp glyph (filled + rays when on, hollow when off) and a `2x tap to toggle` hint. Screen title is `LED`. |
| 5 | Voice already worked | No backend change needed. The intent parser's `_RELAY_WORDS` already covers "light"/"lamp": "turn on the light" → `relay.on`, "light off" → `relay.off`, executed and broadcast to the device, which calls `relay::applyRemote()`. |

Build after the changes: **RAM 16.3%, Flash 15.7%**, 0 warnings. **Not flashed**
this session on request — files only. Reflash with `pio run -e esp32-s3 -t upload`
when ready.

Three control paths now share the one NVS-persisted relay state: on-screen
double-tap, voice, and dashboard.

### Session — MT3608 boost converter acquired (docs only)

The MT3608 adjustable step-up module — the missing piece that has blocked Stage 16
(battery) since the start — is now on hand. No code or hardware change this
session; the four MD files were updated to reflect it:

- **Wiring**: `TP4056 OUT+ → MT3608 IN+`, `TP4056 OUT- → MT3608 IN-`,
  `MT3608 OUT+ → ESP32 5V/VIN + MAX98357 VIN + relay VCC`, `MT3608 OUT- → common GND`.
- **Safety**: set OUT to **5.0 V with a multimeter before wiring OUT to anything** —
  the pot ships at a random position and can emit 20 V+. Also do not dual-source
  5 V (USB + boost) unless a Schottky diode isolates VBUS from the 5V header.
- **Status moves**: Test 7 and roadmap Stage 16 go from "blocked, needs MT3608" to
  "unblocked, on hand". Remaining Stage-16 steps: trim to 5.0 V → wire the rail →
  fit the GPIO 1 battery divider → set `BATTERY_SENSE_ENABLED 1`.

Files touched: `README.md`, `docs/FIRMWARE.md`,
`docs/AI-DeskMate-Project-Reference.md` (component table #13, Section 3 wiring,
Section 7 power architecture, Test 7), `memory.md` (wiring, power section,
outstanding items, roadmap, next actions).


### Session — TTS fixed, amp wiring, voice tuning (hardware brought online)

A long hands-on session that got the device actually talking and listening.
Mostly backend + firmware config; the one firmware logic change was the mic.

**TTS was returning 502 — edge-tts out of date.** The device showed the AI reply
as text but the speaker was silent. Root cause was NOT the device: Microsoft Edge
TTS rejected the handshake with `403` because the installed `edge-tts` 7.2.8 sent
an outdated `Sec-MS-GEC` token. Upgraded to **7.3.1** and speech synthesis works
(verified: a test phrase returned a 109 KB WAV). This recurs whenever Microsoft
changes the token scheme — the fix is always `pip install --upgrade edge-tts`.

**Speaker was silent — the DIN wire was unplugged.** Proven with a throwaway
`test_amp` sketch that played a loud 1 kHz tone. No sound → it was wiring, not
code. Also set `AMP_HAS_SD_PIN 0` in `config.h`: the amp's SD is hardwired to
3V3 (always-on), so the firmware must not drive a GPIO as SD. Both the amp test
and the earlier relay test were deleted after use.

**Amp wiring confirmed:** VIN should be **5V** (3V3 is very quiet), SD → 3V3,
BCLK 15 / LRC 16 / DIN 7, speaker on the two output pads only (bridge-tied amp —
never ground a speaker lead).

**Mic / voice capture — turned a fixed 5 s recording into talk-until-you-stop.**
Changes in `config.h` + `mic.cpp`:
- `VOICE_RECORD_SECONDS` is now a **ceiling** (20 s, 625 KB PSRAM buffer), not the
  normal stop. The clip ends when the user stops talking.
- **Silence auto-stop** (`mic.cpp`): adaptive. It tracks a smoothed RMS and a
  continuously-updated noise floor (min-follower), and ends ~1.2 s after the
  level falls back toward that floor. The first attempt used a fixed threshold on
  per-chunk peak, which the INMP441 noise floor tripped constantly so it ran the
  full ceiling every time; and a max-hold floor learned the user's voice as the
  floor. The min-follower fixed both.
- **Mic gain dropped 11 → 15** (`MIC_GAIN_SHIFT`). At 11 real speech hit peak
  32768 (hard clipping) and rms ~17000; clipping was making Whisper mis-hear.
- **Warm-up discard** (`MIC_WARMUP_MS 150`): the INMP441 emits a large settling
  burst for ~80–100 ms after its clock starts. That burst was recorded and
  counted as "speech started", ending clips early. The first 150 ms now only
  trains the DC blocker.
- **Onset hold** (`VOICE_ONSET_HOLD_MS 120`): sound must stay above threshold
  120 ms to count as speech, so a click or desk bump does not start the clip.

**Tooling added:** `tools/wifi_watch.ps1` (passive serial read that does NOT
pulse DTR/RTS, so opening the port no longer reboots the CH343-connected board;
`-Reset` opts into a reboot) and `tools/serial_logger.ps1` (background logger to
a file). A `VOICE_DEBUG_DIR` setting saves the last 20 device recordings for
quality analysis — gitignored, contains the user's voice, off by default.

**Confirmed working on real hardware this session:** OLED, Wi-Fi, backend
WebSocket, mic capture with real speech, Whisper transcription, TTS playback
through the speaker, the relay/LED. The device is fully alive.

### Session — Hindi / Hinglish voice commands

Backend-only (`intents.py`, `ai.py`, `config.py`, `.env`). No reflash — voice
flows through the same parser.

- **Language detection:** `GROQ_TRANSCRIBE_LANGUAGE` was forcing `en`, which
  garbled Hindi. Now empty (auto-detect). Forcing `hi` would break English, so
  auto is correct.
- **Hindi → English rewrite** (`normalize_hindi` in `intents.py`): a step that
  turns Hindi command words into the English the existing rules already handle.
  "light chalu karo" → "light on", "paanch minute ka timer lagao" → "5 minutes
  timer", "subah 7 baje" → "7:00 am". Handles both Devanagari and Roman (Hinglish)
  script. One rule set serves both languages.
- Includes the misspellings Whisper actually produced in testing (ताइमर, चालो,
  बुजा, मिनिट, "स्टॉप वाट", साथ for सात).
- **Urdu-script fallback:** short Hindi clips sometimes come back as Urdu in
  Arabic script, which nothing can read; the backend re-asks Whisper with Hindi
  forced in that case.
- **Silence/noise rejection:** Whisper invents words for silence ("Thank you.",
  "you", ".") and could run them as commands. Those stock phrases are now rejected
  with a spoken "No clear speech heard".
- Verified by synthesising Hindi speech with two Hindi voices and sending it
  through the voice endpoint: timer, light, alarm, stopwatch, weather, time all
  classify correctly in both languages.

### Session — LED command phrasings + conversational task memory

Backend-only (`intents.py`, `executor.py`, `ai.py`, `conversation.py`).

**"LED" and more light phrasings.** The parser only matched a few exact nouns
("light", "lamp", "bulb") right next to "on/off". It missed "turn on the LED",
"lights off", "shut off the light", "toggle the light". Rewrote the relay rule
(`_relay_intent`) to accept any light word (incl. LED/LEDs, and the spellings
Whisper writes for a spoken LED: "L.E.D.", "lead", "LID", एलईडी) + any on/off/
toggle word in any order. Added a real `relay.toggle` intent. Reminders like
"remind me to turn off the light at 9 pm" stay reminders, and "what is a light
year" stays chat. Replies now say "Light turned on/off."

**Conversational memory for tasks** (`conversation.py`, new). The regex parser is
stateless, so "add a task buy milk" then "remove the last task" / "delete it" /
"mark it done" had nothing to resolve against. Added a tiny per-device in-memory
store of the last thing created/acted on (3-minute TTL). The parser detects
references ("the last", "it", "that one") — but only paired with an action verb,
so "what time is it" is left alone — and the executor resolves them to the actual
task. Added a real `task.delete` command (only `task.complete` existed before).
Verified end to end: create → "remove the last task" removes the right one.

### Session — LLM understands free-form speech, with memory (Stage 11 done)

The big one. Backend-only (`ai.py`, `api/chat.py`, `intents.py`). Works on both
dashboard chat and device voice because they share the `_handle` pipeline.

**Before:** regex parser → if no match, a plain chat reply that did nothing.
**Now:** regex parser (fast, free, offline) → if no match, an **LLM intent layer**
reads the transcript + last 8 messages and, via Groq tool-calling, maps free-form
speech onto a real device action, run through the same executor. If it is genuine
chit-chat, it just replies.

Examples that now work: "it's dark in here" → light on; "too bright" → light off;
"I need to focus for a while" → Pomodoro; "wake me at half past six" → alarm
06:30; "wake me in 20 minutes" → reminder (relative, not an alarm); "add a task
… / actually scrap that" → create then delete. The regex fast path still answers
common fixed commands in ~350 ms with no LLM call.

Design: `resolve_intent()` in `ai.py` uses a `control_device` tool whose enum is
kept in lock-step with `executor.execute()`. Temperature 0.2 (classification, not
prose). Never raises — any failure degrades to a chat reply so the device always
responds. Also fixed a parser bug this surfaced: "wake me in N minutes" was being
caught by the regex alarm rule and dead-ending at "here are your alarms"; relative
wake-ups now fall through to the LLM and become reminders.

**Also this session:** the assistant intro no longer names a creator (system
prompt in `ai.py` was forcing "I was created by Alok Gupta"); it now just
introduces itself as DeskBuddy. Backend-only.

### Session — recurring backend-IP trap, voice failed

`secrets.h` `BACKEND_HOST` was stale after a network change (`10.121.221.80` while
the machine was back on `192.168.0.109` / "Alok"). The device joined Wi-Fi but
could not reach the backend, so every voice command failed. Fixed the IP and
reflashed. **This is the third time an IP change has broken voice.** Standing
fixes offered but not yet done: a static DHCP lease, or mDNS so the firmware finds
the backend by name instead of a hardcoded IP. Confirmed the device's voice path
already uses the full LLM + memory pipeline (shared `_handle`), so no voice-side
code change was needed.

### Session — Study Notes + AI quiz (exam prep) — NEW FEATURE

Upload study files, the AI quizzes you on them. **Dashboard + backend; no
firmware change.** Verified end to end against the live backend.

**Backend (new):**
- `services/extract.py` — extracts text in memory from PDF (`pypdf`), Word
  (`python-docx`), Excel (`openpyxl`), and txt/md/csv (stdlib). Only the text is
  stored, never the file — same approach as the voice upload. Clear errors for
  scanned PDFs (no OCR), password-protected files, unsupported types (.doc,
  .pptx). New pinned deps: `pypdf==5.1.0`, `openpyxl==3.1.5`, `python-docx==1.1.2`.
- `services/quiz.py` — generates questions grounded strictly in the note text and
  grades free-form answers leniently (synonyms, partial credit, 0..1 score), both
  via Groq JSON mode. Does NOT reuse `ai.complete()` (whose prompt forces 2-
  sentence spoken replies). Degrades safely: empty list / neutral grade on
  failure, and an offline exact-match grader.
- `api/notes.py` — `POST /api/notes/upload` (multipart UploadFile), list/get/
  delete notes, `POST /api/quiz/start`, `GET /api/quiz/{id}`, `POST
  /api/quiz/{id}/answer`. Reference answers are withheld until a question is
  graded, so the API cannot leak upcoming answers.
- New `Note` and `QuizSession` models (QuizSession embeds its questions), two
  Mongo collections (`notes`, `quiz_sessions`) with indexes, schemas, serializers,
  events (`note.created/deleted`, `quiz.started/graded`), and config limits
  (`notes_max_upload_bytes` 10 MB, `notes_max_extract_chars` 200k,
  `notes_max_count` 50).
- Registered in `api/__init__.py`.

**Dashboard (new):**
- New **Study** page (`pages/StudyPage.tsx`) + nav entry + `IconBook`. Upload,
  note list, quiz setup (count / type mcq|open|mixed / difficulty), and a
  question-by-question flow with a progress bar, per-answer feedback, revealed
  answers on a miss, and a final score. Page-local state; backend is the source
  of truth; mutations go through `run()`.
- **`api.ts` now supports file upload** — `request()` detects `FormData`, skips
  the JSON content-type so the browser sets the multipart boundary, and passes it
  through. It was JSON-only before. New `api.study.*` group.
- `types.ts`: `Note`, `QuizQuestion`, `QuizSession`. `events.ts` left untouched
  (the quiz is page-driven, not store-driven).

**Verified:** uploaded a .txt, generated 3 questions from it (pigment, equation,
thylakoid stage), graded a correct answer correct with feedback and a wrong answer
wrong with the correct answer revealed. Dashboard typechecks and builds clean.

**Not done:** voice quizzing on the device (say "quiz me on my biology notes",
answer out loud). The backend is structured to allow it. OCR for scanned
images/photos is intentionally out of scope (needs Tesseract or a vision model).
