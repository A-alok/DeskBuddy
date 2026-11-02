"""Stopwatch domain logic.

Stored as `accumulated_ms` (time banked from earlier segments) plus `started_at`
(the instant the current segment began). Elapsed time is derived, so a client
that reconnects mid-run lands on the correct value immediately.
"""

from __future__ import annotations

from .. import repo
from ..db import mongo
from ..models import RunState, Stopwatch
from ..utils import as_utc, utcnow


async def get(device_id: str) -> Stopwatch:
    return await repo.get_or_create(
        mongo.stopwatches, Stopwatch, device_id, lambda: Stopwatch(id=device_id)
    )


def _segment_ms(sw: Stopwatch) -> int:
    if sw.state != RunState.RUNNING or sw.started_at is None:
        return 0
    started = as_utc(sw.started_at)
    if started is None:
        return 0
    return max(int((utcnow() - started).total_seconds() * 1000), 0)


def elapsed_ms(sw: Stopwatch) -> int:
    return max(sw.accumulated_ms + _segment_ms(sw), 0)


async def _apply(device_id: str, changes: dict) -> Stopwatch:
    changes["updated_at"] = utcnow()
    updated = await repo.patch(mongo.stopwatches, Stopwatch, device_id, changes)
    return updated or await get(device_id)


async def start(device_id: str) -> Stopwatch:
    sw = await get(device_id)
    if sw.state == RunState.RUNNING:
        return sw
    return await _apply(
        device_id, {"state": RunState.RUNNING.value, "started_at": utcnow()}
    )


async def stop(device_id: str) -> Stopwatch:
    sw = await get(device_id)
    if sw.state != RunState.RUNNING:
        return sw
    return await _apply(
        device_id,
        {
            "accumulated_ms": elapsed_ms(sw),
            "state": RunState.PAUSED.value,
            "started_at": None,
        },
    )


async def lap(device_id: str) -> Stopwatch:
    sw = await get(device_id)
    if sw.state != RunState.RUNNING:
        return sw
    return await _apply(device_id, {"laps": [*(sw.laps or []), elapsed_ms(sw)]})


async def reset(device_id: str) -> Stopwatch:
    return await _apply(
        device_id,
        {
            "state": RunState.IDLE.value,
            "started_at": None,
            "accumulated_ms": 0,
            "laps": [],
        },
    )
