#include "relay.h"

#include <Preferences.h>

#include "bus.h"
#include "config.h"

namespace relay {

static bool state = false;
static Preferences prefs;

static inline uint8_t levelFor(bool on) {
#if RELAY_ACTIVE_LOW
  return on ? LOW : HIGH;
#else
  return on ? HIGH : LOW;
#endif
}

static void apply() { digitalWrite(PIN_RELAY, levelFor(state)); }

void begin() {
  if (prefs.begin("deskmate", true)) {
    state = prefs.getBool("relay", false);
    prefs.end();
  }

  // Order matters. Write the level first so that the instant the pin becomes an
  // output it is already at the de-energised level. Doing pinMode() first lets
  // the pin sit at 0 for one instruction, which on an active-low module is long
  // enough to hear the relay click on every boot.
  digitalWrite(PIN_RELAY, levelFor(state));
  pinMode(PIN_RELAY, OUTPUT);
  apply();
}

void set(bool on) {
  if (state == on) return;
  state = on;
  apply();
  if (prefs.begin("deskmate", false)) {
    prefs.putBool("relay", state);
    prefs.end();
  }
  bus::emit(bus::Event::RelaySet);
}

void toggle() { set(!state); }

bool isOn() { return state; }

void applyRemote(bool on) {
  bus::RemoteScope guard;
  set(on);
}

}  // namespace relay
