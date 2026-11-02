#pragma once

#include <Arduino.h>

namespace reminderService {

const uint8_t MAX_REMINDERS = 10;

struct Reminder {
  bool used;
  char remoteId[25]; // MongoDB ObjectID is 24 chars + null
  char text[64];
  uint64_t remindAt;
};

void begin();
void clearRemote();
void upsertRemote(const char *remoteId, const char *text, uint64_t remindAt);
bool removeByRemoteId(const char *remoteId);
uint8_t count();

// Pointer to the internal array. Length is always MAX_REMINDERS. Check 'used'.
const Reminder *list();

} // namespace reminderService
