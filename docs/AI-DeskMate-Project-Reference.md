# AI DeskMate — Project Reference

*AI Voice Productivity Assistant built on ESP32-S3*

---

## 1. Project Aim & Goal

Build a physical desktop assistant that:
- Works fully **offline** for core productivity tools (clock, timer, stopwatch, alarm, Pomodoro, reminders, tasks)
- Adds **voice interaction and AI conversation** when internet/AI service is available
- Shows live status on a 1.3" OLED screen
- Mirrors state in real time with a **web dashboard** — starting a timer on the device shows on the dashboard, and vice versa
- Can control an external low-voltage device through a relay
- Eventually runs on battery power for portability

Guiding principle: the device should never become useless just because Wi-Fi or the AI service is down. Local functions (clock, timer, stopwatch, alarm, Pomodoro, touch, OLED, relay) always work; AI/cloud only adds conversation, complex commands, and planning.

---

## 2. Hardware Components

| # | Component | Role | Interface | Power |
|---|---|---|---|---|
| 1 | ESP32-S3-N16R8 | Main controller — Wi-Fi/BT, runs all logic | — | USB 5V (regulated onboard to 3.3V) |
| 2 | INMP441 | Microphone — voice input | I2S digital | 3.3V |
| 3 | MAX98357 | Audio amplifier | I2S digital | 5V (VIN), 3.3V  logic ok |
| 4 | Speaker | Audio output | Analog, driven by MAX98357 | via amp |
| 5 | 1.3" OLED | Status/UI display | I2C | 3.3V |
| 6 | TTP223 | Capacitive touch input | Digital GPIO | 3.3V |
| 7 | 5V Relay module | Switches an LED light (and other low-voltage loads) | Digital GPIO 13, active-LOW coil trigger | 5V (coil), isolated switched side |
| 8 | 18650 battery (1200mAh) | Portable power source | — | 3.0–4.2V raw |
| 9 | 18650 holder | Battery mount | — | — |
| 10 | TP4056 (USB-C) | Battery charger + protection | USB-C in, B+/B- to battery, OUT+/OUT- passthrough | 5V in |
| 11 | Jumper wires | Connections | — | — |
| 12 | GL12 B/B | Unidentified — not yet used | Unknown | Unknown |
| 13 | MT3608 DC-DC boost module | Steps raw cell voltage (3.0–4.2V) up to a regulated 5V | Adjustable step-up, trim pot | IN 3.0–4.2V, OUT set to 5.0V |

**Not on the original list, added as required:**
- Breadboard, multimeter, LED + ~220 ohm resistor (the LED is the relay's switched load)
- **MT3608-based 5V boost converter module** — now on hand; it is what lets the battery safely power the main circuit (see Section 7)

---

## 3. Confirmed Wiring / GPIO Map

All values below are **tested and working** as of the current hardware validation phase.

```
ESP32-S3-N16R8
|
|-- OLED (SH1106, I2C addr 0x3C)
|     SDA -> GPIO 8
|     SCL -> GPIO 9
|     VCC -> 3V3
|     GND -> GND
|
|-- INMP441 microphone (I2S RX)
|     SCK/BCLK -> GPIO 4
|     WS/LRCLK -> GPIO 5
|     SD/DOUT  -> GPIO 6
|     L/R      -> GND (selects left channel)
|     VDD -> 3V3
|     GND -> GND
|
|-- MAX98357 amplifier (I2S TX)
|     BCLK -> GPIO 15
|     LRC  -> GPIO 16
|     DIN  -> GPIO 7
|     VIN  -> 5VIN (confirm: or 3V3 — pending your confirmation)
|     SD   -> 3V3 (or GPIO 10 if driven by firmware — pending your confirmation)
|     GND  -> GND
|     Speaker +/- -> amp output terminals only (never GND)
|
|-- TTP223 touch sensor
|     OUT -> GPIO 14
|     VCC -> 3V3
|     GND -> GND
|     (Polarity: pending — send the "Idle level at boot" line)
|
|-- Relay module (switches an LED light)
|     Control side (to ESP32):
|       IN/SIG -> GPIO 13   (active-LOW: LOW energises the coil, see RELAY_ACTIVE_LOW)
|       VCC    -> 5VIN      (coil power, 5 V — NOT 3V3)
|       GND    -> GND       (shared ground, required)
|     Load side (switches the LED):
|       +5V source -> COM            (common contact)
|       NO         -> LED anode (+)  via ~220 ohm series resistor (bare 5 V LED)
|       LED cathode (-) -> source GND
|     NO = normally-open: LED is OFF when idle, ON when the relay energises.
|     Wire to NC instead only if you want the LED on while idle (it inverts).
|     A self-contained 5 V/12 V lamp module already has its resistor — drive its
|     + leg from COM/NO and its - leg to the supply ground.
|
|-- Battery / Power (via MT3608 boost — see Section 7)
      18650 cell -> TP4056 B+/B-
      TP4056 OUT+ -> MT3608 IN+
      TP4056 OUT- -> MT3608 IN-
      MT3608 OUT+ -> ESP32 5V/VIN  (also MAX98357 VIN, relay coil VCC)
      MT3608 OUT- -> GND  (common with ESP32 GND)
      *** Set MT3608 OUT to 5.0 V with a multimeter BEFORE wiring OUT to anything ***
```

### Reserved pin ranges (avoid — ESP32-S3-N16R8)
| Pins | Reason |
|---|---|
| GPIO 0, 3, 45, 46 | Strapping pins |
| GPIO 19, 20 | Native USB |
| GPIO 43, 44 | Serial console |
| GPIO 35, 36, 37 | Used internally by 8MB PSRAM (R8) |
| GPIO 26–32 | Internal flash/PSRAM, usually not exposed |
| GPIO 48 or 38 | Onboard RGB LED (board-dependent) |

### Pins still free for future use
GPIO 1, 2, 10, 11, 12, 17, 18, 21, and the ADC-capable pins — reserved candidates for battery voltage monitoring (Stage 16) and any future sensors.

---

## 4. Hardware Validation Status

| Test | Component | Result | Notes |
|---|---|---|---|
| 1 | ESP32-S3 basic | ✅ PASS | 16MB flash, ~8MB PSRAM confirmed |
| 2 | OLED | ✅ PASS | SH1106 controller, I2C address 0x3C |
| 3 | INMP441 mic | ✅ PASS | Level meter reacts correctly to voice |
| 4 | MAX98357 + speaker | ✅ PASS | Passed after replacing a faulty speaker |
| 5 | TTP223 touch | ✅ PASS | LED and Serial both confirm touch detection |
| 6 | Relay | ✅ PASS | Clean click + LED switching, no chatter |
| 7 | 18650 + TP4056 + MT3608 | ⏳ IN PROGRESS | Charging circuit identified; MT3608 boost module now on hand. Next: trim OUT to 5.0V on the bench, then wire the rail |

**Outstanding items to finalize the design:**
1. Amp VIN — confirm 5VIN or 3V3
2. Amp SD pin — confirm 3V3, GPIO, or unconnected
3. ESP32 Arduino core version (for reference in later audio/voice stages)
4. Touch sensor polarity (active-high/low) from the boot log line
5. Battery voltage readings (B+/B- and OUT+/OUT-) and TP4056 LED behavior
6. Second-battery goal (more runtime vs. more current) — needed to pick the right charger if pursued

---

## 5. Product Features

### Works fully offline (local firmware only)
- Digital clock (time, date, day) — needs Wi-Fi once for NTP sync, then works offline
- Timer — start/pause/resume/cancel, remaining time shown
- Stopwatch — start/stop/lap/reset
- Alarm — set/cancel/trigger
- Pomodoro — 25/5 default, custom durations, focus/break cycles, session stats
- Basic reminders (text + time)
- Basic task management (add/complete/delete/priority)
- Touch interaction (tap, hold, double-tap — to be defined per screen)
- LED/relay control — on-screen button (LED screen, double-tap toggles), voice ("turn on the light"), or dashboard
- OLED UI across all the above

### Requires internet / AI backend
- General conversation
- Complex natural-language commands ("remind me to call mom after my next meeting")
- Planning / multi-step reasoning
- Question answering
- Advanced voice interaction (STT → LLM → TTS pipeline) — **implemented and
  running**: push-to-talk → Whisper → regex parser → LLM intent fallback with the
  last 8 messages as memory → executor → spoken reply (edge-tts)
- Natural-language understanding: free-form speech maps to actions ("it's dark in
  here" → light on, "I need to focus" → Pomodoro, "wake me in 20 minutes" →
  reminder), with conversational references ("remove the last task", "delete it")
- Hindi / Hinglish commands ("light chalu karo", "5 minute ka timer lagao")
- **Study notes + AI quiz** (exam prep): upload PDF / Word / Excel / text notes,
  the backend extracts the text, and the AI generates questions grounded only in
  those notes and grades your answers. Dashboard **Study** page. Backend:
  `services/extract.py`, `services/quiz.py`, `api/notes.py`; `Note` /
  `QuizSession` models. Voice quizzing on the device is a planned follow-up; OCR
  for scanned images is out of scope.

### Voice command flow — IMPLEMENTED (Stage 10–11)
```
"Hey DeskMate" (wake, via touch first — no wake-word yet)
      ↓
Microphone (INMP441)
      ↓
Speech-to-Text (backend)
      ↓
Intent extraction
      ↓
   Local command  ──or──  AI (LLM)
      ↓                       ↓
   Timer/Task/etc         AI response
      ↓                       ↓
        OLED update
      ↓
Text-to-Speech (backend)
      ↓
Speaker (MAX98357)
```

---

## 6. OLED UI (1.3", 128×64)

**Home screen**
```
--------------------
       14:32
    19 SEP 2026

    Focus: 42m

   WiFi ●
   Battery 82%
--------------------
```

**Timer screen**
```
--------------------
       TIMER

       09:42

     RUNNING
--------------------
```

**Voice mode**
```
--------------------
     LISTENING...

   "Set timer..."
--------------------
```

Screens are managed by a state machine (`screen_manager`) — one active screen at a time, each with its own draw function. This is what Stage 1 firmware implements.

---

## 7. Power Architecture — Battery System

**Key fact confirmed from your TP4056 module:** OUT+/OUT- is a passthrough of the raw battery voltage through a protection IC — it is **not regulated**. It reads whatever the battery reads: ~4.2V full down to ~3.0V near empty.

The **MT3608 boost converter is now on hand** — this is the piece that makes the battery path safe. It takes the raw cell voltage in and boosts it up to a steady 5V, which the ESP32's onboard regulator then drops to 3.3V.

```
18650 (3.0–4.2V)
    ↓
TP4056 (charges the cell, protection IC guards output)
    ↓  OUT+/OUT-  (still 3.0–4.2V, NOT safe for ESP32 5V or 3V3 pins directly)
    ↓
MT3608 boost converter  —  IN+/IN- from TP4056 OUT+/OUT-
    ↓  OUT+/OUT- = steady 5V  (SET WITH A MULTIMETER FIRST — see below)
    ↓
ESP32-S3 "5V" pin → onboard regulator → 3.3V for chip, OLED, mic, touch
                  → also feeds MAX98357 (5V) and relay coil (5V) directly
```

**MT3608 connections:**

| MT3608 | Wire to |
|---|---|
| IN+ | TP4056 OUT+ |
| IN− | TP4056 OUT− |
| OUT+ | ESP32 5V/VIN + MAX98357 VIN + relay VCC |
| OUT− | common GND (ESP32 GND + all other grounds) |

**Set the output to 5.0V before connecting OUT to anything.** The MT3608 ships with its trim pot at a random position and can put out 20V+, which would destroy the ESP32, amp and OLED instantly. Procedure: feed IN+/IN− from the cell (or a bench supply ~3.7V), leave OUT open, meter across OUT+/OUT−, turn the pot clockwise/counter-clockwise until it reads **5.00V**, power down, then wire OUT into the 5V rail.

**Do not connect TP4056 OUT+/OUT- directly to the ESP32 — always go through the MT3608.** Feeding raw battery voltage into the 3V3 pin risks exceeding the chip's ~3.6V absolute max when freshly charged; feeding it into the 5V pin gives unreliable regulation as the battery discharges.

**Do not dual-source 5V.** Check for a Schottky diode between the USB VBUS and the 5V header pin; if there isn't one, powering from the MT3608 while USB is plugged in back-feeds the USB host. Charge through the TP4056's USB-C and keep the ESP32's USB for flashing — do not run both power paths at once unless the diode is present.

**Two-battery question (unresolved):** Series wiring (7.4V nominal) is unsafe with a single-cell TP4056 charger — it will overcharge the pack. Parallel wiring keeps 3.7V nominal, same charger works, but needs a holder actually wired for parallel and similarly-charged cells before first connecting. Waiting on your intended goal (runtime vs. peak current) to proceed.

---

## 8. Software Architecture

```
                 AI DESKMATE
                      |
        +-------------+-------------+
        |             |             |
       ESP32       Backend       Dashboard
        |             |             |
       OLED        Database       Web UI
       Mic         AI layer       Analytics
       Speaker     API            Controls
       Touch       WebSocket
       Relay
                      |
                 AI Services
                 (STT / LLM / TTS)
```

**Stack:**
| Layer | Technology |
|---|---|
| Device firmware | ESP32-S3, Arduino framework, C++ |
| Backend | FastAPI (Python), REST + WebSocket |
| Database | MongoDB Atlas (PyMongo async) — the plan said PostgreSQL; built on Atlas instead |
| Dashboard | React 19 + Vite + TypeScript + Tailwind v4 — the plan said Next.js; Vite chosen so Capacitor gets a static bundle |
| AI | GroqCloud: Whisper (STT), `openai/gpt-oss-20b` (LLM), Edge TTS (speech). All backend-hosted |
| Study notes | pypdf / python-docx / openpyxl extraction + Groq quiz generation and grading |

The ESP32 and dashboard never talk directly — the **backend is the sync hub**. Time-critical logic (timers, alarms, Pomodoro, clock) runs on the ESP32 using absolute end-timestamps, so both device and dashboard compute the same remaining time independently; only events (start/stop/change) are sent over WebSocket, not per-second ticks.

---

## 9. Web Dashboard

**Pages/components:**
1. Overview
2. AI Chat
3. Timer
4. Stopwatch
5. Alarms
6. Pomodoro
7. Tasks
8. Reminders
9. **Study Notes** — upload files, AI quiz from them
10. Productivity Analytics
11. Device Status
11. Device Settings

**Displays:**
- Device online/offline
- Battery %
- Wi-Fi status
- Current time
- Active timer
- Current mode
- Focus time
- Completed tasks
- Recent voice commands

**Controls (dashboard → device):**
- Start/stop timer
- Create reminder
- Create task
- Start Pomodoro
- Control relay
- Change device settings

---

## 10. Database Schema (planned)

Tables: `users`, `devices`, `tasks`, `reminders`, `timers`, `alarms`, `focus_sessions`, `voice_commands`, `device_events`, `settings`

Each will get columns, data types, relationships, and indexes once we reach Stage 13 — kept simple initially, expanded as features land.

---

## 11. API Plan (planned)

```
GET  /api/device/status
POST /api/timer/start
POST /api/timer/stop
GET  /api/timer/status
POST /api/tasks
GET  /api/tasks
POST /api/reminders
POST /api/pomodoro/start
GET  /api/analytics
POST /api/device/relay
```

Plus a WebSocket channel for real-time ESP32 ↔ dashboard sync (events, not polling).

---

## 12. Security Plan (later stages)

- Device authentication
- API authentication
- Secure Wi-Fi credential handling
- HTTPS
- WebSocket security
- Secrets in environment variables, never hardcoded
- Rate limiting where appropriate

---

## 13. Development Roadmap

| Phase | Stage | Status |
|---|---|---|
| A | Hardware validation (Tests 1–7) | 6/7 done |
| B | Stage 1: ESP32-S3 + OLED foundation | ⏳ In progress |
| B | Stage 2: Wi-Fi + NTP clock | Not started |
| B | Stage 3: Touch interaction | Not started |
| B | Stage 4: Timer | Not started |
| B | Stage 5: Stopwatch | Not started |
| B | Stage 6: Alarm | Not started |
| B | Stage 7: Pomodoro | Not started |
| C | Stage 8: Audio input (mic) | Not started |
| C | Stage 9: Audio output (amp) | Not started |
| D | Stage 12: Backend | Not started |
| D | Stage 13: Database | Not started |
| D | Stage 15: ESP32 ↔ backend sync | Not started |
| E | Stage 10: Voice command system | Not started |
| E | Stage 11: AI assistant | Not started |
| F | Stage 14: Web dashboard | Not started |
| G | Stage 16: Battery/power optimization | Blocked — needs boost converter |
| G | Stage 17: Enclosure/final integration | Not started |

---

## 14. Project Folder Structure

```
AI-DeskMate/
├── firmware/
│   ├── src/
│   ├── include/
│   ├── components/
│   └── platformio.ini
├── backend/
│   ├── app/
│   ├── api/
│   ├── models/
│   ├── services/
│   └── requirements.txt
├── dashboard/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── package.json
├── docs/
│   ├── wiring/
│   ├── architecture/
│   └── testing/
└── README.md
```

**Toolchain note:** Hardware tests were done in Arduino IDE; a parallel PlatformIO setup was just started for the touch sensor. Pick one before Stage 1+ firmware continues, to avoid maintaining two build systems side by side.

---

*Last updated: reflects progress through Test 6 (relay) passed, Test 7 (battery) in progress, Stage 1 (screen manager) awaiting confirmation.*
