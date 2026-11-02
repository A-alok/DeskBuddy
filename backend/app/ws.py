"""The WebSocket endpoint.

Both the ESP32 and every dashboard/mobile client connect here:

    ws://<host>:8000/ws?role=device&device_id=deskmate-01&token=...
    ws://<host>:8000/ws?role=dashboard&device_id=deskmate-01&token=...

Inbound command frames are validated, applied to the database, and only then
rebroadcast. That ordering is what makes the device and the dashboard agree:
nobody trusts a peer's state, everybody trusts the stored timestamp.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from . import events as ev
from . import repo
from .config import settings
from .db import mongo
from .deps import get_or_create_device
from .models import CommandSource, Device
from .realtime import Client, ClientRole, envelope, hub
from .security import check_ws_token
from .serializers import device_read
from .services import intents as intent_service
from .services.executor import execute
from .utils import utcnow

log = logging.getLogger(__name__)

router = APIRouter()

# Frames a client may send that map straight onto an executable intent.
COMMAND_FRAMES: set[str] = {
    "timer.start",
    "timer.pause",
    "timer.resume",
    "timer.cancel",
    "timer.status",
    "stopwatch.start",
    "stopwatch.stop",
    "stopwatch.lap",
    "stopwatch.reset",
    "pomodoro.start",
    "pomodoro.pause",
    "pomodoro.resume",
    "pomodoro.stop",
    "pomodoro.skip",
    "alarm.set",
    "alarm.cancel",
    "reminder.create",
    "task.create",
    "task.complete",
    "relay.on",
    "relay.off",
}


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    role: str = Query(default="dashboard"),
    device_id: str = Query(default=settings.default_device_id),
    token: Optional[str] = Query(default=None),
) -> None:
    role_normalized = role.strip().lower()
    if role_normalized not in {"device", "dashboard"}:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unknown role")
        return

    if not check_ws_token(role_normalized, token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    if not mongo.ready:
        # Accept, explain, then close. A silent rejection here looks identical to
        # a network problem from the client side.
        await websocket.accept()
        await websocket.send_json(
            envelope(
                "error",
                {"detail": mongo.error or "Database unavailable"},
                device_id=device_id,
            )
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Database unavailable")
        return

    client_role = ClientRole(role_normalized)

    device = await get_or_create_device(device_id)
    device_snapshot = device_read(device).model_dump(mode="json")

    client = await hub.connect(websocket, client_role, device_id)

    await hub.send(
        client,
        envelope(
            ev.HELLO,
            {
                "role": client_role.value,
                "server_time": utcnow().isoformat(),
                "device": device_snapshot,
                "connections": hub.counts(),
                "snapshot_url": f"/api/snapshot?device_id={device_id}",
            },
            device_id=device_id,
        ),
    )

    if client_role is ClientRole.DEVICE:
        await hub.publish(
            ev.DEVICE_ONLINE, device_snapshot, device_id=device_id, origin="device", exclude=client
        )

    try:
        while True:
            try:
                frame = await websocket.receive_json()
            except ValueError:
                await hub.send(
                    client,
                    envelope("error", {"detail": "Frames must be JSON"}, device_id=device_id),
                )
                continue
            await _handle_frame(client, frame)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("WebSocket loop failed for %s", device_id)
    finally:
        await hub.disconnect(client)
        if client_role is ClientRole.DEVICE and not hub.device_connected(device_id):
            if mongo.ready:
                device = await get_or_create_device(device_id)
                await hub.publish(
                    ev.DEVICE_OFFLINE,
                    device_read(device).model_dump(mode="json"),
                    device_id=device_id,
                    origin="device",
                )


async def _handle_frame(client: Client, frame: Any) -> None:
    if not isinstance(frame, dict):
        await hub.send(
            client,
            envelope("error", {"detail": "Frame must be a JSON object"}, device_id=client.device_id),
        )
        return

    frame_type = str(frame.get("type") or "").strip()
    payload: dict[str, Any] = frame.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    device_id = client.device_id
    source = (
        CommandSource.TOUCH if client.role is ClientRole.DEVICE else CommandSource.DASHBOARD
    )

    # ------------------------------------------------------------ liveness #
    if frame_type in {ev.PING, "ping"}:
        await hub.send(client, envelope(ev.PONG, device_id=device_id))
        return
    if frame_type == ev.PONG:
        return

    # ----------------------------------------------------------- heartbeat #
    if frame_type == ev.DEVICE_HEARTBEAT:
        await _apply_heartbeat(client, payload)
        return

    # -------------------------------------------------------- UI / gesture #
    if frame_type == ev.SCREEN_CHANGED:
        screen = str(payload.get("screen") or "home")[:32]
        await repo.patch(
            mongo.devices, Device, device_id, {"current_screen": screen, "last_seen_at": utcnow()}
        )
        await hub.publish(
            ev.SCREEN_CHANGED, {"screen": screen}, device_id=device_id, origin="device", exclude=client
        )
        return

    if frame_type == ev.TOUCH:
        await hub.publish(
            ev.TOUCH,
            {"gesture": str(payload.get("gesture") or "tap")[:16]},
            device_id=device_id,
            origin="device",
            exclude=client,
            persist=False,
        )
        return

    if frame_type == ev.VOICE_LISTENING:
        await hub.publish(
            ev.VOICE_LISTENING,
            {"listening": bool(payload.get("listening", True))},
            device_id=device_id,
            origin="device",
            exclude=client,
            persist=False,
        )
        return

    # ------------------------------------------------------ voice command #
    if frame_type == ev.VOICE_COMMAND:
        transcript = str(payload.get("transcript") or "").strip()
        if not transcript:
            return
        device = await get_or_create_device(device_id)
        intent = intent_service.parse(transcript)
        result = await execute(device, intent, source=CommandSource.VOICE)
        await hub.publish(
            "voice.reply",
            {"transcript": transcript, "intent": intent.name, "reply": result.reply},
            device_id=device_id,
            origin=CommandSource.VOICE.value,
            persist=False,
        )
        return

    # ---------------------------------------------------------- relay.set #
    if frame_type == ev.RELAY_SET:
        frame_type = "relay.on" if bool(payload.get("on", False)) else "relay.off"

    # ------------------------------------------------------ command frames #
    if frame_type in COMMAND_FRAMES:
        device = await get_or_create_device(device_id)
        intent = intent_service.Intent(name=frame_type, entities=payload)
        result = await execute(device, intent, source=source)
        await hub.send(
            client,
            envelope(
                "ack",
                {"of": frame_type, "reply": result.reply, "action": result.action},
                device_id=device_id,
            ),
        )
        return

    await hub.send(
        client,
        envelope("error", {"detail": f"Unknown frame type '{frame_type}'"}, device_id=device_id),
    )


async def _apply_heartbeat(client: Client, payload: dict[str, Any]) -> None:
    from .schemas import DeviceHeartbeat

    try:
        telemetry = DeviceHeartbeat.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        await hub.send(
            client,
            envelope(
                "error",
                {"detail": f"Invalid heartbeat: {exc}"[:300]},
                device_id=client.device_id,
            ),
        )
        return

    await get_or_create_device(client.device_id)
    changes: dict[str, Any] = telemetry.model_dump(exclude_none=True)
    changes["last_seen_at"] = utcnow()
    device = await repo.patch(mongo.devices, Device, client.device_id, changes)
    if device is None:
        return

    await hub.to_dashboards(
        client.device_id,
        envelope(
            ev.DEVICE_STATUS,
            device_read(device).model_dump(mode="json"),
            device_id=client.device_id,
            origin="device",
        ),
    )
