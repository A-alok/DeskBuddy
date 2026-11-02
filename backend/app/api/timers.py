"""Timer endpoints.

Every mutation returns the full timer object AND broadcasts the same object as an
event, so a client that issued the request and a client that only listens end up
in exactly the same state.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, status

from .. import events as ev
from ..deps import DeviceDep
from ..models import Timer
from ..realtime import hub
from ..schemas import TimerCreate, TimerRead
from ..serializers import timer_read
from ..services import timers as timer_service

router = APIRouter(prefix="/timer", tags=["timer"])


async def _require_active(device_id: str) -> Timer:
    timer = await timer_service.get_active(device_id)
    if timer is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active timer")
    return timer


@router.get("/status", response_model=Optional[TimerRead])
async def timer_status(device: DeviceDep) -> Optional[TimerRead]:
    timer = await timer_service.get_active(device.id)
    return timer_read(timer) if timer else None


@router.get("/history", response_model=list[TimerRead])
async def timer_history(
    device: DeviceDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[TimerRead]:
    timers = await timer_service.list_recent(device.id, limit)
    return [timer_read(t) for t in timers]


@router.post("/start", response_model=TimerRead, status_code=status.HTTP_201_CREATED)
async def start_timer(device: DeviceDep, payload: TimerCreate) -> TimerRead:
    total = payload.total_seconds()
    if total < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Timer duration must be at least 1 second",
        )
    timer = await timer_service.start(device.id, total, payload.label)
    read = timer_read(timer)
    await hub.publish(
        ev.TIMER_STARTED,
        read.model_dump(mode="json"),
        device_id=device.id,
        origin=payload.source.value,
    )
    return read


@router.post("/pause", response_model=TimerRead)
async def pause_timer(device: DeviceDep) -> TimerRead:
    timer = await timer_service.pause(await _require_active(device.id))
    read = timer_read(timer)
    await hub.publish(ev.TIMER_PAUSED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.post("/resume", response_model=TimerRead)
async def resume_timer(device: DeviceDep) -> TimerRead:
    timer = await timer_service.resume(await _require_active(device.id))
    read = timer_read(timer)
    await hub.publish(ev.TIMER_RESUMED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.post("/stop", response_model=TimerRead)
async def stop_timer(device: DeviceDep) -> TimerRead:
    """Cancel the active timer (the API plan calls this /timer/stop)."""
    timer = await timer_service.cancel(await _require_active(device.id))
    read = timer_read(timer)
    await hub.publish(ev.TIMER_CANCELLED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.post("/extend", response_model=TimerRead)
async def extend_timer(
    device: DeviceDep,
    seconds: int = Body(default=60, embed=True, ge=-3600, le=3600),
) -> TimerRead:
    timer = await timer_service.add_seconds(await _require_active(device.id), seconds)
    read = timer_read(timer)
    await hub.publish(
        ev.TIMER_STARTED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard"
    )
    return read
