"""Productivity aggregation for the dashboard analytics page.

Totals come from a Mongo `$group` pipeline so they do not grow with history.
The per-day series needs day boundaries in the *device's* local timezone — "focus
minutes today" should mean the user's today, not UTC's — so that part fetches a
bounded window and buckets in Python. Doing the offset arithmetic in an
aggregation is possible but much harder to read for no practical gain at this
scale.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from .. import repo
from ..db import mongo
from ..models import FocusSession, SessionKind, Task, User
from ..schemas import AnalyticsRead, DailyPoint
from ..utils import as_utc, utcnow
from .alarms import tz_offset_for


def _local_date(value: Optional[datetime], offset_minutes: int) -> Optional[date]:
    aware = as_utc(value)
    if aware is None:
        return None
    return (aware + timedelta(minutes=offset_minutes)).date()


async def build(
    device_id: str, range_days: int = 7, user: Optional[User] = None
) -> AnalyticsRead:
    range_days = max(1, min(range_days, 90))
    offset = await tz_offset_for(device_id)

    today = _local_date(utcnow(), offset)
    assert today is not None
    window_start_local = today - timedelta(days=range_days - 1)
    # Widen the UTC cutoff by a day so a large timezone offset cannot clip the
    # first local day of the window.
    cutoff_utc = datetime.combine(
        window_start_local - timedelta(days=1), datetime.min.time()
    ).replace(tzinfo=utcnow().tzinfo)

    focus_kind = SessionKind.POMODORO_FOCUS.value

    # Match condition for user or device
    if user:
        user_match = {
            "$or": [
                {"user_id": user.id},
                {"username": user.username},
                {"device_id": user.device_id},
            ]
        }
    else:
        user_match = {"device_id": device_id}

    # --- all-time totals, server-side -------------------------------------- #
    totals_pipeline = [
        {"$match": {**user_match, "kind": focus_kind}},
        {
            "$group": {
                "_id": None,
                "seconds": {"$sum": "$actual_seconds"},
                "sessions": {"$sum": 1},
            }
        },
    ]
    focus_total_seconds = 0
    sessions_total = 0
    async for row in await mongo.focus_sessions.aggregate(totals_pipeline):
        focus_total_seconds = int(row.get("seconds") or 0)
        sessions_total = int(row.get("sessions") or 0)

    # --- bounded window for the daily series ------------------------------- #
    windowed = await repo.find_many(
        mongo.focus_sessions,
        FocusSession,
        {**user_match, "kind": focus_kind, "started_at": {"$gte": cutoff_utc}},
        sort=[("started_at", repo.ASC)],
        limit=2000,
    )

    buckets: dict[date, DailyPoint] = {}
    for offset_days in range(range_days):
        day = window_start_local + timedelta(days=offset_days)
        buckets[day] = DailyPoint(date=day.isoformat())

    focus_today_seconds = 0
    sessions_today = 0
    cycles_today = 0

    for session in windowed:
        day = _local_date(session.started_at, offset)
        if day is None:
            continue
        seconds = max(session.actual_seconds, 0)
        if day == today:
            focus_today_seconds += seconds
            sessions_today += 1
            if session.completed:
                cycles_today += 1
        point = buckets.get(day)
        if point is not None:
            point.focus_minutes += seconds // 60
            point.sessions += 1

    # --- tasks ------------------------------------------------------------- #
    tasks_open = await mongo.tasks.count_documents({**user_match, "done": False})
    tasks_completed_total = await mongo.tasks.count_documents(
        {**user_match, "done": True}
    )

    completed = await repo.find_many(
        mongo.tasks,
        Task,
        {**user_match, "done": True, "completed_at": {"$gte": cutoff_utc}},
        limit=2000,
    )
    tasks_completed_today = 0
    for task in completed:
        day = _local_date(task.completed_at, offset)
        if day == today:
            tasks_completed_today += 1
        point = buckets.get(day) if day else None
        if point is not None:
            point.tasks_completed += 1

    voice_total = await mongo.voice_commands.count_documents({"device_id": device_id})

    # --- streak ------------------------------------------------------------ #
    # Count back from today over days that had any recorded focus. Bounded to a
    # year so a long history cannot turn this into a full scan.
    streak_cutoff = datetime.combine(
        today - timedelta(days=366), datetime.min.time()
    ).replace(tzinfo=utcnow().tzinfo)
    streak_pipeline = [
        {
            "$match": {
                "device_id": device_id,
                "kind": focus_kind,
                "actual_seconds": {"$gt": 0},
                "started_at": {"$gte": streak_cutoff},
            }
        },
        {"$project": {"started_at": 1}},
    ]
    active_days: set[date] = set()
    async for row in await mongo.focus_sessions.aggregate(streak_pipeline):
        day = _local_date(row.get("started_at"), offset)
        if day is not None:
            active_days.add(day)

    streak = 0
    cursor = today
    while cursor in active_days:
        streak += 1
        cursor -= timedelta(days=1)

    return AnalyticsRead(
        range_days=range_days,
        focus_minutes_today=focus_today_seconds // 60,
        focus_minutes_total=focus_total_seconds // 60,
        sessions_today=sessions_today,
        sessions_total=sessions_total,
        tasks_completed_today=tasks_completed_today,
        tasks_open=tasks_open,
        tasks_completed_total=tasks_completed_total,
        pomodoro_cycles_today=cycles_today,
        current_streak_days=streak,
        voice_commands_total=voice_total,
        daily=[buckets[day] for day in sorted(buckets)],
    )
