"""Per-device settings — a small key/value store.

Used for things the firmware and the dashboard both need to agree on: timezone
offset, 24h clock, OLED brightness, beep volume, wake behaviour.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .. import events as ev
from .. import repo
from ..db import mongo
from ..deps import DeviceDep
from ..models import Setting
from ..realtime import hub
from ..schemas import SettingsRead, SettingsUpdate
from ..utils import utcnow

router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULTS: dict[str, Any] = {
    "tz_offset_minutes": 0,
    "clock_24h": True,
    "oled_brightness": 180,
    "beep_volume": 6,
    "speaker_volume": 8,
    "touch_wake_voice": True,
    "chime_on_timer_end": True,
    "relay_label": "LED light",
}


async def _values(device_id: str) -> dict[str, Any]:
    rows = await repo.find_many(
        mongo.settings_store, Setting, {"device_id": device_id}, limit=200
    )
    values = dict(DEFAULTS)
    values.update({row.key: row.value for row in rows})
    return values


@router.get("", response_model=SettingsRead)
async def get_settings(device: DeviceDep) -> SettingsRead:
    return SettingsRead(device_id=device.id, values=await _values(device.id))


@router.put("", response_model=SettingsRead)
async def update_settings(device: DeviceDep, payload: SettingsUpdate) -> SettingsRead:
    now = utcnow()
    for key, value in payload.values.items():
        # `_id` is "<device>:<key>", so this upsert is naturally idempotent and
        # needs no read-modify-write.
        await mongo.settings_store.update_one(
            {"_id": Setting.make_id(device.id, key)},
            {
                "$set": {"value": value, "updated_at": now},
                "$setOnInsert": {"device_id": device.id, "key": key},
            },
            upsert=True,
        )

    values = await _values(device.id)
    await hub.publish(
        ev.SETTINGS_UPDATED, {"values": values}, device_id=device.id, origin="dashboard"
    )
    return SettingsRead(device_id=device.id, values=values)


@router.get("/defaults")
async def get_defaults() -> dict[str, Any]:
    return DEFAULTS
