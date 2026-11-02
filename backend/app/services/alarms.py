"""Alarm and reminder scheduling helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .. import repo
from ..db import mongo
from ..models import Alarm, Reminder, Setting
from ..utils import next_occurrence, utcnow

# Device timezone offset in minutes. Alarms are wall-clock on the device, so the
# backend needs the offset to compute an absolute next fire time. Stored as a
# per-device setting ("tz_offset_minutes"); defaults to UTC.
DEFAULT_TZ_OFFSET_MINUTES = 0


async def tz_offset_for(device_id: str) -> int:
    doc = await mongo.settings_store.find_one(
        {"_id": Setting.make_id(device_id, "tz_offset_minutes")}
    )
    if doc is None or doc.get("value") is None:
        return DEFAULT_TZ_OFFSET_MINUTES
    try:
        return int(doc["value"])
    except (TypeError, ValueError):
        return DEFAULT_TZ_OFFSET_MINUTES


async def compute_next_trigger(
    alarm: Alarm, *, tz_offset: Optional[int] = None
) -> Optional[datetime]:
    if not alarm.enabled:
        return None
    offset = tz_offset if tz_offset is not None else await tz_offset_for(alarm.device_id)
    return next_occurrence(
        alarm.time_of_day, list(alarm.days_of_week or []), tz_offset_minutes=offset
    )


async def recompute_next_trigger(alarm: Alarm) -> Alarm:
    alarm.next_trigger_at = await compute_next_trigger(alarm)
    return alarm


async def list_for_device(device_id: str) -> list[Alarm]:
    alarms = await repo.find_many(
        mongo.alarms, Alarm, {"device_id": device_id}, sort=[("time_of_day", repo.ASC)]
    )
    # Backfill any alarm missing a computed trigger (e.g. created by firmware).
    offset = await tz_offset_for(device_id)
    for alarm in alarms:
        if alarm.enabled and alarm.next_trigger_at is None:
            alarm.next_trigger_at = await compute_next_trigger(alarm, tz_offset=offset)
            await repo.patch(
                mongo.alarms, Alarm, alarm.id, {"next_trigger_at": alarm.next_trigger_at}
            )
    return alarms


async def get(alarm_id: str) -> Optional[Alarm]:
    return await repo.find_by_id(mongo.alarms, Alarm, alarm_id)


async def due_alarms() -> list[Alarm]:
    """Enabled alarms whose absolute next trigger has passed. Uses the index."""
    return await repo.find_many(
        mongo.alarms,
        Alarm,
        {"enabled": True, "next_trigger_at": {"$ne": None, "$lte": utcnow()}},
        limit=50,
    )


async def mark_triggered(alarm: Alarm) -> Alarm:
    now = utcnow()
    changes: dict = {"last_triggered_at": now}

    if alarm.days_of_week:
        # Repeating: roll forward to the next matching day.
        offset = await tz_offset_for(alarm.device_id)
        changes["next_trigger_at"] = next_occurrence(
            alarm.time_of_day, list(alarm.days_of_week), tz_offset_minutes=offset
        )
    else:
        # One-shot: disable so it does not fire again tomorrow.
        changes["enabled"] = False
        changes["next_trigger_at"] = None

    updated = await repo.patch(mongo.alarms, Alarm, alarm.id, changes)
    return updated or alarm


# --------------------------------------------------------------------------- #
# Reminders
# --------------------------------------------------------------------------- #


async def due_reminders() -> list[Reminder]:
    return await repo.find_many(
        mongo.reminders,
        Reminder,
        {"done": False, "notified_at": None, "remind_at": {"$lte": utcnow()}},
        limit=50,
    )


async def mark_notified(reminder: Reminder) -> Reminder:
    updated = await repo.patch(
        mongo.reminders, Reminder, reminder.id, {"notified_at": utcnow()}
    )
    return updated or reminder
