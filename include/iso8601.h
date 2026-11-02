#pragma once
/**
 * ISO-8601 <-> UTC epoch conversion. Header-only, freestanding C++ with no
 * Arduino or ESP-IDF dependency.
 *
 * Deliberately separated from clock_time.cpp so it can be compiled and tested on
 * a host machine. Every deadline the backend sends arrives as a string and is
 * parsed here; an off-by-one in the calendar maths would silently shift timers by
 * a day, which is exactly the kind of bug that does not show up until it does.
 *
 * Host test: test/host/test_iso8601.cpp
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

namespace iso8601 {

/**
 * Days since 1970-01-01 for a proleptic Gregorian date.
 * Howard Hinnant's days_from_civil: exact integer maths, no loops, and no
 * dependency on timegm() — which newlib on the ESP32 does not provide.
 */
inline int64_t daysFromCivil(int64_t y, unsigned m, unsigned d) {
  y -= m <= 2;
  const int64_t era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = static_cast<unsigned>(y - era * 400);          // 0..399
  const unsigned doy = (153u * (m + (m > 2 ? -3u : 9u)) + 2u) / 5u + d - 1u;
  const unsigned doe = yoe * 365u + yoe / 4u - yoe / 100u + doy;      // 0..146096
  return era * 146097 + static_cast<int64_t>(doe) - 719468;
}

/** Inverse of daysFromCivil. */
inline void civilFromDays(int64_t z, int &year, unsigned &month, unsigned &day) {
  z += 719468;
  const int64_t era = (z >= 0 ? z : z - 146096) / 146097;
  const unsigned doe = static_cast<unsigned>(z - era * 146097);
  const unsigned yoe = (doe - doe / 1460u + doe / 36524u - doe / 146096u) / 365u;
  const int64_t y = static_cast<int64_t>(yoe) + era * 400;
  const unsigned doy = doe - (365u * yoe + yoe / 4u - yoe / 100u);
  const unsigned mp = (5u * doy + 2u) / 153u;
  day = doy - (153u * mp + 2u) / 5u + 1u;
  month = mp + (mp < 10u ? 3u : -9u);
  year = static_cast<int>(y + (month <= 2u));
}

/**
 * Parse "2026-09-22T11:47:31.553990Z", with or without fractional seconds, and
 * with either "Z" or a "+HH:MM" / "-HH:MM" offset.
 * Returns UTC milliseconds since the epoch, or 0 if the input is unusable.
 * 0 doubles as "no value" because the backend sends null, never 1970.
 */
inline uint64_t parse(const char *text) {
  if (text == nullptr || *text == '\0') return 0;

  int year = 0, month = 0, day = 0, hour = 0, minute = 0, second = 0;
  if (sscanf(text, "%4d-%2d-%2dT%2d:%2d:%2d", &year, &month, &day, &hour, &minute,
             &second) != 6) {
    return 0;
  }
  if (year < 1970 || month < 1 || month > 12 || day < 1 || day > 31) return 0;
  if (hour > 23 || minute > 59 || second > 60) return 0;

  unsigned millis = 0;
  const char *timePart = strchr(text, 'T');
  if (timePart != nullptr) {
    const char *dot = strchr(timePart, '.');
    if (dot != nullptr) {
      unsigned scale = 100;
      for (const char *p = dot + 1; *p >= '0' && *p <= '9' && scale > 0; ++p) {
        millis += static_cast<unsigned>(*p - '0') * scale;
        scale /= 10;
      }
    }
  }

  int64_t days = daysFromCivil(year, static_cast<unsigned>(month),
                               static_cast<unsigned>(day));
  int64_t seconds = days * 86400LL + hour * 3600LL + minute * 60LL + second;

  // A trailing numeric offset means the timestamp is local: shift it to UTC.
  const size_t length = strlen(text);
  if (length >= 6) {
    const char sign = text[length - 6];
    if ((sign == '+' || sign == '-') && text[length - 3] == ':') {
      const int offsetHour = atoi(text + length - 5);
      const int offsetMinute = atoi(text + length - 2);
      const int64_t offset = offsetHour * 3600LL + offsetMinute * 60LL;
      seconds += (sign == '+') ? -offset : offset;
    }
  }

  if (seconds < 0) return 0;
  return static_cast<uint64_t>(seconds) * 1000ULL + millis;
}

/** Format UTC epoch milliseconds as "YYYY-MM-DDTHH:MM:SS.mmmZ". */
inline void format(uint64_t epochMs, char *out, size_t length) {
  if (out == nullptr || length == 0) return;
  if (epochMs == 0) {
    out[0] = '\0';
    return;
  }

  const int64_t totalSeconds = static_cast<int64_t>(epochMs / 1000ULL);
  const unsigned millis = static_cast<unsigned>(epochMs % 1000ULL);

  int64_t days = totalSeconds / 86400;
  int64_t rest = totalSeconds % 86400;
  if (rest < 0) {
    rest += 86400;
    --days;
  }

  int year = 1970;
  unsigned month = 1;
  unsigned day = 1;
  civilFromDays(days, year, month, day);

  snprintf(out, length, "%04d-%02u-%02uT%02u:%02u:%02u.%03uZ", year, month, day,
           static_cast<unsigned>(rest / 3600), static_cast<unsigned>((rest % 3600) / 60),
           static_cast<unsigned>(rest % 60), millis);
}

}  // namespace iso8601
