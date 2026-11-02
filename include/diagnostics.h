#pragma once
/**
 * Hardware self-test and memory reporting.
 *
 * `DIAGNOSTIC_MODE` in config.h boots into run() instead of the normal UI. It
 * exists because "tapping does nothing" has at least three causes that look
 * identical from the outside:
 *
 *   - the OLED is not drawing (so you cannot see anything change)
 *   - the touch pad is not sensing (so nothing changes)
 *   - the gesture logic is wrong (so the wrong thing changes)
 *
 * run() separates them. It draws unmistakable test patterns first, so the screen
 * proves itself before being used to report anything else, then shows the raw
 * touch pin live in large type with a transition counter.
 */

#include <Arduino.h>

namespace diagnostics {

/** Flash, heap, PSRAM and NVS usage. Safe to call in normal mode. */
void memoryReport();

/** Blocking hardware self-test. Never returns. */
void run();

}  // namespace diagnostics
