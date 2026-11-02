"""Auth dependencies.

Two separate credentials, because the two clients have different trust levels:

  * X-API-Key      — the dashboard / mobile app
  * X-Device-Token — the ESP32 firmware

Both are OFF by default so a fresh checkout runs with zero setup. That means the
REST API and the WebSocket are UNAUTHENTICATED in the default development
configuration. Before exposing this backend past localhost (port forwarding,
tunnels, a VPS, anything reachable from the internet) set REQUIRE_AUTH=true and
provide API_KEY and DEVICE_TOKEN in the environment.
"""

from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import Header, HTTPException, Query, status

from .config import settings

log = logging.getLogger(__name__)


def _matches(provided: Optional[str], expected: Optional[str]) -> bool:
    if not expected:
        return False
    if not provided:
        return False
    return hmac.compare_digest(provided.strip(), expected.strip())


def auth_enabled() -> bool:
    return settings.require_auth


async def require_client(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_device_token: Optional[str] = Header(default=None, alias="X-Device-Token"),
) -> str:
    """Allow either a dashboard key or a device token. Returns the caller role."""
    if not settings.require_auth:
        return "anonymous"

    if _matches(x_device_token, settings.device_token):
        return "device"
    if _matches(x_api_key, settings.api_key):
        return "dashboard"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid credentials",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def require_device(
    x_device_token: Optional[str] = Header(default=None, alias="X-Device-Token"),
) -> str:
    """Device-only endpoints (heartbeat, firmware state push)."""
    if not settings.require_auth:
        return "device"
    if _matches(x_device_token, settings.device_token):
        return "device"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid device token",
    )


def check_ws_token(role: str, token: Optional[str]) -> bool:
    """WebSocket handshake check. Browsers cannot set headers on a WS upgrade,
    so the credential arrives as a query parameter instead."""
    if not settings.require_auth:
        return True
    if role == "device":
        return _matches(token, settings.device_token)
    return _matches(token, settings.api_key)


async def ws_token(token: Optional[str] = Query(default=None)) -> Optional[str]:
    return token


def warn_if_open() -> None:
    if not settings.require_auth:
        log.warning(
            "REQUIRE_AUTH is false: the REST API and WebSocket accept unauthenticated "
            "requests. Fine on localhost, not fine on a public network."
        )
