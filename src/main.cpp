/**
 * AI DeskMate — ESP32-S3 firmware
 *
 * Wiring: docs/AI-DeskMate-Project-Reference.md (validated through Test 6)
 * Protocol: backend/app/events.py
 *
 * ---------------------------------------------------------------------------
 * Structure
 * ---------------------------------------------------------------------------
 * Single-threaded cooperative loop. No RTOS tasks, no mutexes, no shared-state
 * races to debug at 2am. Every subsystem exposes update() and returns quickly;
 * the only blocking call in the whole firmware is the snapshot HTTP GET, and
 * that runs at most once per reconnect.
 *
 * Dependency direction is the product requirement made structural:
 *
 *     services  ->  bus  ->  net_link
 *        |                      |
 *        +------> screens <-----+
 *
 * Services never call the network. They mutate their own state and drop a note
 * on the bus. If net_link were deleted the device would still keep time, run
 * timers, ring alarms, switch the relay and drive the OLED — which is exactly
 * what "works fully offline" has to mean.
 *
 * ---------------------------------------------------------------------------
 * Time
 * ---------------------------------------------------------------------------
 * Local deadlines are absolute monotonic instants (esp_timer, µs since boot).
 * Nothing counts down. A slow loop, a Wi-Fi retry storm or a blocking HTTP call
 * cannot make a timer drift, and an NTP correction cannot make one jump.
 * Wall-clock epoch time is used only to talk to the backend and to evaluate
 * alarms, which are genuinely calendar-based.
 */

#include <Arduino.h>

#include "alarm_service.h"
#include "animations.h"
#include "ble_prov.h"
#include "bus.h"
#include "chime.h"
#include "clock_time.h"
#include "config.h"
#include "diagnostics.h"
#include "display.h"
#include "mic.h"
#include "net_link.h"
#include "pomodoro_service.h"
#include "relay.h"
#include "screens.h"
#include "stopwatch_service.h"
#include "storage.h"
#include "timer_service.h"
#include "task_service.h"
#include "reminder_service.h"
#include "weather_service.h"
#include "touch.h"
#include "voice.h"

static uint64_t lastFrameMs = 0;
static const uint32_t FRAME_INTERVAL_MS = 1000UL / DISPLAY_FPS;
static const uint32_t ANIMATION_FRAME_INTERVAL_MS = 1000UL / ANIMATION_FPS;

/** Local events that need a sound or a screen takeover, handled UI-side. */
static void reactToLocalEvent(bus::Event event) {
  switch (event) {
    case bus::Event::TimerFinished:
      chime::playTimerDone();
      screens::showNotice("TIMER DONE", timerService::label(), NOTICE_DURATION_MS);
      screens::show(screens::Screen::Timer);
      break;

    case bus::Event::PomodoroPhaseChanged: {
      const bool focus = pomodoroService::phase() == PomodoroPhase::Focus;
      if (focus) {
        chime::playPomodoroFocus();
        screens::showNotice("FOCUS", "break over", NOTICE_DURATION_MS);
      } else {
        chime::playPomodoroBreak();
        screens::showNotice("BREAK", "focus block done", NOTICE_DURATION_MS);
      }
      screens::show(screens::Screen::Pomodoro);
      break;
    }

    case bus::Event::AlarmTriggered:
      chime::playAlarmLoop();
      screens::show(screens::Screen::Alarms);
      display::noteActivity();
      break;

    default:
      break;
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println();
  Serial.println("=== AI DeskMate " FIRMWARE_VERSION " ===");
  Serial.printf("chip: %s rev %d, %d core(s) @ %lu MHz\n", ESP.getChipModel(),
                ESP.getChipRevision(), ESP.getChipCores(),
                static_cast<unsigned long>(getCpuFrequencyMhz()));
  Serial.printf("flash: %lu MB   PSRAM: %lu KB   free heap: %lu KB\n",
                static_cast<unsigned long>(ESP.getFlashChipSize() / (1024 * 1024)),
                static_cast<unsigned long>(ESP.getPsramSize() / 1024),
                static_cast<unsigned long>(ESP.getFreeHeap() / 1024));

  // Breadcrumbs. A peripheral that misbehaves at boot otherwise gives you a
  // silent hang and no idea which one it was.
  Serial.print("[boot] nvs ");
  storage::begin();

  // Order matters here. The relay goes first so its pin is parked at the
  // de-energised level as early as possible — anything else first and you hear
  // a click on every boot.
  Serial.println("[boot] relay");
  relay::begin();

  Serial.println("[boot] display");
  const bool haveDisplay = display::begin();
  if (!haveDisplay) {
    Serial.println("[boot] no OLED — continuing headless, everything else still works");
  }

  Serial.println("[boot] chime");
  chime::begin();

  Serial.println("[boot] touch");
  touch::begin();

  // Microphone after the chime, so the two I2S peripherals are installed in a
  // fixed order and a failure in either is unambiguous in the log. A failure here
  // only costs voice: begin() says so and every other feature carries on.
  Serial.println("[boot] microphone");
  mic::begin();

#if DIAGNOSTIC_MODE
  // Everything the self-test needs (display, chime, relay, touch pin) is up.
  // This never returns.
  diagnostics::run();
#endif

  Serial.println("[boot] services");
  timerService::begin();
  stopwatchService::begin();
  pomodoroService::begin();
  alarmService::begin();
  taskService::begin();
  reminderService::begin();
  weatherService::begin();
  voice::begin();
  screens::begin();

  // Network last, and it never blocks. Everything above already works.
  Serial.println("[boot] network");
  netLink::begin();
  bleProv::begin();

  // The device comes up as a face and stays there. Armed last, not inside
  // display::begin(), because everything between the two would have eaten into
  // the lid ramp and you would only see the tail of it.
  if (haveDisplay) animations::startFace();

  Serial.println();
  Serial.println("ready");
  Serial.println("showing the face — touch the pad to open the menu");
  Serial.println("gestures: tap = next screen, double tap = action");
  Serial.println("push to talk: double tap on Home, hold on any other screen");
}

void loop() {
  // --- input ---
  touch::Gesture gesture = touch::update();
  if (gesture != touch::Gesture::None) {
    screens::handleGesture(gesture);
    Serial.printf("[touch] %s -> %s\n", touch::gestureName(gesture), screens::currentName());
  }

  // --- local logic: each of these fires its own deadline ---
  timerService::update();
  pomodoroService::update();
  alarmService::update();

  // Voice sits here rather than with the output: it drains the microphone DMA,
  // which is an input that cannot wait for the frame interval. Once a recording
  // ends this call performs the upload and does not return for up to two seconds —
  // the one place in the loop that knowingly blocks.
  voice::update();

  // --- react to anything the services just raised ---
  // The UI has its own read cursor, so sounds and notices never depend on the
  // network layer having run, or on it having run first.
  bus::Event event;
  uint8_t budget = 4;
  while (budget-- > 0 && bus::nextForUi(event)) {
    reactToLocalEvent(event);
  }

  // --- output ---
  chime::update();

  // --- network: pumps the socket and drains the bus ---
  netLink::update();
  bleProv::update();

  // --- draw; the I2C panel is the slowest thing in this loop ---
  // Two rates, not one. Static screens at DISPLAY_FPS leave plenty of loop time
  // for the socket and the chime; an animation needs ANIMATION_FPS to look like
  // motion rather than a slideshow. Paying for the faster rate only while
  // something is actually moving keeps the idle case cheap.
  const uint64_t now = clocktime::monotonicMs();
  const uint32_t frameInterval =
      screens::animating() ? ANIMATION_FRAME_INTERVAL_MS : FRAME_INTERVAL_MS;
  if (now - lastFrameMs >= frameInterval) {
    lastFrameMs = now;
    screens::render();
  }

  // Yield so the IDLE task can run and the watchdog stays fed.
  delay(2);
}
