"""Timer domain logic — absolute end timestamps, no server-side ticking."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from .. import repo
from ..db import mongo
from ..models import RunState, Timer
from ..utils import as_utc, in_seconds, seconds_until, utcnow

ACTIVE_STATES = [RunState.IDLE.value, RunState.RUNNING.value, RunState.PAUSED.value]


async def _latest(device_id: str, extra: Optional[dict] = None) -> Optional[Timer]:
    filt: dict = {"device_id": device_id}
    if extra:
        filt.update(extra)
    found = await repo.find_many(
        mongo.timers, Timer, filt, sort=[("created_at", repo.DESC)], limit=1
    )
    return found[0] if found else None


async def get_active(device_id: str) -> Optional[Timer]:
    """The timer a client should be showing, if any."""
    return await _latest(device_id, {"state": {"$in": ACTIVE_STATES}})


async def get_latest(device_id: str) -> Optional[Timer]:
    return await _latest(device_id)


async def list_recent(device_id: str, limit: int = 20) -> list[Timer]:
    return await repo.find_many(
        mongo.timers,
        Timer,
        {"device_id": device_id},
        sort=[("created_at", repo.DESC)],
        limit=limit,
    )


async def get(timer_id: str) -> Optional[Timer]:
    return await repo.find_by_id(mongo.timers, Timer, timer_id)


async def start(device_id: str, duration_seconds: int, label: str = "Timer") -> Timer:
    """Cancel whatever is active and start a fresh timer."""
    if duration_seconds < 1:
        raise ValueError("duration_seconds must be at least 1")

    # One active timer per device: retire the previous one in a single write.
    await mongo.timers.update_many(
        {"device_id": device_id, "state": {"$in": ACTIVE_STATES}},
        {
            "$set": {
                "state": RunState.CANCELLED.value,
                "ends_at": None,
                "remaining_seconds": None,
                "updated_at": utcnow(),
            }
        },
    )

    now = utcnow()
    timer = Timer(
        device_id=device_id,
        label=label or "Timer",
        duration_seconds=duration_seconds,
        state=RunState.RUNNING,
        ends_at=now + timedelta(seconds=duration_seconds),
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    await repo.insert(mongo.timers, timer)
    return timer


async def pause(timer: Timer) -> Timer:
    if timer.state != RunState.RUNNING:
        return timer
    changes = {
        "remaining_seconds": seconds_until(timer.ends_at),
        "state": RunState.PAUSED.value,
        "ends_at": None,
        "updated_at": utcnow(),
    }
    updated = await repo.patch(mongo.timers, Timer, timer.id, changes)
    return updated or timer


async def resume(timer: Timer) -> Timer:
    if timer.state != RunState.PAUSED:
        return timer
    remaining = timer.remaining_seconds or 0
    if remaining <= 0:
        return await finish(timer)
    changes = {
        "state": RunState.RUNNING.value,
        "ends_at": in_seconds(remaining),
        "remaining_seconds": None,
        "updated_at": utcnow(),
    }
    updated = await repo.patch(mongo.timers, Timer, timer.id, changes)
    return updated or timer


async def cancel(timer: Timer) -> Timer:
    changes = {
        "state": RunState.CANCELLED.value,
        "ends_at": None,
        "remaining_seconds": None,
        "updated_at": utcnow(),
    }
    updated = await repo.patch(mongo.timers, Timer, timer.id, changes)
    return updated or timer


async def add_seconds(timer: Timer, delta: int) -> Timer:
    """Extend or shorten a running/paused timer."""
    changes: dict = {"updated_at": utcnow()}

    if timer.state == RunState.RUNNING:
        current = seconds_until(timer.ends_at)
        new_remaining = max(current + delta, 1)
        changes["ends_at"] = in_seconds(new_remaining)
    elif timer.state == RunState.PAUSED:
        changes["remaining_seconds"] = max((timer.remaining_seconds or 0) + delta, 0)
    else:
        return timer

    changes["duration_seconds"] = max(timer.duration_seconds + delta, 1)
    updated = await repo.patch(mongo.timers, Timer, timer.id, changes)
    return updated or timer


async def finish(timer: Timer) -> Timer:
    now = utcnow()
    changes = {
        "state": RunState.FINISHED.value,
        "ends_at": None,
        "remaining_seconds": 0,
        "finished_at": now,
        "updated_at": now,
    }
    updated = await repo.patch(mongo.timers, Timer, timer.id, changes)
    return updated or timer


async def due_timers() -> list[Timer]:
    """Running timers whose absolute end instant has passed.

    Indexed on (state, ends_at), so the scheduler's once-a-second question is a
    bounded index scan rather than a collection walk.
    """
    candidates = await repo.find_many(
        mongo.timers,
        Timer,
        {"state": RunState.RUNNING.value, "ends_at": {"$lte": utcnow()}},
        limit=50,
    )
    now = utcnow()
    return [t for t in candidates if (ends := as_utc(t.ends_at)) is not None and ends <= now]
