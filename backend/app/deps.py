"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status

from . import repo
from .config import settings
from .db import mongo
from .models import Device, PomodoroState, Stopwatch


async def require_db() -> None:
    """Fail fast with an explanation instead of a 500 from deep in the driver."""
    if not mongo.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=mongo.error or "Database is not connected",
        )


async def ensure_child_docs(device_id: str) -> None:
    """Stopwatch and Pomodoro are singleton-per-device; create on first touch."""
    await repo.get_or_create(
        mongo.stopwatches, Stopwatch, device_id, lambda: Stopwatch(id=device_id)
    )
    await repo.get_or_create(
        mongo.pomodoro_states, PomodoroState, device_id, lambda: PomodoroState(id=device_id)
    )


async def get_device(
    device_id: str = Query(
        default=settings.default_device_id,
        description="Target device. Defaults to the configured device.",
    ),
) -> Device:
    await require_db()
    device = await repo.find_by_id(mongo.devices, Device, device_id)
    if device is None:
        device = await repo.get_or_create(
            mongo.devices, Device, device_id, lambda: Device(id=device_id, name=device_id)
        )
    await ensure_child_docs(device_id)
    return device


async def get_or_create_device(device_id: str, name: str | None = None) -> Device:
    """Used by device-facing paths so a fresh ESP32 can self-register."""
    device = await repo.get_or_create(
        mongo.devices, Device, device_id, lambda: Device(id=device_id, name=name or device_id)
    )
    await ensure_child_docs(device_id)
    return device


DeviceDep = Annotated[Device, Depends(get_device)]
DbDep = Annotated[None, Depends(require_db)]
