#include "task_service.h"
#include <string.h>

namespace taskService {

static Task tasks[MAX_TASKS];

void begin() {
  clearRemote();
}

void clearRemote() {
  for (uint8_t i = 0; i < MAX_TASKS; ++i) {
    tasks[i].used = false;
  }
}

static int8_t findByRemoteId(const char *remoteId) {
  if (remoteId == nullptr || *remoteId == '\0') return -1;
  for (uint8_t i = 0; i < MAX_TASKS; ++i) {
    if (tasks[i].used && strcmp(tasks[i].remoteId, remoteId) == 0) return i;
  }
  return -1;
}

static int8_t findFreeSlot() {
  for (uint8_t i = 0; i < MAX_TASKS; ++i) {
    if (!tasks[i].used) return i;
  }
  return -1;
}

void upsertRemote(const char *remoteId, const char *title, bool done) {
  int8_t slot = findByRemoteId(remoteId);
  if (slot < 0) {
    slot = findFreeSlot();
    if (slot < 0) return; // Full
  }

  tasks[slot].used = true;
  strlcpy(tasks[slot].remoteId, remoteId, sizeof(tasks[slot].remoteId));
  strlcpy(tasks[slot].title, title, sizeof(tasks[slot].title));
  tasks[slot].done = done;
}

bool removeByRemoteId(const char *remoteId) {
  int8_t slot = findByRemoteId(remoteId);
  if (slot < 0) return false;
  tasks[slot].used = false;
  return true;
}

uint8_t count() {
  uint8_t c = 0;
  for (uint8_t i = 0; i < MAX_TASKS; ++i) {
    if (tasks[i].used) c++;
  }
  return c;
}

const Task *list() { return tasks; }

} // namespace taskService
