"""WebSocket hub — the single sync point between the ESP32 and every client.

The ESP32 and the dashboard never talk to each other directly. Both connect here;
the backend persists state changes and fans the resulting event out to everyone
else. Payloads carry absolute timestamps, never countdowns, so each client renders
its own smooth tick without network traffic per second.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from . import events as ev
from .utils import iso, utcnow

log = logging.getLogger(__name__)


class ClientRole(str, Enum):
    DEVICE = "device"
    DASHBOARD = "dashboard"


@dataclass
class Client:
    websocket: WebSocket
    role: ClientRole
    device_id: str
    connected_at: Any = field(default_factory=utcnow)

    @property
    def is_open(self) -> bool:
        return self.websocket.client_state == WebSocketState.CONNECTED


def envelope(
    type_: str,
    payload: Optional[dict[str, Any]] = None,
    *,
    device_id: Optional[str] = None,
    origin: str = "server",
) -> dict[str, Any]:
    """Every frame on the wire uses this shape."""
    return {
        "type": type_,
        "device_id": device_id,
        "origin": origin,
        "ts": iso(utcnow()),
        "payload": payload or {},
    }


class Hub:
    def __init__(self) -> None:
        self._clients: list[Client] = []
        self._lock = asyncio.Lock()

    # ----------------------------------------------------------------- state #
    @property
    def clients(self) -> list[Client]:
        return list(self._clients)

    def device_connected(self, device_id: str) -> bool:
        return any(
            c.role is ClientRole.DEVICE and c.device_id == device_id and c.is_open
            for c in self._clients
        )

    def counts(self) -> dict[str, int]:
        return {
            "devices": sum(1 for c in self._clients if c.role is ClientRole.DEVICE),
            "dashboards": sum(1 for c in self._clients if c.role is ClientRole.DASHBOARD),
        }

    # ------------------------------------------------------------ lifecycle #
    async def connect(self, websocket: WebSocket, role: ClientRole, device_id: str) -> Client:
        await websocket.accept()
        client = Client(websocket=websocket, role=role, device_id=device_id)
        async with self._lock:
            self._clients.append(client)
        log.info("WS connect role=%s device=%s (%s)", role.value, device_id, self.counts())
        return client

    async def disconnect(self, client: Client) -> None:
        async with self._lock:
            if client in self._clients:
                self._clients.remove(client)
        log.info(
            "WS disconnect role=%s device=%s (%s)",
            client.role.value,
            client.device_id,
            self.counts(),
        )

    # ------------------------------------------------------------ messaging #
    async def send(self, client: Client, message: dict[str, Any]) -> None:
        if not client.is_open:
            return
        try:
            await client.websocket.send_json(message)
        except Exception as exc:  # noqa: BLE001 - a dead socket must not kill the caller
            log.debug("WS send failed (%s); dropping client", exc)
            await self.disconnect(client)

    async def broadcast(
        self,
        message: dict[str, Any],
        *,
        device_id: Optional[str] = None,
        roles: Optional[set[ClientRole]] = None,
        exclude: Optional[Client] = None,
    ) -> int:
        """Fan a frame out. Returns how many clients it reached."""
        targets = [
            c
            for c in self._clients
            if c is not exclude
            and (device_id is None or c.device_id == device_id)
            and (roles is None or c.role in roles)
        ]
        if not targets:
            return 0
        results = await asyncio.gather(
            *(self.send(c, message) for c in targets), return_exceptions=True
        )
        return sum(1 for r in results if not isinstance(r, Exception))

    async def to_device(self, device_id: str, message: dict[str, Any]) -> int:
        return await self.broadcast(message, device_id=device_id, roles={ClientRole.DEVICE})

    async def to_dashboards(self, device_id: str, message: dict[str, Any]) -> int:
        return await self.broadcast(message, device_id=device_id, roles={ClientRole.DASHBOARD})

    async def publish(
        self,
        type_: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        device_id: str,
        origin: str = "server",
        exclude: Optional[Client] = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Persist (optionally) then broadcast a state-change event."""
        frame = envelope(type_, payload, device_id=device_id, origin=origin)
        if persist and type_ not in ev.EPHEMERAL:
            await _record_event(
                device_id=device_id, type_=type_, origin=origin, payload=payload or {}
            )
        await self.broadcast(frame, device_id=device_id, exclude=exclude)
        return frame


async def _record_event(
    *, device_id: str, type_: str, origin: str, payload: dict[str, Any]
) -> None:
    """Append to device_events. Never let logging break the request.

    A TTL index on created_at expires these, so this collection cannot grow into
    an Atlas storage limit.
    """
    from .db import mongo
    from .models import CommandSource, DeviceEvent

    if not mongo.ready:
        return

    try:
        source = CommandSource(origin)
    except ValueError:
        source = CommandSource.SYSTEM

    try:
        event = DeviceEvent(
            device_id=device_id,
            type=type_,
            origin=source,
            payload=_jsonable(payload),
        )
        await mongo.device_events.insert_one(event.to_doc())
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not persist event %s: %s", type_, exc)


def _jsonable(value: Any) -> Any:
    from datetime import datetime

    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, Enum):
        return value.value
    return value


hub = Hub()
