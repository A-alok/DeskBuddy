#pragma once
/**
 * NVS namespace bootstrap.
 *
 * Every module opens the shared "deskmate" namespace read-only to load its
 * settings. On a factory-fresh chip that namespace does not exist yet, so each
 * of those opens logs `nvs_open failed: NOT_FOUND` — harmless, but it buries the
 * real boot diagnostics in noise.
 *
 * Calling begin() once, first, creates the namespace so the read-only opens that
 * follow succeed.
 */

#include <Arduino.h>

namespace storage {

/** Create the shared namespace if it does not exist. Safe to call repeatedly. */
void begin();

/** True if NVS is usable. False means settings will not persist across reboots. */
bool available();

}  // namespace storage
