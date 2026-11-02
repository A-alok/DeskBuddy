#pragma once
/**
 * Screen state machine — one active screen, each with its own draw function and
 * its own meaning for the three gestures.
 *
 * Gesture model, uniform across every screen:
 *   tap        -> next screen        (navigation: frequent, never destructive)
 *   double tap -> primary action     (start / pause / toggle)
 *   hold       -> secondary action   (cancel / reset / skip)
 *
 * Navigation gets the cheapest gesture because it is by far the most common
 * thing you do on the device itself; the dashboard is the real control surface.
 * Anything that could destroy a running 25-minute focus block needs a
 * deliberate gesture, not a brush of the pad.
 */

#include <Arduino.h>

#include "touch.h"

namespace screens {

enum class Screen : uint8_t {
  Home = 0,
  Timer,
  Stopwatch,
  Alarms,
  Pomodoro,
  Tasks,
  Reminders,
  Relay,
  Network,
  Count,
};

void begin();

/** Draw the current screen (or an active notice). Call at the UI frame rate. */
void render();

/**
 * True while something on screen is moving fast enough to need ANIMATION_FPS
 * instead of DISPLAY_FPS. The main loop asks before every frame so the faster
 * cadence — and the I2C traffic it costs — only applies while it buys something.
 */
bool animating();

/** Route a gesture to the current screen. */
void handleGesture(touch::Gesture gesture);

void show(Screen screen);
void next();
Screen current();
/** Lower-case name matching the backend's `current_screen` field. */
const char *currentName();
/** Adopt a screen name pushed by the backend. */
void showByName(const char *name);

/** Take over the display with a transient message. */
void showNotice(const char *title, const char *body, uint32_t durationMs);
bool noticeActive();
void dismissNotice();

}  // namespace screens
