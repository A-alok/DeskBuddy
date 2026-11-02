#pragma once
/**
 * Stopwatch: banked milliseconds from finished segments plus the start instant
 * of the current one. Elapsed time is derived, same reasoning as the timer.
 */

#include <Arduino.h>

#include "run_state.h"

namespace stopwatchService {

void begin();

void start();
void stop();
void lap();
void reset();
void toggle();

RunState state();
uint64_t elapsedMs();
uint8_t lapCount();
/** Cumulative elapsed time at lap `index` (0-based). */
uint64_t lapAt(uint8_t index);
/** Duration of lap `index` on its own. */
uint64_t lapSplit(uint8_t index);

void applyRemote(RunState newState, uint64_t accumulatedMs, uint64_t startedAtEpochMs);

}  // namespace stopwatchService
