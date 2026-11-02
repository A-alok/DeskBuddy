#include "touch.h"

#include "clock_time.h"
#include "config.h"

namespace touch {

static bool activeHigh = true;
static bool debounced = false;
static bool rawLast = false;
static uint64_t lastEdgeMs = 0;
static uint64_t pressStartMs = 0;
static bool holdFired = false;

// A tap is only reported once we know no second tap is coming.
static bool tapPending = false;
static uint64_t tapPendingSince = 0;

static bool readRaw() {
  bool level = digitalRead(PIN_TOUCH) == HIGH;
  return activeHigh ? level : !level;
}

/**
 * Is anything actually driving the pin, or is it just floating?
 *
 * A stable idle reading proves nothing on its own — a disconnected input can sit
 * at a convincing 0. Fighting it with the internal pull-up settles it: the
 * TTP223's push-pull output easily wins against ~45 kOhm, so a genuinely
 * connected sensor holds its level either way. A floating pin follows whichever
 * resistor is enabled.
 */
static void reportWiring() {
  pinMode(PIN_TOUCH, INPUT_PULLUP);
  delay(10);
  const int withPullUp = digitalRead(PIN_TOUCH);

  pinMode(PIN_TOUCH, INPUT_PULLDOWN);
  delay(10);
  const int withPullDown = digitalRead(PIN_TOUCH);

  pinMode(PIN_TOUCH, INPUT);
  delay(10);

  // Note the limit of this check: it proves *something* holds the pin, but it
  // cannot tell the TTP223 driving low from the OUT wire being shorted to GND.
  if (withPullUp == withPullDown) {
    Serial.printf("[touch] driven %s — sensor connected\n", withPullUp ? "HIGH" : "LOW");
  } else {
    Serial.printf(
        "[touch] *** PIN FLOATING on GPIO %d (pull-up->%d, pull-down->%d) ***\n"
        "[touch]     Nothing is driving it. Check VCC=3V3, GND, and the OUT wire.\n",
        PIN_TOUCH, withPullUp, withPullDown);
  }
}

void begin() {
  pinMode(PIN_TOUCH, INPUT);
  // The sensor calibrates its baseline over the first few hundred ms.
  delay(500);

  reportWiring();

  int idle = digitalRead(PIN_TOUCH);
  activeHigh = (idle == LOW);

  Serial.printf("[touch] idle level %s -> %s\n", idle ? "HIGH" : "LOW",
                activeHigh ? "active-HIGH (default config)"
                           : "active-LOW (pad B bridged)");

  rawLast = readRaw();
  debounced = rawLast;
  if (debounced) {
    Serial.println("[touch] warning: reads as touched at boot — check wiring");
  }
  lastEdgeMs = clocktime::monotonicMs();
}

Gesture update() {
  const uint64_t now = clocktime::monotonicMs();
  bool raw = readRaw();

#if TOUCH_DEBUG
  // Report the electrical truth, separately from the gesture state machine.
  // This is what distinguishes "the sensor never fires" from "the sensor fires
  // and the gesture logic mishandles it".
  static bool debugLast = false;
  static bool debugInit = false;
  static uint64_t lastHeartbeat = 0;
  if (!debugInit) {
    debugInit = true;
    debugLast = raw;
  }
  if (raw != debugLast) {
    debugLast = raw;
    Serial.printf("[touch] raw %s (pin level %d)\n", raw ? "TOUCH" : "release",
                  digitalRead(PIN_TOUCH));
  }
  if (now - lastHeartbeat > 3000) {
    lastHeartbeat = now;
    Serial.printf("[touch] idle check: pin=%d active%s debounced=%d\n",
                  digitalRead(PIN_TOUCH), activeHigh ? "HIGH" : "LOW",
                  debounced ? 1 : 0);
  }
#endif

  if (raw != rawLast) {
    rawLast = raw;
    lastEdgeMs = now;
  }

  // Accept the level only once it has been stable through the debounce window.
  if (raw != debounced && (now - lastEdgeMs) >= TOUCH_DEBOUNCE_MS) {
    debounced = raw;

    if (debounced) {
      pressStartMs = now;
      holdFired = false;
    } else {
      uint64_t heldFor = now - pressStartMs;
      if (!holdFired && heldFor < TOUCH_HOLD_MS) {
        if (tapPending && (now - tapPendingSince) <= TOUCH_DOUBLE_TAP_WINDOW_MS) {
          tapPending = false;
          return Gesture::DoubleTap;
        }
        tapPending = true;
        tapPendingSince = now;
      }
    }
  }

  // Hold fires while the finger is still down, so it feels immediate.
  if (debounced && !holdFired && (now - pressStartMs) >= TOUCH_HOLD_MS) {
    holdFired = true;
    tapPending = false;
    return Gesture::Hold;
  }

  // A tap is confirmed only after the double-tap window closes.
  if (tapPending && (now - tapPendingSince) > TOUCH_DOUBLE_TAP_WINDOW_MS) {
    tapPending = false;
    return Gesture::Tap;
  }

  return Gesture::None;
}

bool isDown() { return debounced; }

float holdProgress() {
  if (!debounced || holdFired) return 0.0f;
  uint64_t held = clocktime::monotonicMs() - pressStartMs;
  if (held >= TOUCH_HOLD_MS) return 1.0f;
  return static_cast<float>(held) / static_cast<float>(TOUCH_HOLD_MS);
}

bool activeLowDetected() { return !activeHigh; }

const char *gestureName(Gesture gesture) {
  switch (gesture) {
    case Gesture::Tap: return "tap";
    case Gesture::DoubleTap: return "double_tap";
    case Gesture::Hold: return "hold";
    default: return "none";
  }
}

}  // namespace touch
