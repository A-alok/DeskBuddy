"""Shared FastAPI dependencies."""

from __future__ import annotations

import re
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Query, Request, status

from . import repo
from .config import settings
from .db import mongo
from .models import Device, PomodoroState, Stopwatch, User
from .realtime import hub


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


async def get_current_user_optional(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_username: Optional[str] = Header(default=None, alias="X-Username"),
    user_id: Optional[str] = Query(default=None),
    username: Optional[str] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
) -> Optional[User]:
    """Resolve the active user identity from token, headers, query, or linked device."""
    if not mongo.ready:
        return None

    # 1. Bearer Token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            user_doc = await mongo.users.find_one({"auth_token": token})
            if user_doc:
                return User.model_validate(user_doc)

    # 2. X-User-Id or user_id query
    target_uid = x_user_id or user_id
    if target_uid:
        user_doc = await mongo.users.find_one({"_id": target_uid})
        if user_doc:
            return User.model_validate(user_doc)

    # 3. X-Username or username query
    target_uname = x_username or username
    if target_uname:
        user_doc = await mongo.users.find_one({
            "username": {"$regex": f"^{re.escape(target_uname.strip())}$", "$options": "i"}
        })
        if user_doc:
            return User.model_validate(user_doc)

    # 4. Resolve by device_id
    if device_id:
        # Direct user device link (e.g. dev-alok17 -> alok17)
        user_doc = await mongo.users.find_one({"device_id": device_id})
        if user_doc:
            return User.model_validate(user_doc)

        dev_doc = await mongo.devices.find_one({"_id": device_id})
        if dev_doc and dev_doc.get("user_id"):
            user_doc = await mongo.users.find_one({"_id": dev_doc["user_id"]})
            if user_doc:
                return User.model_validate(user_doc)

    return None


async def get_device(
    device_id: str = Query(
        default=settings.default_device_id,
        description="Target device. Defaults to the configured device.",
    ),
    user: Optional[User] = Depends(get_current_user_optional),
) -> Device:
    await require_db()
    device = await repo.find_by_id(mongo.devices, Device, device_id)
    if device is None:
        device = await repo.get_or_create(
            mongo.devices, Device, device_id, lambda: Device(id=device_id, name=device_id)
        )
    await ensure_child_docs(device_id)

    # Telemetry bridging:
    # If the requested device is a virtual user device (e.g. dev-alok17) or has no direct
    # hardware connection, but the main hardware desk assistant (e.g. deskmate-01) is online,
    # bridge the live hardware telemetry so the user's dashboard reflects the active assistant.
    hw_id = settings.default_device_id
    if device.id != hw_id:
        hw_device = await repo.find_by_id(mongo.devices, Device, hw_id)
        if hw_device and (hw_device.wifi_connected or hub.device_connected(hw_id)):
            device.wifi_connected = hw_device.wifi_connected
            device.wifi_ssid = hw_device.wifi_ssid
            device.wifi_rssi = hw_device.wifi_rssi
            device.ip_address = hw_device.ip_address
            device.firmware_version = hw_device.firmware_version
            device.current_screen = hw_device.current_screen
            device.relay_on = hw_device.relay_on
            device.last_seen_at = hw_device.last_seen_at
            device.uptime_seconds = hw_device.uptime_seconds
            device.free_heap_bytes = hw_device.free_heap_bytes

    return device


async def get_or_create_device(device_id: str, name: str | None = None) -> Device:
    """Used by device-facing paths so a fresh ESP32 can self-register."""
    device = await repo.get_or_create(
        mongo.devices, Device, device_id, lambda: Device(id=device_id, name=name or device_id)
    )
    await ensure_child_docs(device_id)
    return device


DeviceDep = Annotated[Device, Depends(get_device)]
UserDep = Annotated[Optional[User], Depends(get_current_user_optional)]
DbDep = Annotated[None, Depends(require_db)]
