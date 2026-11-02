#pragma once
/**
 * TTP223 gesture recogniser.
 *
 * One pad, three gestures. Polarity is detected at boot rather than assumed,
 * because whether the module is active-high or active-low depends on which
 * solder pad was bridged at the factory — and getting it wrong inverts every
 * gesture silently.
 */

#include <Arduino.h>

namespace touch {

enum class Gesture : uint8_t {
  None = 0,
  Tap,        // primary action on the current screen
  DoubleTap,  // next screen
  Hold,       // secondary action: cancel / reset / skip
};

/** Samples the idle level to learn polarity. Keep off the pad for ~500 ms. */
void begin();

/** Call every loop. Returns a gesture once, on completion. */
Gesture update();

/** True while the pad is being touched (debounced). */
bool isDown();

/**
 * 0..1 progress toward a Hold while the pad is held. Lets the UI draw a
 * progress bar so a long press has visible feedback instead of feeling dead.
 */
float holdProgress();

/** True if the module turned out to be active-low (pad B bridged). */
bool activeLowDetected();

const char *gestureName(Gesture gesture);

}  // namespace touch
