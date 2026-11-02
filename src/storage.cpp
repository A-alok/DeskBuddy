#include "storage.h"

#include <Preferences.h>

namespace storage {

static bool ready = false;

void begin() {
  Preferences prefs;
  // Read-write open creates the namespace. A marker key makes sure the namespace
  // is actually committed, since an empty namespace is not persisted.
  if (!prefs.begin("deskmate", false)) {
    Serial.println("[nvs] could not open namespace; settings will not persist");
    ready = false;
    return;
  }
  if (!prefs.isKey("init")) {
    prefs.putUChar("init", 1);
    Serial.println("[nvs] namespace created");
  }
  prefs.end();
  ready = true;
}

bool available() { return ready; }

}  // namespace storage
