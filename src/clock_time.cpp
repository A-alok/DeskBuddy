#include "clock_time.h"

#include <esp_timer.h>
#include <sys/time.h>
#include <time.h>

#include "config.h"
#include "iso8601.h"

namespace clocktime {

// Any wall-clock value below this is the 1970 default, i.e. "not set".
static const uint64_t PLAUSIBLE_EPOCH_MS = 1600000000000ULL;  // Sep 2020

uint64_t monotonicMs() {
  // esp_timer is a 64-bit microsecond counter: no rollover to handle, and it
  // keeps running through light sleep. millis() would wrap at ~49.7 days.
  return static_cast<uint64_t>(esp_timer_get_time() / 1000);
}

void beginNtp() {
  // configTzTime applies the POSIX TZ string and starts SNTP in one call.
  configTzTime(DESKMATE_TZ, NTP_SERVER_1, NTP_SERVER_2);
}

uint64_t epochMs() {
  struct timeval tv;
  if (gettimeofday(&tv, nullptr) != 0) return 0;
  uint64_t ms = static_cast<uint64_t>(tv.tv_sec) * 1000ULL + tv.tv_usec / 1000;
  return ms < PLAUSIBLE_EPOCH_MS ? 0 : ms;
}

bool isSynced() { return epochMs() != 0; }

long utcOffsetSeconds() {
  time_t now = time(nullptr);
  if (now < static_cast<time_t>(PLAUSIBLE_EPOCH_MS / 1000)) return 0;
  struct tm local {};
  struct tm utc {};
  localtime_r(&now, &local);
  gmtime_r(&now, &utc);
  // Compare the two broken-down times rather than trusting tm_gmtoff.
  long localSecs = local.tm_hour * 3600L + local.tm_min * 60L + local.tm_sec;
  long utcSecs = utc.tm_hour * 3600L + utc.tm_min * 60L + utc.tm_sec;
  long diff = localSecs - utcSecs;
  if (diff > 43200L) diff -= 86400L;
  if (diff < -43200L) diff += 86400L;
  return diff;
}

bool localTime(struct tm &out) {
  time_t now = time(nullptr);
  if (now < static_cast<time_t>(PLAUSIBLE_EPOCH_MS / 1000)) return false;
  localtime_r(&now, &out);
  return true;
}

uint64_t monotonicToEpochMs(uint64_t monoMs) {
  uint64_t nowEpoch = epochMs();
  if (nowEpoch == 0) return 0;
  uint64_t nowMono = monotonicMs();
  // Signed arithmetic: the deadline may be in the past.
  int64_t delta = static_cast<int64_t>(monoMs) - static_cast<int64_t>(nowMono);
  int64_t result = static_cast<int64_t>(nowEpoch) + delta;
  return result < 0 ? 0 : static_cast<uint64_t>(result);
}

uint64_t epochToMonotonicMs(uint64_t epoch) {
  uint64_t nowEpoch = epochMs();
  if (nowEpoch == 0 || epoch == 0) return 0;
  uint64_t nowMono = monotonicMs();
  int64_t delta = static_cast<int64_t>(epoch) - static_cast<int64_t>(nowEpoch);
  int64_t result = static_cast<int64_t>(nowMono) + delta;
  return result < 0 ? 0 : static_cast<uint64_t>(result);
}

// --------------------------------------------------------------------------- //
// ISO-8601 — implementation lives in include/iso8601.h so it can be host-tested
// --------------------------------------------------------------------------- //

uint64_t parseIso8601(const char *iso) { return iso8601::parse(iso); }

void formatIso8601(uint64_t epoch, char *out, size_t len) {
  iso8601::format(epoch, out, len);
}

// --------------------------------------------------------------------------- //
// Wall-clock scheduling
// --------------------------------------------------------------------------- //

uint8_t localWeekdayBit() {
  struct tm local {};
  if (!localTime(local)) return 0;
  // tm_wday: 0 = Sunday. Our mask is bit 0 = Monday.
  int isoIndex = (local.tm_wday + 6) % 7;
  return static_cast<uint8_t>(1u << isoIndex);
}

uint32_t secondsUntilLocalTimeOfDay(uint8_t hour, uint8_t minute,
                                    uint8_t daysOfWeekMask) {
  struct tm local {};
  if (!localTime(local)) return 0;

  long nowSecs = local.tm_hour * 3600L + local.tm_min * 60L + local.tm_sec;
  long targetSecs = hour * 3600L + minute * 60L;
  long delta = targetSecs - nowSecs;
  int dayOffset = 0;
  if (delta <= 0) {
    delta += 86400L;
    dayOffset = 1;
  }

  if (daysOfWeekMask != 0) {
    int isoToday = (local.tm_wday + 6) % 7;
    for (int i = 0; i < 8; ++i) {
      int candidate = (isoToday + dayOffset + i) % 7;
      if (daysOfWeekMask & (1u << candidate)) {
        delta += static_cast<long>(i) * 86400L;
        break;
      }
    }
  }

  return static_cast<uint32_t>(delta);
}

}  // namespace clocktime
