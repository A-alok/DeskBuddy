"""Weather endpoint.

Served from a backend-side cache so a polling device cannot hammer Open-Meteo.
On an upstream failure a stale reading is returned with `stale: true` rather than
an error — a slightly old temperature is far more useful on a desk clock than a
blank field.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..config import settings
from ..schemas import WeatherRead
from ..services import weather as weather_service

router = APIRouter(tags=["weather"])


@router.get("/weather", response_model=WeatherRead)
async def current_weather(
    refresh: bool = Query(default=False, description="Bypass the cache"),
) -> WeatherRead:
    if not settings.weather_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No location configured. Set WEATHER_CITY (e.g. 'Delhi'), or "
                "WEATHER_LATITUDE and WEATHER_LONGITUDE, in backend/.env."
            ),
        )
    try:
        return await weather_service.get(force=refresh)
    except weather_service.WeatherError as exc:
        # Prefer a stale reading over a failure.
        fallback = weather_service.cached()
        if fallback is not None:
            return fallback.model_copy(update={"stale": True})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
