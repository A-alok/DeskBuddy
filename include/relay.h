#pragma once
/**
 * Relay output.
 *
 * The pin is driven to the de-energised level *before* it becomes an output, so
 * the coil does not click during the few hundred milliseconds between power-on
 * and setup() running. Last state is restored from NVS.
 */

#include <Arduino.h>

namespace relay {

void begin();

void set(bool on);
void toggle();
bool isOn();

/** Apply a state pushed from the backend without re-publishing it. */
void applyRemote(bool on);

}  // namespace relay
