#include "alarm_service.h"

#include <Preferences.h>

#include "bus.h"
#include "clock_time.h"

namespace alarmService {

static Alarm alarms[MAX_ALARMS];
static bool ringing = false;
static uint8_t ringingIdx = 0;
static Preferences prefs;

// One NVS blob rather than a key per field: fewer writes, and the flash on these
// modules has a finite erase budget.
static void persist() {
  if (!prefs.begin("deskmate", false)) return;
  prefs.putBytes("alarms", alarms, sizeof(alarms));
  prefs.end();
}

static void load() {
  if (!prefs.begin("deskmate", true)) return;
  // isKey() first: asking for the length of a missing blob logs an error, which
  // is pure noise on a factory-fresh chip where no alarm has ever been saved.
  if (prefs.isKey("alarms") && prefs.getBytesLength("alarms") == sizeof(alarms)) {
    prefs.getBytes("alarms", alarms, sizeof(alarms));
  }
  prefs.end();

  // Defensive: reject anything that could not have come from this firmware.
  for (uint8_t i = 0; i < MAX_ALARMS; ++i) {
    if (alarms[i].hour > 23 || alarms[i].minute > 59) alarms[i] = Alarm();
    alarms[i].label[sizeof(alarms[i].label) - 1] = '\0';
    alarms[i].lastFiredMinute = 0;
  }
}

void begin() {
  load();
  ringing = false;
}

uint8_t count() {
  uint8_t used = 0;
  for (uint8_t i = 0; i < MAX_ALARMS; ++i) {
    if (alarms[i].used) ++used;
  }
  return used;
}

const Alarm &at(uint8_t index) {
  static Alarm empty;
  return index < MAX_ALARMS ? alarms[index] : empty;
}

int8_t add(uint8_t hour, uint8_t minute, uint8_t daysMask, const char *label) {
  if (hour > 23 || minute > 59) return -1;
  for (uint8_t i = 0; i < MAX_ALARMS; ++i) {
    if (alarms[i].used) continue;
    alarms[i] = Alarm();
    alarms[i].used = true;
    alarms[i].enabled = true;
    alarms[i].hour = hour;
    alarms[i].minute = minute;
    alarms[i].daysMask = daysMask;
    strlcpy(alarms[i].label, (label && *label) ? label : "Alarm",
            sizeof(alarms[i].label));
    persist();
    return static_cast<int8_t>(i);
  }
  return -1;  // all slots full
}

bool remove(uint8_t index) {
  if (index >= MAX_ALARMS || !alarms[index].used) return false;
  alarms[index] = Alarm();
  if (ringing && ringingIdx == index) ringing = false;
  persist();
  return true;
}

bool setEnabled(uint8_t index, bool enabled) {
  if (index >= MAX_ALARMS || !alarms[index].used) return false;
  alarms[index].enabled = enabled;
  persist();
  return true;
}

bool toggleEnabled(uint8_t index) {
  if (index >= MAX_ALARMS || !alarms[index].used) return false;
  return setEnabled(index, !alarms[index].enabled);
}

int8_t nextAlarmIndex() {
  if (!clocktime::isSynced()) return -1;
  int8_t best = -1;
  uint32_t bestDelta = UINT32_MAX;
  for (uint8_t i = 0; i < MAX_ALARMS; ++i) {
    if (!alarms[i].used || !alarms[i].enabled) continue;
    uint32_t delta = clocktime::secondsUntilLocalTimeOfDay(
        alarms[i].hour, alarms[i].minute, alarms[i].daysMask);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = static_cast<int8_t>(i);
    }
  }
  return best;
}

uint32_t secondsUntilNext() {
  int8_t index = nextAlarmIndex();
  if (index < 0) return 0;
  return clocktime::secondsUntilLocalTimeOfDay(alarms[index].hour,
                                               alarms[index].minute,
                                               alarms[index].daysMask);
}

void update() {
  // Wall-clock alarms are meaningless without a real clock.
  if (!clocktime::isSynced()) return;

  struct tm local {};
  if (!clocktime::localTime(local)) return;

  uint32_t epochMinute = static_cast<uint32_t>(clocktime::epochMs() / 60000ULL);
  uint8_t todayBit = clocktime::localWeekdayBit();

  for (uint8_t i = 0; i < MAX_ALARMS; ++i) {
    Alarm &alarm = alarms[i];
    if (!alarm.used || !alarm.enabled) continue;
    if (alarm.hour != local.tm_hour || alarm.minute != local.tm_min) continue;
    if (alarm.daysMask != 0 && (alarm.daysMask & todayBit) == 0) continue;
    // Already handled this minute.
    if (alarm.lastFiredMinute == epochMinute) continue;

    alarm.lastFiredMinute = epochMinute;
    ringing = true;
    ringingIdx = i;

    // One-shot alarms disable themselves so they do not fire again tomorrow.
    if (alarm.daysMask == 0) alarm.enabled = false;
    persist();

    bus::emit(bus::Event::AlarmTriggered);
    return;
  }
}

bool isRinging() { return ringing; }
uint8_t ringingIndex() { return ringingIdx; }
void acknowledge() { ringing = false; }

void clearAll() {
  for (uint8_t i = 0; i < MAX_ALARMS; ++i) alarms[i] = Alarm();
  ringing = false;
  persist();
}

// --------------------------------------------------------------------------- //
// Backend sync
// --------------------------------------------------------------------------- //

int8_t findByRemoteId(const char *remoteId) {
  if (remoteId == nullptr || *remoteId == '\0') return -1;
  for (uint8_t i = 0; i < MAX_ALARMS; ++i) {
    if (alarms[i].used && strcmp(alarms[i].remoteId, remoteId) == 0) {
      return static_cast<int8_t>(i);
    }
  }
  return -1;
}

int8_t upsertRemote(const char *remoteId, uint8_t hour, uint8_t minute,
                    uint8_t daysMask, bool enabled, const char *label) {
  if (hour > 23 || minute > 59) return -1;

  int8_t slot = findByRemoteId(remoteId);
  if (slot < 0) {
    for (uint8_t i = 0; i < MAX_ALARMS; ++i) {
      if (!alarms[i].used) {
        slot = static_cast<int8_t>(i);
        break;
      }
    }
  }
  // All slots full: the device holds MAX_ALARMS and the dashboard may hold more.
  // Dropping the overflow is the honest outcome; the backend still rings it.
  if (slot < 0) return -1;

  Alarm &alarm = alarms[static_cast<uint8_t>(slot)];
  bool changed = !alarm.used || alarm.hour != hour || alarm.minute != minute ||
                 alarm.daysMask != daysMask || alarm.enabled != enabled;

  alarm.used = true;
  alarm.enabled = enabled;
  alarm.hour = hour;
  alarm.minute = minute;
  alarm.daysMask = daysMask;
  strlcpy(alarm.label, (label && *label) ? label : "Alarm", sizeof(alarm.label));
  strlcpy(alarm.remoteId, remoteId != nullptr ? remoteId : "", sizeof(alarm.remoteId));
  // A rescheduled alarm must be allowed to fire again.
  if (changed) alarm.lastFiredMinute = 0;

  return slot;
}

bool removeByRemoteId(const char *remoteId) {
  int8_t slot = findByRemoteId(remoteId);
  if (slot < 0) return false;
  return remove(static_cast<uint8_t>(slot));
}

bool triggerRemote(const char *remoteId) {
  int8_t slot = findByRemoteId(remoteId);
  if (slot < 0) return false;

  ringing = true;
  ringingIdx = static_cast<uint8_t>(slot);

  Alarm &alarm = alarms[ringingIdx];
  // One-shot alarms disable themselves so they do not fire again tomorrow.
  if (alarm.daysMask == 0) alarm.enabled = false;
  persist();

  bus::emit(bus::Event::AlarmTriggered);
  return true;
}

void clearRemote() {
  for (uint8_t i = 0; i < MAX_ALARMS; ++i) {
    if (alarms[i].used && alarms[i].remoteId[0] != '\0') {
      if (ringing && ringingIdx == i) ringing = false;
      alarms[i] = Alarm();
    }
  }
}

void flush() { persist(); }

}  // namespace alarmService
