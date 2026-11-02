#pragma once
/**
 * Time. Two independent clocks, on purpose.
 *
 *  monotonicMs()  microseconds-since-boot / 1000. Never jumps, never wraps in
 *                 any practical lifetime, available immediately at power-on.
 *                 ALL local deadlines are stored against this.
 *
 *  epochMs()      real UTC time, only valid after NTP has answered.
 *                 Used solely to talk to the backend.
 *
 * Why the split: a timer must keep correct time with Wi-Fi down and the clock
 * unset. If deadlines were stored as epoch values, the moment NTP corrected a
 * drifting clock every running timer would jump. Storing them monotonically and
 * converting only at the network boundary means an NTP correction changes what
 * we *report*, never what we *count*.
 */

#include <Arduino.h>

namespace clocktime {

/** Milliseconds since boot. Safe before Wi-Fi, never goes backwards. */
uint64_t monotonicMs();

/** Start the SNTP client. Non-blocking; poll isSynced(). */
void beginNtp();

/** True once NTP has delivered a plausible wall-clock time. */
bool isSynced();

/** UTC milliseconds since the epoch, or 0 when not yet synced. */
uint64_t epochMs();

/** Seconds the local timezone is ahead of UTC (e.g. 19800 for IST). */
long utcOffsetSeconds();

/** Local wall-clock parts. Returns false if the clock is not set yet. */
bool localTime(struct tm &out);

/** Convert a monotonic deadline to a UTC epoch instant. 0 if unsynced. */
uint64_t monotonicToEpochMs(uint64_t monoMs);

/** Convert a UTC epoch instant to a monotonic deadline. 0 if unsynced. */
uint64_t epochToMonotonicMs(uint64_t epoch);

/** Parse "2026-09-22T11:47:31.553990Z" to UTC epoch ms. 0 on failure. */
uint64_t parseIso8601(const char *iso);

/** Format a UTC epoch instant as "...Z". Writes at most len bytes. */
void formatIso8601(uint64_t epoch, char *out, size_t len);

/** How many seconds until the next occurrence of a local HH:MM. */
uint32_t secondsUntilLocalTimeOfDay(uint8_t hour, uint8_t minute,
                                    uint8_t daysOfWeekMask);

/** Bit 0 = Monday ... bit 6 = Sunday. 0 means "any day". */
uint8_t localWeekdayBit();

}  // namespace clocktime
