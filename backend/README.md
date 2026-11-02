# AI DeskMate — Backend

FastAPI sync hub between the ESP32-S3 device and the dashboard / mobile app.
Storage is **MongoDB Atlas**, the assistant runs on **GroqCloud**. Completely
standalone: its own virtualenv, its own port. The dashboard talks to it over HTTP
and one WebSocket, nothing else.

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then fill in MONGODB_URI and GROQ_API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` is what lets a phone or the ESP32 on the same Wi-Fi reach it.

- Interactive docs: http://localhost:8000/docs
- Health, including the two things that actually break: http://localhost:8000/health
- One-shot state for a cold start: http://localhost:8000/api/snapshot

### Verify it before building on it

```powershell
.\.venv\Scripts\python.exe scripts\selfcheck.py
```

Exercises the real cluster and the real Groq key: connection, indexes, CRUD on
every collection, the timer/stopwatch/Pomodoro state machines, the scheduler
firing a live timer, the intent parser, the HTTP surface, and a Groq completion.
Everything it writes is namespaced to a throwaway device id and deleted at the
end, so it is safe against the cluster you actually use.

## MongoDB Atlas

Get the URI from **Atlas > Database > Connect > Drivers > Python**:

```
MONGODB_URI=mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=deskmate
```

Two things cause nearly every first-run failure, so the error messages call them
out by name:

1. **Network Access.** Atlas blocks everything by default, and the resulting
   error looks like a plain timeout rather than a permission problem. Add your IP
   under *Security > Network Access* (`0.0.0.0/0` is fine for a throwaway demo
   cluster, never for anything real).
2. **Password encoding.** If the password contains `@ : / ? # [ ] %` it must be
   percent-encoded in the URI — `p@ss` becomes `p%40ss`.

### Driver choice

PyMongo's native async API (`AsyncMongoClient`). Motor reached end of life in
May 2026 and MongoDB points all new async work here. The client is opened with
`tz_aware=True`, so every datetime comes back timezone-aware and the whole class
of naive-datetime comparison bugs simply does not exist. BSON keeps millisecond
precision; microseconds are truncated, which is far below anything this app cares
about.

Because the driver is genuinely async, handlers are async all the way down. The
awkward tradeoff the SQLite version carried — synchronous sessions called from
async endpoints — is gone.

### Collections

`users` · `devices` · `timers` · `stopwatches` · `alarms` · `reminders` · `tasks`
· `pomodoro_states` · `focus_sessions` · `voice_commands` · `device_events` ·
`settings` · `chat_messages`

Conventions worth knowing:

- `_id` is our own uuid4 hex, exposed as `id`. **No ObjectId ever reaches the
  API**, so ids stay identical to what earlier clients already stored.
- Singleton-per-device documents (`stopwatches`, `pomodoro_states`) use the device
  id as `_id`, which makes "get or create" one idempotent upsert.
- `settings._id` is `"<device_id>:<key>"`, so writing a setting needs no
  read-modify-write and concurrent writers cannot duplicate a key.
- Enums are stored as their string values (`"running"`, not `2`), so documents are
  readable in the Atlas UI.
- **`device_events` has a TTL index.** It is the only collection that grows
  without bound, and the free tier is 512 MB. Retention is
  `EVENT_RETENTION_DAYS`, default 14.

Indexes are created on every startup (idempotent), including one per scheduler
query so "what is already due?" is a bounded index scan rather than a collection
walk.

### Failure behaviour

A missing or unreachable cluster does **not** crash the process. `/health`
reports `database: {"status": "down", "detail": ...}` with a message that names
the likely fix, and data endpoints return **503** rather than a 500 from deep in
the driver. Starting up and explaining the problem beats dying on import when the
cause is usually one wrong character in a connection string.

## Groq

```
GROQ_API_KEY=gsk_...
AI_PROVIDER=groq              # or "mock" to force the offline path
GROQ_MODEL=openai/gpt-oss-20b
GROQ_REASONING_EFFORT=low
```

Groq speaks the OpenAI chat-completions shape at
`https://api.groq.com/openai/v1`, so this is a thin httpx client rather than
another SDK dependency.

### Model choice matters here

Verified against the live API in September 2026:

| Model | Speed | Notes |
|---|---|---|
| `openai/gpt-oss-20b` | ~1000 tok/s | cheapest, **default** |
| `openai/gpt-oss-120b` | ~500 tok/s | stronger |
| `llama-3.3-70b-versatile` | — | **Enterprise-only, 404s on a free key** |
| `whisper-large-v3-turbo` | — | speech-to-text, for Stage 8 |

GroqCloud retires models on a regular cadence — the Llama models moved to
Enterprise-only in 2026. `GET /api/ai/models` lists what your key can actually
use, and a dead model id produces a log line naming the replacement rather than a
generic 404.

### reasoning_effort is not optional tuning

`gpt-oss` are reasoning models. At default effort they spend most of the token
budget thinking before emitting anything — measured on this key:

| | reasoning tokens | latency |
|---|---|---|
| default | 109 | 220 ms |
| `low` | 5 | 85 ms |

We want two short sentences to speak aloud, not deliberation, so `low` is both
faster and better. If a future model rejects the parameter, the client retries
once without it instead of failing the request. An empty reply (budget consumed
entirely by reasoning) is treated as an error and falls back, with a message
telling you to raise `GROQ_MAX_COMPLETION_TOKENS` or lower the effort.

### Offline is a first-class path

With `AI_PROVIDER=mock`, or no key, or Groq unreachable, the assistant still
works: the local intent parser handles every device command and open-ended
questions get a short canned reply. That is not a fallback bolted on afterwards —
it is the product requirement that the device stays useful when the network does
not.

The key is read from the environment on the backend only. It never reaches the
dashboard, the phone or the ESP32.

## How sync works

The device and the dashboard never talk directly. Both connect to `/ws`, the
backend persists every state change, then fans out one event:

```
ESP32  ──ws──►  backend  ──ws──►  dashboard / phone
              (Atlas)
```

Nothing streams per-second ticks. A running timer is stored as an **absolute UTC
`ends_at`**, and each client computes `ends_at - now` on its own animation frame.
Consequences that matter:

- A client that reconnects after ten minutes offline lands on the correct value.
- Restarting the backend does not shift any deadline.
- A dropped WebSocket costs you the *notification*, never the *schedule*.

The background scheduler ticks once a second and asks "what is already due?"
rather than counting anything down.

## WebSocket protocol

```
ws://localhost:8000/ws?role=device&device_id=deskmate-01&token=<DEVICE_TOKEN>
ws://localhost:8000/ws?role=dashboard&device_id=deskmate-01&token=<API_KEY>
```

`token` is only checked when `REQUIRE_AUTH=true`. Every frame, both directions,
uses the same envelope:

```json
{
  "type": "timer.started",
  "device_id": "deskmate-01",
  "origin": "device",
  "ts": "2026-09-22T11:22:31.553Z",
  "payload": { "id": "...", "label": "Deep work", "ends_at": "2026-09-22T11:47:31Z", "state": "running" }
}
```

Frames a client may **send**:

| Frame | Payload | Meaning |
|---|---|---|
| `device.heartbeat` | telemetry fields | battery, Wi-Fi, heap, uptime, relay, screen |
| `timer.start` | `duration_seconds`, `label` | start/replace the active timer |
| `timer.pause` / `.resume` / `.cancel` | — | control the active timer |
| `stopwatch.start` / `.stop` / `.lap` / `.reset` | — | stopwatch control |
| `pomodoro.start` / `.pause` / `.resume` / `.stop` / `.skip` | optional config | Pomodoro control |
| `alarm.set` | `time_of_day`, `days_of_week` | create an alarm |
| `reminder.create` | `text`, `in_minutes` or `at_time` | create a reminder |
| `task.create` / `task.complete` | `title`, `priority` | task control |
| `relay.set` | `on` | switch the relay |
| `screen.changed` | `screen` | firmware reports the active OLED screen |
| `touch` | `gesture` | firmware reports tap / hold / double-tap |
| `voice.command` | `transcript` | run a spoken command through the pipeline |
| `voice.listening` | `listening` | mic opened/closed, drives the LISTENING UI |
| `ping` | — | replies `pong` |

Note the asymmetry: the device sends **commands** (`timer.start`), the backend
broadcasts **facts** (`timer.started`). Server-sent names live in
`app/events.py` — that file is the contract the firmware mirrors.

## Voice / AI pipeline

```
transcript ─► local intent parser ─► execute + broadcast   (works offline)
                     └─ no match ─► Groq ─► spoken reply     (needs network)
```

`app/services/intents.py` is deliberately regex-based, not a model, so a spoken
command and the same text typed into the dashboard behave identically. Only
genuinely open-ended messages reach Groq.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness, **Atlas status**, AI mode, connection counts |
| GET | `/api/snapshot` | full state in one request — use on load and reconnect |
| GET | `/api/device/status` | device telemetry |
| POST | `/api/device/heartbeat` | ESP32 telemetry push (self-registers new devices) |
| POST | `/api/device/relay` | `{ "on": true }` |
| POST | `/api/device/screen` | force an OLED screen |
| POST | `/api/device/ping` | ask the firmware to acknowledge |
| GET | `/api/device/events` | recent event log (TTL-expired) |
| GET/POST | `/api/timer/*` | `status`, `start`, `pause`, `resume`, `stop`, `extend`, `history` |
| GET/POST | `/api/stopwatch/*` | `status`, `start`, `stop`, `lap`, `reset` |
| GET/POST/PATCH/DELETE | `/api/alarms` | |
| GET/POST/PATCH/DELETE | `/api/tasks` | |
| GET/POST/PATCH/DELETE | `/api/reminders` | |
| GET/POST/PATCH | `/api/pomodoro/*` | `status`, `start`, `pause`, `resume`, `stop`, `skip`, `config`, `reset-cycles`, `sessions` |
| GET | `/api/analytics?range_days=7` | focus minutes, streak, per-day series |
| POST/GET | `/api/chat`, `/api/chat/history` | dashboard + mobile chat |
| POST/GET | `/api/voice/command`, `/api/voice/commands` | firmware voice entry point |
| GET | `/api/ai/models` | **what your Groq key can actually use** |
| GET/PUT | `/api/settings` | per-device key/value (timezone, brightness, volumes) |

Every endpoint takes an optional `?device_id=` and defaults to
`DEFAULT_DEVICE_ID`, so single-device setups can ignore it.

## Security

**The default configuration is unauthenticated.** `REQUIRE_AUTH=false` ships that
way so a clean checkout runs with zero setup, which is fine on localhost and not
fine anywhere else. Before you port-forward, tunnel, or deploy this:

```env
REQUIRE_AUTH=true
API_KEY=<python -c "import secrets; print(secrets.token_urlsafe(32))">
DEVICE_TOKEN=<another one>
```

The dashboard then sends `X-API-Key`, the firmware sends `X-Device-Token`, and the
WebSocket takes the same value as `?token=`. Both are compared with
`hmac.compare_digest`. Secrets come from the environment only; `.env` is
gitignored and `.env.example` holds no real values.

Also worth knowing: the Atlas URI contains a database password, so `.env` is the
only place it belongs — never a config file you commit. And CORS defaults to an
explicit origin list including Capacitor's `capacitor://localhost`;
`CORS_ALLOW_ALL=true` exists for quick LAN demos and disables credentialed
requests as a consequence.

## Layout

```
backend/
├── app/
│   ├── main.py            FastAPI app, CORS, lifespan, /health
│   ├── config.py          env-driven settings (Atlas + Groq)
│   ├── db.py              AsyncMongoClient, indexes, TTL, seed, health
│   ├── repo.py            thin document <-> model helpers
│   ├── models.py          pydantic documents
│   ├── schemas.py         request/response shapes
│   ├── serializers.py     document -> API, computes remaining_seconds
│   ├── events.py          WebSocket event name contract
│   ├── realtime.py        connection hub + fan-out + event log
│   ├── ws.py              /ws endpoint and inbound frame handling
│   ├── security.py        API key / device token dependencies
│   ├── deps.py            device resolution, 503 when the DB is down
│   ├── utils.py           UTC helpers, next-occurrence maths
│   ├── api/               REST routers, one per feature
│   └── services/          domain logic + scheduler + intents + Groq
├── scripts/selfcheck.py   end-to-end verification against your cluster
└── requirements.txt
```

## Verification status

Verified without a cluster (no Docker, Atlas URI not yet supplied):

- Imports clean, **46 OpenAPI paths**.
- Every PyMongo async API assumption checked by introspection — which methods are
  coroutines, which return chainable cursors. Getting an `await` wrong on a cursor
  method is a whole class of runtime bug, and none of them are present.
- Degraded mode: `connect()` returns False instead of raising, `/health` answers
  200 with `status: degraded`, data endpoints return 503 with an explanatory body.
- Intent parser: 12 phrasings plus duration and clock parsing.
- **Groq live**: model list retrieved, configured model confirmed available,
  single-turn and multi-turn completions succeeded (59 ms), a decommissioned model
  id degrades to the mock path with a message naming the replacement, and an
  invalid `reasoning_effort` is dropped rather than sent.

**Not verified: no MongoDB server has run this code.** Collection reads/writes,
index creation, the TTL index, the aggregation pipelines and the scheduler against
real data are all unexercised. That is what `scripts/selfcheck.py` is for — run it
first, before assuming anything works.
