/**
 * Host test for include/iso8601.h — the calendar maths every remote deadline
 * passes through. Runs on your PC, no board needed:
 *
 *   g++ -std=c++17 -Wall -Wextra -I include test/host/test_iso8601.cpp -o iso_test
 *   ./iso_test
 *
 * PlatformIO ignores test/ during `pio run`, so this does not affect the
 * firmware build.
 */

#include <cstdio>
#include <cstring>
#include <string>

#include "iso8601.h"

static int failures = 0;
static int checks = 0;

static void expectEq(const char *label, uint64_t actual, uint64_t expected) {
  ++checks;
  if (actual == expected) {
    printf("[PASS] %s\n", label);
  } else {
    printf("[FAIL] %s  expected %llu, got %llu\n", label,
           static_cast<unsigned long long>(expected),
           static_cast<unsigned long long>(actual));
    ++failures;
  }
}

static void expectStr(const char *label, const char *actual, const char *expected) {
  ++checks;
  if (strcmp(actual, expected) == 0) {
    printf("[PASS] %s\n", label);
  } else {
    printf("[FAIL] %s  expected \"%s\", got \"%s\"\n", label, expected, actual);
    ++failures;
  }
}

static void expectTrue(const char *label, bool condition) {
  ++checks;
  if (condition) {
    printf("[PASS] %s\n", label);
  } else {
    printf("[FAIL] %s\n", label);
    ++failures;
  }
}

int main() {
  // --- known epoch anchors ------------------------------------------------- //
  expectEq("epoch itself", iso8601::parse("1970-01-01T00:00:00Z"), 0ULL);
  expectEq("2001-09-09T01:46:40Z = 1000000000s",
           iso8601::parse("2001-09-09T01:46:40Z"), 1000000000000ULL);
  expectEq("2009-02-13T23:31:30Z = 1234567890s",
           iso8601::parse("2009-02-13T23:31:30Z"), 1234567890000ULL);
  expectEq("2038 past the 32-bit cliff",
           iso8601::parse("2038-01-19T03:14:08Z"), 2147483648000ULL);

  // --- milliseconds -------------------------------------------------------- //
  // Anchors cross-checked against Python's datetime, not derived by hand.
  expectEq("3-digit fraction", iso8601::parse("2026-09-22T11:47:31.553Z"),
           1790077651553ULL);
  expectEq("6-digit fraction truncates to ms (backend sends this)",
           iso8601::parse("2026-09-22T11:47:31.553990Z"), 1790077651553ULL);
  expectEq("1-digit fraction scales", iso8601::parse("2026-09-22T11:47:31.5Z"),
           1790077651500ULL);
  expectEq("no fraction", iso8601::parse("2026-09-22T11:47:31Z"), 1790077651000ULL);

  // --- leap years: the classic off-by-a-day source ------------------------- //
  expectEq("2024-02-29 exists (div by 4)", iso8601::parse("2024-02-29T00:00:00Z"),
           1709164800000ULL);
  expectEq("2000-02-29 exists (div by 400)", iso8601::parse("2000-02-29T00:00:00Z"),
           951782400000ULL);
  expectTrue("2100-03-01 follows 2100-02-28 (no 29th)",
             iso8601::parse("2100-03-01T00:00:00Z") -
                     iso8601::parse("2100-02-28T00:00:00Z") ==
                 86400000ULL);
  expectTrue("2024-03-01 is two days after 2024-02-28 (leap)",
             iso8601::parse("2024-03-01T00:00:00Z") -
                     iso8601::parse("2024-02-28T00:00:00Z") ==
                 2ULL * 86400000ULL);

  // --- month boundaries ---------------------------------------------------- //
  expectTrue("Dec 31 -> Jan 1 is one day",
             iso8601::parse("2027-01-01T00:00:00Z") -
                     iso8601::parse("2026-12-31T00:00:00Z") ==
                 86400000ULL);
  expectTrue("every month length is 28..31 days", [] {
    static const int expected[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    for (int month = 1; month <= 12; ++month) {
      char start[32];
      char next[32];
      snprintf(start, sizeof(start), "2026-%02d-01T00:00:00Z", month);
      if (month == 12) {
        snprintf(next, sizeof(next), "2027-01-01T00:00:00Z");
      } else {
        snprintf(next, sizeof(next), "2026-%02d-01T00:00:00Z", month + 1);
      }
      uint64_t days = (iso8601::parse(next) - iso8601::parse(start)) / 86400000ULL;
      if (static_cast<int>(days) != expected[month - 1]) return false;
    }
    return true;
  }());

  // --- explicit offsets ---------------------------------------------------- //
  expectEq("+05:30 shifts back to UTC", iso8601::parse("2026-09-22T17:17:31+05:30"),
           iso8601::parse("2026-09-22T11:47:31Z"));
  expectEq("-08:00 shifts forward to UTC",
           iso8601::parse("2026-09-22T03:47:31-08:00"),
           iso8601::parse("2026-09-22T11:47:31Z"));

  // --- rejection: 0 means "no value", never 1970 --------------------------- //
  expectEq("null pointer", iso8601::parse(nullptr), 0ULL);
  expectEq("empty string", iso8601::parse(""), 0ULL);
  expectEq("not a timestamp", iso8601::parse("tomorrow"), 0ULL);
  expectEq("date with no time", iso8601::parse("2026-09-22"), 0ULL);
  expectEq("month 13", iso8601::parse("2026-13-01T00:00:00Z"), 0ULL);
  expectEq("day 32", iso8601::parse("2026-09-32T00:00:00Z"), 0ULL);
  expectEq("hour 24", iso8601::parse("2026-09-22T24:00:00Z"), 0ULL);
  expectEq("minute 60", iso8601::parse("2026-09-22T11:60:00Z"), 0ULL);
  expectEq("pre-epoch year", iso8601::parse("1969-12-31T23:59:59Z"), 0ULL);

  // --- format -------------------------------------------------------------- //
  char buffer[40];
  iso8601::format(1790077651553ULL, buffer, sizeof(buffer));
  expectStr("format matches backend shape", buffer, "2026-09-22T11:47:31.553Z");

  iso8601::format(0ULL, buffer, sizeof(buffer));
  expectStr("format of 0 is empty", buffer, "");

  iso8601::format(1709164800000ULL, buffer, sizeof(buffer));
  expectStr("format handles the leap day", buffer, "2024-02-29T00:00:00.000Z");

  // --- round trip over a decade of days ------------------------------------ //
  expectTrue("round trip is stable across 4000 days", [&] {
    for (uint64_t day = 0; day < 4000; ++day) {
      uint64_t epoch = 1600000000000ULL + day * 86400000ULL + 3661000ULL;
      char text[40];
      iso8601::format(epoch, text, sizeof(text));
      if (iso8601::parse(text) != epoch) {
        printf("       mismatch at %s\n", text);
        return false;
      }
    }
    return true;
  }());

  printf("\n%d checks, %d failure(s)\n", checks, failures);
  return failures == 0 ? 0 : 1;
}
