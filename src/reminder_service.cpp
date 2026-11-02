#include "reminder_service.h"
#include <string.h>

namespace reminderService {

static Reminder reminders[MAX_REMINDERS];

void begin() {
  clearRemote();
}

void clearRemote() {
  for (uint8_t i = 0; i < MAX_REMINDERS; ++i) {
    reminders[i].used = false;
  }
}

static int8_t findByRemoteId(const char *remoteId) {
  if (remoteId == nullptr || *remoteId == '\0') return -1;
  for (uint8_t i = 0; i < MAX_REMINDERS; ++i) {
    if (reminders[i].used && strcmp(reminders[i].remoteId, remoteId) == 0) return i;
  }
  return -1;
}

static int8_t findFreeSlot() {
  for (uint8_t i = 0; i < MAX_REMINDERS; ++i) {
    if (!reminders[i].used) return i;
  }
  return -1;
}

void upsertRemote(const char *remoteId, const char *text, uint64_t remindAt) {
  int8_t slot = findByRemoteId(remoteId);
  if (slot < 0) {
    slot = findFreeSlot();
    if (slot < 0) return; // Full
  }

  reminders[slot].used = true;
  strlcpy(reminders[slot].remoteId, remoteId, sizeof(reminders[slot].remoteId));
  strlcpy(reminders[slot].text, text, sizeof(reminders[slot].text));
  reminders[slot].remindAt = remindAt;
}

bool removeByRemoteId(const char *remoteId) {
  int8_t slot = findByRemoteId(remoteId);
  if (slot < 0) return false;
  reminders[slot].used = false;
  return true;
}

uint8_t count() {
  uint8_t c = 0;
  for (uint8_t i = 0; i < MAX_REMINDERS; ++i) {
    if (reminders[i].used) c++;
  }
  return c;
}

const Reminder *list() { return reminders; }

} // namespace reminderService
