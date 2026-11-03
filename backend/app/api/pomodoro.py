"""Pomodoro endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from .. import events as ev
from .. import repo
from ..db import mongo
from ..deps import DeviceDep, UserDep
from ..models import FocusSession, RunState
from ..realtime import hub
from ..schemas import FocusSessionRead, PomodoroConfig, PomodoroRead, PomodoroStartRequest
from ..serializers import pomodoro_read
from ..services import pomodoro as pomodoro_service

router = APIRouter(prefix="/pomodoro", tags=["pomodoro"])


@router.get("/status", response_model=PomodoroRead)
async def status_(device: DeviceDep) -> PomodoroRead:
    return pomodoro_read(await pomodoro_service.get(device.id))


@router.post("/start", response_model=PomodoroRead)
async def start(device: DeviceDep, payload: PomodoroStartRequest) -> PomodoroRead:
    state = await pomodoro_service.get(device.id)
    state = await pomodoro_service.apply_config(
        state,
        focus_minutes=payload.focus_minutes,
        short_break_minutes=payload.short_break_minutes,
        long_break_minutes=payload.long_break_minutes,
        cycles_before_long_break=payload.cycles_before_long_break,
    )
    state = await pomodoro_service.start(state)
    read = pomodoro_read(state)
    await hub.publish(
        ev.POMODORO_STARTED,
        read.model_dump(mode="json"),
        device_id=device.id,
        origin=payload.source.value,
    )
    return read


@router.post("/pause", response_model=PomodoroRead)
async def pause(device: DeviceDep) -> PomodoroRead:
    state = await pomodoro_service.get(device.id)
    if state.state != RunState.RUNNING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pomodoro is not running")
    state = await pomodoro_service.pause(state)
    read = pomodoro_read(state)
    await hub.publish(ev.POMODORO_PAUSED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.post("/resume", response_model=PomodoroRead)
async def resume(device: DeviceDep) -> PomodoroRead:
    state = await pomodoro_service.get(device.id)
    if state.state != RunState.PAUSED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pomodoro is not paused")
    state = await pomodoro_service.resume(state)
    read = pomodoro_read(state)
    await hub.publish(ev.POMODORO_RESUMED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.post("/stop", response_model=PomodoroRead)
async def stop(device: DeviceDep) -> PomodoroRead:
    state = await pomodoro_service.stop(await pomodoro_service.get(device.id))
    read = pomodoro_read(state)
    await hub.publish(ev.POMODORO_STOPPED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.post("/skip", response_model=PomodoroRead)
async def skip(device: DeviceDep) -> PomodoroRead:
    state = await pomodoro_service.get(device.id)
    if state.state == RunState.IDLE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pomodoro is idle")
    change = await pomodoro_service.advance(state, natural=False)
    read = pomodoro_read(change.state)
    payload = read.model_dump(mode="json")
    payload["previous_phase"] = change.previous_phase
    await hub.publish(ev.POMODORO_SKIPPED, payload, device_id=device.id, origin="dashboard")
    return read


@router.patch("/config", response_model=PomodoroRead)
async def update_config(device: DeviceDep, payload: PomodoroConfig) -> PomodoroRead:
    state = await pomodoro_service.apply_config(
        await pomodoro_service.get(device.id),
        focus_minutes=payload.focus_minutes,
        short_break_minutes=payload.short_break_minutes,
        long_break_minutes=payload.long_break_minutes,
        cycles_before_long_break=payload.cycles_before_long_break,
    )
    read = pomodoro_read(state)
    await hub.publish(
        ev.SETTINGS_UPDATED,
        {"pomodoro": read.model_dump(mode="json")},
        device_id=device.id,
        origin="dashboard",
    )
    return read


@router.post("/reset-cycles", response_model=PomodoroRead)
async def reset_cycles(device: DeviceDep) -> PomodoroRead:
    state = await pomodoro_service.reset_cycles(await pomodoro_service.get(device.id))
    read = pomodoro_read(state)
    await hub.publish(ev.POMODORO_STOPPED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.get("/sessions", response_model=list[FocusSessionRead])
async def sessions(
    device: DeviceDep,
    user: UserDep,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[FocusSessionRead]:
    filt: dict = {}
    if user:
        filt["$or"] = [
            {"user_id": user.id},
            {"username": user.username},
            {"device_id": user.device_id},
        ]
    else:
        filt["device_id"] = device.id

    rows = await repo.find_many(
        mongo.focus_sessions,
        FocusSession,
        filt,
        sort=[("started_at", repo.DESC)],
        limit=limit,
    )
    return [FocusSessionRead.model_validate(row.model_dump()) for row in rows]
