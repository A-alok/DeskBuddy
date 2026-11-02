#pragma once

#include <Arduino.h>

namespace taskService {

const uint8_t MAX_TASKS = 10;

struct Task {
  bool used;
  char remoteId[25]; // MongoDB ObjectID is 24 chars + null
  char title[64];
  bool done;
};

void begin();
void clearRemote();
void upsertRemote(const char *remoteId, const char *title, bool done);
bool removeByRemoteId(const char *remoteId);
uint8_t count();

// Pointer to the internal array. Length is always MAX_TASKS. Check 'used'.
const Task *list();

} // namespace taskService
