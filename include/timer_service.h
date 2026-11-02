#pragma once
/**
 * Countdown timer.
 *
 * The running state is a single absolute monotonic deadline. Remaining time is
 * always derived, never decremented, so a slow loop, a long Wi-Fi retry or a
 * blocking HTTP call cannot make the timer drift.
 */

#include <Arduino.h>

#include "run_state.h"

namespace timerService {

void begin();

/** Call every loop. Fires the finished event when the deadline passes. */
void update();

void start(uint32_t durationSeconds, const char *label = "Timer");
void pause();
void resume();
void cancel();

/** Extend or shorten a live timer. Negative values shorten it. */
void adjust(int32_t deltaSeconds);

/** Tap behaviour: start default / pause / resume depending on state. */
void toggle();

RunState state();
uint32_t durationSeconds();
uint32_t remainingSeconds();
const char *label();

/** Absolute monotonic deadline, or 0 when not running. */
uint64_t deadlineMonotonicMs();

/** Adopt state pushed by the backend. Deadline arrives as a UTC epoch. */
void applyRemote(RunState newState, uint32_t duration, uint64_t endsAtEpochMs,
                 uint32_t remainingSecondsIfPaused, const char *newLabel);

}  // namespace timerService
