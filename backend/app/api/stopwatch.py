"""Stopwatch endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from .. import events as ev
from ..deps import DeviceDep
from ..realtime import hub
from ..schemas import StopwatchRead
from ..serializers import stopwatch_read
from ..services import stopwatch as stopwatch_service

router = APIRouter(prefix="/stopwatch", tags=["stopwatch"])


async def _broadcast(device_id: str, event: str, read: StopwatchRead) -> StopwatchRead:
    await hub.publish(event, read.model_dump(mode="json"), device_id=device_id, origin="dashboard")
    return read


@router.get("/status", response_model=StopwatchRead)
async def stopwatch_status(device: DeviceDep) -> StopwatchRead:
    return stopwatch_read(await stopwatch_service.get(device.id))


@router.post("/start", response_model=StopwatchRead)
async def start(device: DeviceDep) -> StopwatchRead:
    sw = await stopwatch_service.start(device.id)
    return await _broadcast(device.id, ev.STOPWATCH_STARTED, stopwatch_read(sw))


@router.post("/stop", response_model=StopwatchRead)
async def stop(device: DeviceDep) -> StopwatchRead:
    sw = await stopwatch_service.stop(device.id)
    return await _broadcast(device.id, ev.STOPWATCH_STOPPED, stopwatch_read(sw))


@router.post("/lap", response_model=StopwatchRead)
async def lap(device: DeviceDep) -> StopwatchRead:
    sw = await stopwatch_service.lap(device.id)
    return await _broadcast(device.id, ev.STOPWATCH_LAPPED, stopwatch_read(sw))


@router.post("/reset", response_model=StopwatchRead)
async def reset(device: DeviceDep) -> StopwatchRead:
    sw = await stopwatch_service.reset(device.id)
    return await _broadcast(device.id, ev.STOPWATCH_RESET, stopwatch_read(sw))
