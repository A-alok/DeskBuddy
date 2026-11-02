"""Small time helpers shared across the app.

SQLite does not persist tzinfo, so datetimes read back from the DB come out
naive. Everything we store is UTC, so `as_utc()` re-attaches that fact before
any comparison or arithmetic. Getting this wrong is the classic source of
"timer finished instantly" bugs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to an aware UTC datetime."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: Optional[datetime]) -> Optional[str]:
    """ISO-8601 string with a trailing Z, or None."""
    aware = as_utc(value)
    if aware is None:
        return None
    return aware.isoformat().replace("+00:00", "Z")


def seconds_until(target: Optional[datetime], *, floor_at_zero: bool = True) -> int:
    """Whole seconds from now until `target`."""
    aware = as_utc(target)
    if aware is None:
        return 0
    delta = (aware - utcnow()).total_seconds()
    if floor_at_zero and delta < 0:
        return 0
    return int(round(delta))


def in_seconds(seconds: float) -> datetime:
    return utcnow() + timedelta(seconds=seconds)


def parse_hhmm(value: str) -> tuple[int, int]:
    """Parse 'HH:MM' into (hour, minute). Raises ValueError when malformed."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM, got {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time out of range: {value!r}")
    return hour, minute


def next_occurrence(
    time_of_day: str,
    days_of_week: list[int] | None,
    *,
    tz_offset_minutes: int = 0,
    reference: Optional[datetime] = None,
) -> datetime:
    """Next UTC instant matching a wall-clock time on the device.

    `tz_offset_minutes` is the device's offset from UTC (e.g. +330 for IST).
    An empty `days_of_week` means "the next time that clock time comes around".
    """
    hour, minute = parse_hhmm(time_of_day)
    ref_utc = as_utc(reference) or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    local_now = ref_utc + offset

    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)

    if days_of_week:
        allowed = {d % 7 for d in days_of_week}
        for _ in range(8):
            if candidate.weekday() in allowed:
                break
            candidate += timedelta(days=1)

    return (candidate - offset).astimezone(timezone.utc)
