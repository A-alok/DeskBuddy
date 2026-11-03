"""Device status, telemetry, relay and the combined snapshot endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from .. import events as ev
from .. import repo
from ..config import settings as app_settings
from ..db import mongo
from ..deps import DeviceDep, UserDep, get_or_create_device, require_db
from ..models import (
    Device,
    DeviceEvent,
    Reminder,
    Setting,
    Task,
    VoiceCommand,
)
from ..realtime import envelope, hub
from ..schemas import (
    DeviceHeartbeat,
    DeviceRead,
    OkResponse,
    RelayRequest,
    ScreenRequest,
    SnapshotRead,
    WifiConfigRequest,
    WifiConfigRead,
)
from ..serializers import (
    alarm_read,
    device_read,
    pomodoro_read,
    reminder_read,
    stopwatch_read,
    task_read,
    timer_read,
    voice_command_read,
)
from ..services import alarms as alarm_service
from ..services import analytics as analytics_service
from ..services import pomodoro as pomodoro_service
from ..services import stopwatch as stopwatch_service
from ..services import timers as timer_service
from ..utils import utcnow

router = APIRouter(tags=["device"])


@router.get("/device/status", response_model=DeviceRead)
async def device_status(device: DeviceDep) -> DeviceRead:
    return device_read(device)


@router.post("/device/heartbeat", response_model=DeviceRead)
async def device_heartbeat(
    payload: DeviceHeartbeat,
    device_id: str = Query(default=app_settings.default_device_id),
) -> DeviceRead:
    """Called by the ESP32 every few seconds. Self-registers unknown devices."""
    await require_db()
    device = await get_or_create_device(device_id)
    was_online = device_read(device).online

    changes: dict[str, Any] = payload.model_dump(exclude_none=True)
    changes["last_seen_at"] = utcnow()
    updated = await repo.patch(mongo.devices, Device, device_id, changes)
    device = updated or device

    read = device_read(device)
    if not was_online:
        await hub.publish(
            ev.DEVICE_ONLINE, read.model_dump(mode="json"), device_id=device.id, origin="device"
        )
    await hub.to_dashboards(
        device.id,
        envelope(
            ev.DEVICE_STATUS,
            read.model_dump(mode="json"),
            device_id=device.id,
            origin="device",
        ),
    )
    return read


@router.post("/device/relay", response_model=DeviceRead)
async def set_relay(device: DeviceDep, payload: RelayRequest) -> DeviceRead:
    """Dashboard -> device relay control. The firmware applies it on the event."""
    updated = await repo.patch(mongo.devices, Device, device.id, {"relay_on": payload.on})
    device = updated or device

    read = device_read(device)
    await hub.publish(
        ev.RELAY_SET,
        {"on": payload.on, "device": read.model_dump(mode="json")},
        device_id=device.id,
        origin=payload.source.value,
    )
    return read


@router.post("/device/screen", response_model=DeviceRead)
async def set_screen(device: DeviceDep, payload: ScreenRequest) -> DeviceRead:
    updated = await repo.patch(
        mongo.devices, Device, device.id, {"current_screen": payload.screen}
    )
    device = updated or device
    read = device_read(device)
    await hub.publish(
        ev.SCREEN_CHANGED, {"screen": payload.screen}, device_id=device.id, origin="dashboard"
    )
    return read


@router.get("/device/events")
async def device_events(
    device: DeviceDep,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    rows = await repo.find_many(
        mongo.device_events,
        DeviceEvent,
        {"device_id": device.id},
        sort=[("created_at", repo.DESC)],
        limit=limit,
    )
    return [
        {
            "id": row.id,
            "type": row.type,
            "origin": row.origin,
            "payload": row.payload,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/device/wifi", response_model=WifiConfigRead)
async def get_device_wifi(device: DeviceDep) -> WifiConfigRead:
    """Retrieve the currently configured Wi-Fi network saved in MongoDB."""
    ssid = getattr(device, "wifi_config_ssid", "") or device.wifi_ssid or ""
    pwd = getattr(device, "wifi_config_password", "")
    return WifiConfigRead(
        device_id=device.id,
        ssid=ssid,
        password_set=bool(pwd),
        configured_at=getattr(device, "wifi_configured_at", None),
    )


@router.post("/device/wifi", response_model=WifiConfigRead)
async def set_device_wifi(device: DeviceDep, payload: WifiConfigRequest) -> WifiConfigRead:
    """Save Wi-Fi network credentials in MongoDB database and dispatch to ESP32."""
    now = utcnow()
    updates = {
        "wifi_config_ssid": payload.ssid.strip(),
        "wifi_config_password": payload.password or "",
        "wifi_configured_at": now,
    }
    updated = await repo.patch(mongo.devices, Device, device.id, updates)
    device = updated or device

    # Broadcast event to device & dashboards via WebSocket
    await hub.publish(
        ev.WIFI_CONFIG_SET,
        {
            "device_id": device.id,
            "ssid": payload.ssid.strip(),
            "password": payload.password or "",
        },
        device_id=device.id,
        origin="dashboard",
    )

    return WifiConfigRead(
        device_id=device.id,
        ssid=payload.ssid.strip(),
        password_set=bool(payload.password),
        configured_at=now,
    )


@router.post("/device/ping", response_model=OkResponse)
async def ping_device(device: DeviceDep) -> OkResponse:
    """Ask the firmware to acknowledge — useful to prove the link is alive."""
    reached = await hub.to_device(
        device.id, envelope(ev.PING, device_id=device.id, origin="server")
    )
    return OkResponse(ok=reached > 0, detail=f"Reached {reached} device connection(s)")


@router.post("/device/touch", response_model=OkResponse)
async def touch_event(
    device: DeviceDep,
    gesture: str = Body(default="tap", embed=True),
) -> OkResponse:
    """Firmware reports a touch gesture so dashboards can reflect it live."""
    await hub.publish(ev.TOUCH, {"gesture": gesture}, device_id=device.id, origin="device")
    return OkResponse(detail=gesture)


@router.get("/snapshot", response_model=SnapshotRead, tags=["snapshot"])
async def snapshot(
    device: DeviceDep,
    user: UserDep,
    range_days: int = Query(default=7, ge=1, le=90),
    tasks_limit: int = Query(default=200, ge=1, le=200),
    reminders_limit: int = Query(default=100, ge=1, le=100),
) -> SnapshotRead:
    """Everything a client needs for a cold start, in one request."""
    active_timer = await timer_service.get_active(device.id)
    recent_timers = await timer_service.list_recent(device.id, limit=10)
    sw = await stopwatch_service.get(device.id)
    pomo = await pomodoro_service.get(device.id)
    alarms = await alarm_service.list_for_device(device.id)

    reminder_filter: dict = {}
    if user:
        reminder_filter["$or"] = [
            {"user_id": user.id},
            {"username": user.username},
            {"device_id": user.device_id},
        ]
    else:
        reminder_filter["device_id"] = device.id

    reminders = await repo.find_many(
        mongo.reminders,
        Reminder,
        reminder_filter,
        sort=[("remind_at", repo.ASC)],
        limit=reminders_limit,
    )

    task_filter: dict = {}
    if user:
        task_filter["$or"] = [
            {"user_id": user.id},
            {"username": user.username},
            {"device_id": user.device_id},
        ]
    else:
        task_filter["device_id"] = device.id

    tasks = await repo.find_many(
        mongo.tasks,
        Task,
        task_filter,
        sort=[("done", repo.ASC), ("created_at", repo.DESC)],
        limit=tasks_limit,
    )
    commands = await repo.find_many(
        mongo.voice_commands,
        VoiceCommand,
        {"device_id": device.id},
        sort=[("created_at", repo.DESC)],
        limit=20,
    )
    setting_rows = await repo.find_many(
        mongo.settings_store, Setting, {"device_id": device.id}, limit=100
    )

    analytics = await analytics_service.build(device.id, range_days, user=user)
    
    from ..services import weather as weather_service
    weather = None
    if app_settings.weather_configured:
        try:
            weather = await weather_service.get()
        except weather_service.WeatherError:
            weather = weather_service.cached()
            if weather:
                weather = weather.model_copy(update={"stale": True})

    return SnapshotRead(
        server_time=utcnow(),
        device=device_read(device),
        weather=weather,
        timer=timer_read(active_timer) if active_timer else None,
        timers=[timer_read(t) for t in recent_timers],
        stopwatch=stopwatch_read(sw),
        pomodoro=pomodoro_read(pomo),
        alarms=[alarm_read(a) for a in alarms],
        reminders=[reminder_read(r) for r in reminders],
        tasks=[task_read(t) for t in tasks],
        recent_commands=[voice_command_read(c) for c in commands],
        analytics=analytics,
        settings={row.key: row.value for row in setting_rows},
    )
