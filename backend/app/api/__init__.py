"""REST API routers, assembled into one /api router."""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    alarms,
    analytics,
    auth,
    chat,
    competitive,
    device,
    notes,
    pomodoro,
    reminders,
    settings,
    stopwatch,
    tasks,
    timers,
    weather,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router)
api_router.include_router(device.router)
api_router.include_router(timers.router)
api_router.include_router(stopwatch.router)
api_router.include_router(alarms.router)
api_router.include_router(pomodoro.router)
api_router.include_router(tasks.router)
api_router.include_router(reminders.router)
api_router.include_router(analytics.router)
api_router.include_router(chat.router)
api_router.include_router(settings.router)
api_router.include_router(weather.router)
api_router.include_router(notes.router)
api_router.include_router(competitive.router)

__all__ = ["api_router"]
