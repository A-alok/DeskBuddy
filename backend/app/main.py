"""FastAPI application entry point.

Run it with:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api import api_router
from .config import settings
from .db import init_db, mongo
from .realtime import hub
from .security import require_client, warn_if_open
from .services import ai as ai_service
from .services.scheduler import scheduler
from .utils import iso, utcnow
from .ws import router as ws_router

# The Windows console is cp1252 by default. Any log line carrying a character
# outside it — a task title with a curly quote, an LLM reply with a non-breaking
# hyphen — would raise UnicodeEncodeError inside the logging handler and, on the
# request path, surface as a 500 with no useful traceback.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
# pymongo is chatty at DEBUG and drowns out everything else.
logging.getLogger("pymongo").setLevel(logging.WARNING)
log = logging.getLogger("deskmate")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201, ARG001
    await init_db()
    warn_if_open()
    scheduler.start()

    log.info(
        "%s v%s ready (env=%s, db=%s, ai=%s)",
        settings.app_name,
        __version__,
        settings.environment,
        "connected" if mongo.ready else "DOWN",
        ai_service.describe(),
    )
    if not mongo.ready:
        log.error(
            "Data endpoints will return 503 until MongoDB is reachable. "
            "See GET /health for the reason."
        )
    try:
        yield
    finally:
        await scheduler.stop()
        await mongo.close()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Backend sync hub for the AI DeskMate ESP32-S3 desk assistant. "
        "The device and the dashboard never talk directly: both connect here, "
        "and state is exchanged as events carrying absolute timestamps. "
        "Storage is MongoDB Atlas; the assistant runs on GroqCloud."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_allow_all else settings.cors_origins,
    allow_origin_regex=None if settings.cors_allow_all else r"^(capacitor|ionic)://localhost$",
    allow_credentials=not settings.cors_allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The WebSocket does its own token check (browsers cannot set headers on an
# upgrade request), so it is mounted outside the REST auth dependency.
app.include_router(ws_router)
app.include_router(api_router, dependencies=[Depends(require_client)])


@app.get("/", tags=["meta"])
async def root() -> dict[str, Any]:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "websocket": "/ws?role=dashboard&device_id=" + settings.default_device_id,
        "snapshot": "/api/snapshot",
    }


@app.get("/health", tags=["meta"])
async def health() -> dict[str, Any]:
    """Liveness plus the two things that actually break: the DB and the AI key."""
    database = await mongo.health()
    return {
        "status": "ok" if database["status"] == "ok" else "degraded",
        "server_time": iso(utcnow()),
        "environment": settings.environment,
        "auth_required": settings.require_auth,
        "database": database,
        "ai": {
            "provider": settings.ai_provider,
            "mode": ai_service.describe(),
            "model": settings.groq_model,
            "key_present": bool(settings.groq_api_key),
        },
        "connections": hub.counts(),
    }


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):  # noqa: ANN001, ARG001
    return JSONResponse(status_code=400, content={"detail": str(exc)})
