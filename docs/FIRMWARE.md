# AI DeskMate — ESP32-S3 Firmware

Arduino framework under PlatformIO. Implements Stages 1–7 (OLED screen manager,
Wi-Fi + NTP clock, touch, timer, stopwatch, alarm, Pomodoro) plus the device half
of Stage 15 (backend sync), and drives the MAX98357 for chimes.

## Build and flash

```powershell
copy include\secrets.h.example include\secrets.h   # then edit it
pio run                 # compile
pio run -t upload       # flash
pio device monitor       # serial, 115200
```

It compiles and runs with `secrets.h` left at its defaults — it just stays
offline and says so on the serial port. Every local feature still works.

Current footprint: **RAM 15.2%** (49.7 KB of 320 KB), **Flash 15.4%**
(1.0 MB of 6.5 MB). Plenty of headroom for the audio pipeline in Stages 8–11.

## Set these three things first

| In | What | Why |
|---|---|---|
| `include/config.h` | `DESKMATE_TZ` | POSIX TZ string. **The sign is inverted**: UTC+5:30 is `"IST-5:30"`. Defaults to `UTC0`, so the clock will be wrong until you set it. |
| `include/config.h` | `RELAY_ACTIVE_LOW` | 1 for most opto-isolated modules (coil energises on a LOW input). Wrong value = relay closed whenever the device is idle. The relay switches an LED on GPIO 13; wire the LED through COM/NO so it is off when idle. |
| `include/secrets.h` | Wi-Fi + `BACKEND_HOST` | Your computer's LAN IP, not `localhost`. Start the backend with `--host 0.0.0.0`. |

Two things auto-detect, so you don't have to resolve the open questions from the
hardware doc before flashing:

- **Touch polarity.** Sampled at boot and printed to serial. Keep off the pad for
  the first half second.
- **Amp SD pin.** `AMP_HAS_SD_PIN 1` drives GPIO 10 to mute the output stage
  between sounds. Set it to 0 if SD is tied straight to 3V3.

## Gestures — one pad, three actions

| Gesture | Does | Everywhere |
|---|---|---|
| tap | next screen | yes |
| double tap | primary action (start / pause / **toggle the LED** on the LED screen) | per screen |
| hold ≥900 ms | push-to-talk voice (double tap on Home) | per screen |

Navigation gets the cheapest gesture because it is by far the most common thing
you do on the device itself — the dashboard is the real control surface. Every
screen prints its own bindings on the bottom line, and a hold draws a progress
bar so a long press never feels dead.

Screens cycle: Home → Timer → Stopwatch → Alarms → Pomodoro → Tasks →
Reminders → **LED (relay)** → back to Home. Network is left out of the cycle
(forcing a reconnect is a diagnostic action, reachable from the dashboard); the
LED screen is now in it so the light can be toggled by touch alone.

### LED (relay) screen
The LED screen is the on-screen button for the relay-switched light. **Double-tap
toggles it.** The screen shows `LED ON` / `LED OFF` with a lamp glyph (filled with
rays when on, hollow when off). The same light also responds to voice —
"turn on the light", "switch off the lamp", "light on" — and to the dashboard.
All paths share the one relay state, which is persisted in NVS and restored on
boot at the de-energised level so the coil does not click during startup.

## Architecture

```
services ──► bus ──► net_link
    │                   │
    └────► screens ◄────┘
```

Single-threaded cooperative loop. No RTOS tasks, no mutexes, no shared-state
races. Every subsystem exposes `update()` and returns quickly; the only blocking
call in the firmware is the snapshot HTTP GET, which runs at most once per
reconnect.

The dependency arrow is the product requirement made structural: **services never
call the network.** They mutate their own state and drop a note on the bus. Delete
`net_link.cpp` and the device still keeps time, runs timers, rings alarms,
switches the relay and drives the OLED.

The bus has two independent read cursors, one for the UI and one for the network.
A single shared queue would mean whichever consumer ran first swallowed the
event — so a timer finishing while the socket was busy would ring but not
publish, or publish but not ring.

## Two clocks, deliberately

| | Source | Used for |
|---|---|---|
| `monotonicMs()` | `esp_timer`, µs since boot | **every local deadline** |
| `epochMs()` | NTP wall clock | talking to the backend, evaluating alarms |

Nothing counts down. A running timer is a single absolute monotonic instant and
remaining time is always derived. Consequences that matter:

- A slow loop, a Wi-Fi retry storm or a blocking HTTP call cannot make a timer drift.
- An NTP correction changes what we *report*, never what we *count*. Store
  deadlines as epoch values instead and the first sync makes every running timer jump.
- Timers work correctly before NTP has ever answered.

`millis()` is not used for deadlines anywhere — it wraps at 49.7 days.

Alarms are the exception and have to be: "07:00 on weekdays" is a statement about
the calendar, not about elapsed time. They need NTP, and each carries a
one-per-minute fire guard so a clock correction cannot double-trigger it.

## Backend sync

Connects to `ws://<host>:8000/ws?role=device&device_id=...`, heartbeats every
10 s (the backend marks a device offline after 30 s), and adopts
`GET /api/snapshot` on every reconnect.

**Reconcile, don't replay.** Events emitted while the socket is down are dropped,
not queued. State is recovered wholesale from the snapshot, so there is no
half-applied replay to get wrong.

**On reconnect the backend wins**, since it survives device reboots and is shared
with the dashboard and the phone. One exception: a timer started on the device
while offline is pushed up rather than silently lost.

**Echo suppression.** Inbound state is applied under a `bus::RemoteScope`, which
suppresses emission. A dashboard "start timer" does not bounce back as a device
event. The backend does echo its authoritative `timer.started` to us, and we
adopt its `ends_at` — that is the resync, not a loop.

**Two events are deliberately not published:** `timer.finished` and
`pomodoro.phase_changed`. The backend holds the same absolute deadline and fires
them from its own scheduler; publishing ours too would double-notify every
dashboard.

Alarms live on both sides. The backend owns the definition so the dashboard can
edit it; the device keeps a copy in NVS so it still rings with the network down.
Both evaluate the same "07:00 on weekdays" independently — nobody has to be told
when.

Persisted in NVS: alarms, relay state, Pomodoro durations, brightness, volume.

## Audio

Chimes only, on I2S peripheral 1. `chime::update()` tops up the DMA buffer with
whatever it accepts right now and returns — a blocking beep would freeze the
display and stall the socket for the length of the sound. Notes get a 5 ms attack
and decay, without which a class-D amp clicks audibly at every note edge.

**The microphone is wired and tested but not opened.** Capture is Stage 8, and
the backend has no speech-to-text endpoint to send audio to yet. Pins are
reserved in `config.h` on I2S peripheral 0, so mic and amp can run
simultaneously — that separation is what makes full-duplex voice possible later.
An inbound `speak` frame currently chimes and shows the text instead of speaking it.

## Files

```
include/
  config.h            pins, timings, timezone — start here
  secrets.h.example   copy to secrets.h
  iso8601.h           header-only date maths, host-testable
  clock_time.h        the two clocks
  bus.h               event queue, two cursors, RemoteScope
  run_state.h         mirrors the backend's RunState
  display.h           SH1106 + burn-in protection + draw helpers
  screens.h           screen state machine
  touch.h  relay.h  chime.h
  timer_service.h  stopwatch_service.h  pomodoro_service.h  alarm_service.h
  net_link.h          Wi-Fi + WebSocket + snapshot
src/                  one .cpp per header, plus main.cpp
test/host/            host tests, not part of the firmware build
```

## First flash — what the hardware actually reported

Flashed and running on the real board. `esptool --chip esp32s3 flash_id` says:

```
Chip is ESP32-S3 (QFN56) (revision v0.2)
Features: WiFi, BLE, Embedded PSRAM 8MB (AP_3v3)
Crystal is 40MHz      MAC: ac:a7:04:12:66:74
Detected flash size: 16MB
```

So the board is genuinely an **N16R8** — 16 MB flash, 8 MB *octal* PSRAM.

Serial is a **WCH CH343 bridge (`VID:PID=1A86:55D3`) on COM5**, i.e. a separate
USB-UART chip rather than native USB. That is why the `ARDUINO_USB_MODE` /
`ARDUINO_USB_CDC_ON_BOOT` flags in `platformio.ini` must stay commented out.

Clean boot log:

```
=== AI DeskMate 0.1.0 ===
chip: ESP32-S3 rev 0, 2 core(s) @ 240 MHz
flash: 16 MB   PSRAM: 8189 KB   free heap: 321 KB
[boot] nvs [boot] relay
[boot] display
[oled] prefs... pins... Wire.begin... probe... u8g2... ok
[oled] SH1106 ready at 0x3C, contrast 180
[boot] chime
[chime] I2S TX ready
[boot] touch
[touch] idle level LOW -> active-HIGH (default config)
[boot] services
[boot] network
[net] Wi-Fi credentials not set in include/secrets.h — running offline.
ready
```

### Three things the first flash found

**1. It hung in `setup()` with no output.** The U8g2 constructor is given the
clock/data pins, which makes the library call `Wire.begin(sda, scl)` itself during
`panel.begin()`. Since `display::begin()` had *already* called `Wire.begin()` to
probe for the panel, that second init deadlocked inside the ESP32 I2C driver — a
silent hang, the worst kind to debug. Fixed by calling `Wire.end()` to hand the bus
back before `panel.begin()`, so exactly one `begin()` ever runs against it.

`display::begin()` now returns `bool` and the firmware continues headless if no
panel answers. A desk clock that refuses to boot because its screen is unplugged
is worse than one that boots and says so.

**2. PSRAM reported 0 KB despite the chip having 8 MB.** Selecting
`board_build.arduino.memory_type = qio_opi` is necessary but **not sufficient** —
Arduino only brings PSRAM up when `-DBOARD_HAS_PSRAM` is also defined. Without it
there is no error and no warning, just `ESP.getPsramSize() == 0`. Both are now set
and it reports 8189 KB. This matters for Stage 8: audio buffering wants that RAM.

**3. Touch polarity is resolved.** Idle reads LOW, so the module is **active-HIGH,
factory default config** (neither solder pad bridged). That was outstanding item #4
in the hardware doc. The auto-detection in `touch::begin()` means the firmware
would have adapted either way, but now it is a known quantity.

Also cleaned up: NVS logged `nvs_open failed: NOT_FOUND` twice at every boot
because each module opened the shared namespace read-only before anything had
created it. `storage::begin()` now creates it first, so the boot log contains only
real information.

### Verifying touch, LED/relay and screens without watching the OLED

Every gesture is logged, so bring-up does not require squinting at a 128×64 panel.
To toggle the LED by touch: tap through the screen cycle to **LED**, then
double-tap.

```powershell
pio device monitor
# then tap the pad
[touch] tap -> screen timer
[touch] double_tap -> screen led (relay on)
[touch] hold -> screen timer
```

To capture the `setup()` output — which `pio device monitor` misses because it
attaches after the board has already booted — force a reset with the monitor
already listening:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" tools\boot_log.py COM5 12
```

## Verification status

- **Runs on the real board.** Boots clean with no errors, 30-second soak with no
  watchdog reset or panic under the continuous 10 fps I2C refresh. OLED
  acknowledged at 0x3C, I2S TX initialised, touch polarity detected, PSRAM up.
- **Compiles clean**: zero warnings under `-Wall` for every file in `src/`.
- **Date maths**: 29 host tests pass, including leap years (2024, 2000, 2100),
  every month length, explicit `+05:30` / `-08:00` offsets, malformed-input
  rejection, and a 4000-day format/parse round trip. Anchors were cross-checked
  against Python's `datetime`, which is how I found that four of my own expected
  constants were wrong rather than the code.

  ```powershell
  g++ -std=c++17 -Wall -Wextra -I include test/host/test_iso8601.cpp -o iso_test
  ./iso_test
  ```

- **Protocol contract**: 59 checks against the running backend. Every frame
  `net_link.cpp` sends was replayed and accepted; heartbeat telemetry was
  confirmed stored on the device row; every field the firmware parses was
  confirmed present in `timer.started`, `alarm.created`, `settings.updated` and
  `/api/snapshot`; `ends_at` was confirmed to be the exact ISO-8601-Z shape
  `iso8601::parse` expects.

### Network sync, verified on hardware

Wi-Fi, NTP, the WebSocket and snapshot adoption all work against the live backend.
Measured from a cold boot:

```
  0.4s  boot, PSRAM 8189 KB
  2.5s  [net] Wi-Fi up, IP 192.168.0.110, RSSI -45
  4.5s  [net] websocket connected
  5.0s  [net] snapshot adopted
  6.8s  [net] <- relay.set (from dashboard)
  9.4s  [net] <- pomodoro.started (from dashboard)
 15.9s  [net] <- speak (from server)           Groq reply, 1.7s round trip
 18.4s  [net] <- timer.started (from dashboard)
 24.5s  [net] <- timer.finished (from system)   backend scheduler fired it
```

Two behaviours worth calling out, both confirmed rather than assumed:

- A relay command sent while the socket was still down was picked up anyway at
  5.0s through `snapshot adopted`. **Reconcile-on-reconnect works** — the event was
  dropped, the state was not.
- `timer.finished` arrived `from system`, meaning the backend's own scheduler fired
  it from the stored `ends_at`. The firmware deliberately does not publish that
  event itself, and the two sides agreed without coordination.

`BACKEND_HOST` in `secrets.h` is a DHCP address. If the router reassigns it the
device stops linking silently — set a static lease, or watch for
`snapshot HTTP -1` in the log and reflash.

**Still unverified — needs eyes and ears on the device:**

| Not checked | How to check |
|---|---|
| Whether the OLED shows the right thing | Nobody has looked at it. The panel acknowledges at 0x3C and U8g2 initialises, but glyphs, layout and the dim/blank policy are unconfirmed. |
| Touch gestures end to end | Polarity is detected; tap/double-tap/hold timing needs a finger. Watch the `[touch]` lines. |
| LED/relay actually switching | Double-tap on the LED screen (or say "turn on the light"). Confirm the relay click, the LED lighting, and that it does **not** click during boot. |
| Chime audio | `speak` and `timer.finished` both arrived, so it *should* have sounded. Nobody has heard it. Double-tap on the Timer screen. |
| Alarms firing | NTP works now, but no alarm has been scheduled and waited on. |

## Known gaps

| Gap | Why |
|---|---|
| No microphone capture, STT, TTS | Stage 8–11; backend has no audio endpoint |
| Alarms cannot be created on the device | One button makes time entry impractical; create them on the dashboard, the device mirrors and rings them |
| Tasks and reminders not shown on OLED | 128×64 is the wrong surface for a list; reminders announce themselves as a notice when due |
| `BATTERY_SENSE_ENABLED 0` | Divider not fitted yet (Stage 16). MT3608 boost module now on hand; set its OUT to 5.0 V, wire the rail, fit the GPIO 1 divider, then flip this to 1 |
| Timer duration limited to presets on-device | 5/10/15/25/45 min; arbitrary durations come from the dashboard |
