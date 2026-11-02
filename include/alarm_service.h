#pragma once
/**
 * Alarms: wall-clock times, so they need NTP. Stored in NVS and reloaded at
 * boot, because an alarm that forgets itself on a power blip is worse than no
 * alarm at all.
 *
 * Unlike timers these cannot be monotonic — "07:00" is a statement about the
 * local calendar, not about elapsed time. Each alarm therefore carries a
 * one-per-minute fire guard so a clock correction cannot double-trigger it.
 */

#include <Arduino.h>

#include "config.h"

struct Alarm {
  bool used = false;
  bool enabled = false;
  uint8_t hour = 7;
  uint8_t minute = 0;
  /** Bit 0 = Monday ... bit 6 = Sunday. 0 = one-shot, next occurrence only. */
  uint8_t daysMask = 0;
  char label[25] = "Alarm";
  /**
   * Backend row id, empty for a device-local alarm. Alarms live in both places:
   * the backend owns the definition so the dashboard can edit it, and the device
   * keeps a copy so it still rings with the network down. Both sides evaluate
   * the same "07:00 on weekdays" independently — nobody has to be told when.
   */
  char remoteId[33] = "";
  /** Epoch minute we last fired at, to suppress repeats inside one minute. */
  uint32_t lastFiredMinute = 0;
};

namespace alarmService {

void begin();
void update();

uint8_t count();
const Alarm &at(uint8_t index);

int8_t add(uint8_t hour, uint8_t minute, uint8_t daysMask, const char *label);
bool remove(uint8_t index);
bool setEnabled(uint8_t index, bool enabled);
bool toggleEnabled(uint8_t index);

/** Index of the alarm that will fire soonest, or -1. */
int8_t nextAlarmIndex();
/** Seconds until that alarm, or 0 if none / clock unset. */
uint32_t secondsUntilNext();

/** True while an alarm is ringing and not yet acknowledged. */
bool isRinging();
uint8_t ringingIndex();
void acknowledge();

void clearAll();

// --- backend sync --------------------------------------------------------- //

int8_t findByRemoteId(const char *remoteId);

/** Create or update the alarm carrying `remoteId`. Returns its slot, or -1. */
int8_t upsertRemote(const char *remoteId, uint8_t hour, uint8_t minute,
                    uint8_t daysMask, bool enabled, const char *label);

bool removeByRemoteId(const char *remoteId);
bool triggerRemote(const char *remoteId);

/** Drop every backend-owned alarm. Used before adopting a fresh snapshot. */
void clearRemote();

/** Write the current set to NVS. Call once after a batch of upserts. */
void flush();

}  // namespace alarmService
