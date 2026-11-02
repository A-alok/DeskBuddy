"""Weather via Open-Meteo.

Chosen because it needs no API key and no account, which keeps the setup burden
at zero — the same reason the rest of this project defaults to working offline.

Two caches, both deliberate:

* Geocoding is cached for the process lifetime. A city name resolves to the same
  coordinates forever, so asking twice is pure waste.
* The forecast is cached for `weather_cache_minutes`. The device polls this
  endpoint, and Open-Meteo updates roughly every 15 minutes, so hammering it
  would be rude and would gain nothing.

Field names below were verified against the live API rather than assumed:
`current.temperature_2m`, `current.weather_code`, `daily.temperature_2m_max`,
and so on. Errors come back as HTTP 400 with `{"reason": ..., "error": true}`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from ..config import settings
from ..schemas import WeatherRead
from ..utils import utcnow

log = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
    "precipitation,weather_code,wind_speed_10m"
)
DAILY_FIELDS = (
    "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,"
    "precipitation_probability_max"
)

# WMO weather interpretation codes.
# `short` is capped at 12 characters: the OLED is 128 px wide and this has to sit
# next to a temperature reading without wrapping.
_WMO: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "Clear"),
    1: ("Mainly clear", "Mainly clear"),
    2: ("Partly cloudy", "Part cloudy"),
    3: ("Overcast", "Overcast"),
    45: ("Fog", "Fog"),
    48: ("Depositing rime fog", "Rime fog"),
    51: ("Light drizzle", "Drizzle"),
    53: ("Moderate drizzle", "Drizzle"),
    55: ("Dense drizzle", "Drizzle"),
    56: ("Light freezing drizzle", "Frz drizzle"),
    57: ("Dense freezing drizzle", "Frz drizzle"),
    61: ("Slight rain", "Light rain"),
    63: ("Moderate rain", "Rain"),
    65: ("Heavy rain", "Heavy rain"),
    66: ("Light freezing rain", "Frz rain"),
    67: ("Heavy freezing rain", "Frz rain"),
    71: ("Slight snowfall", "Light snow"),
    73: ("Moderate snowfall", "Snow"),
    75: ("Heavy snowfall", "Heavy snow"),
    77: ("Snow grains", "Snow grains"),
    80: ("Slight rain showers", "Showers"),
    81: ("Moderate rain showers", "Showers"),
    82: ("Violent rain showers", "Hvy showers"),
    85: ("Slight snow showers", "Snow shwrs"),
    86: ("Heavy snow showers", "Snow shwrs"),
    95: ("Thunderstorm", "Thunder"),
    96: ("Thunderstorm with hail", "Thunder+hail"),
    99: ("Thunderstorm with heavy hail", "Thunder+hail"),
}


def describe_code(code: Optional[int]) -> tuple[str, str]:
    if code is None:
        return ("Unknown", "Unknown")
    return _WMO.get(int(code), (f"Code {code}", f"WMO {code}"))


@dataclass
class Location:
    latitude: float
    longitude: float
    name: str
    country: str = ""


_location_cache: Optional[Location] = None
_forecast_cache: Optional[WeatherRead] = None
_forecast_fetched_at: Optional[datetime] = None


class WeatherError(RuntimeError):
    """Raised with a message meant to be shown to a human."""


def _explain(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("reason"):
            return str(body["reason"])[:200]
    except Exception:  # noqa: BLE001
        pass
    return f"HTTP {response.status_code}: {response.text[:150]}"


async def resolve_location(force: bool = False) -> Location:
    """Explicit coordinates win; otherwise geocode the city name once."""
    global _location_cache

    if settings.weather_latitude is not None and settings.weather_longitude is not None:
        return Location(
            latitude=float(settings.weather_latitude),
            longitude=float(settings.weather_longitude),
            name=settings.weather_city.strip() or "Configured location",
        )

    if _location_cache is not None and not force:
        return _location_cache

    city = settings.weather_city.strip()
    if not city:
        raise WeatherError(
            "No location configured. Set WEATHER_CITY (e.g. 'Delhi'), or "
            "WEATHER_LATITUDE and WEATHER_LONGITUDE, in backend/.env."
        )

    try:
        async with httpx.AsyncClient(timeout=settings.weather_timeout_seconds) as client:
            response = await client.get(
                GEOCODE_URL,
                params={"name": city, "count": 1, "language": "en", "format": "json"},
            )
    except Exception as exc:  # noqa: BLE001
        raise WeatherError(f"Could not reach the geocoding service: {exc}") from exc

    if response.status_code != 200:
        raise WeatherError(f"Geocoding failed — {_explain(response)}")

    results = (response.json() or {}).get("results") or []
    if not results:
        raise WeatherError(
            f"No place called '{city}' was found. Try adding the country, or set "
            "WEATHER_LATITUDE/WEATHER_LONGITUDE directly."
        )

    top = results[0]
    _location_cache = Location(
        latitude=float(top["latitude"]),
        longitude=float(top["longitude"]),
        name=str(top.get("name") or city),
        country=str(top.get("country") or ""),
    )
    log.info(
        "[weather] '%s' resolved to %s, %s (%.4f, %.4f)",
        city,
        _location_cache.name,
        _location_cache.country,
        _location_cache.latitude,
        _location_cache.longitude,
    )
    return _location_cache


def _parse_local(value: Any, offset_seconds: int) -> Optional[datetime]:
    """Open-Meteo returns local wall-clock times with no offset attached."""
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return (naive - timedelta(seconds=offset_seconds)).replace(tzinfo=timezone.utc)


def cached() -> Optional[WeatherRead]:
    """Whatever is in the cache, fresh or not. Used as a fallback on failure."""
    return _forecast_cache


def _is_fresh() -> bool:
    if _forecast_cache is None or _forecast_fetched_at is None:
        return False
    age = utcnow() - _forecast_fetched_at
    return age < timedelta(minutes=settings.weather_cache_minutes)


async def get(force: bool = False) -> WeatherRead:
    """Current conditions, from cache unless stale."""
    global _forecast_cache, _forecast_fetched_at

    if _is_fresh() and not force:
        return _forecast_cache  # type: ignore[return-value]

    location = await resolve_location()
    fahrenheit = settings.weather_units.lower().startswith("f")

    params: dict[str, Any] = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": CURRENT_FIELDS,
        "daily": DAILY_FIELDS,
        "timezone": "auto",
        "forecast_days": 2,
    }
    if fahrenheit:
        params["temperature_unit"] = "fahrenheit"
        params["wind_speed_unit"] = "mph"

    try:
        async with httpx.AsyncClient(timeout=settings.weather_timeout_seconds) as client:
            response = await client.get(FORECAST_URL, params=params)
    except Exception as exc:  # noqa: BLE001
        if _forecast_cache is not None:
            log.warning("[weather] fetch failed (%s); serving stale cache", exc)
            return _forecast_cache
        raise WeatherError(f"Could not reach the weather service: {exc}") from exc

    if response.status_code != 200:
        if _forecast_cache is not None:
            log.warning("[weather] %s; serving stale cache", _explain(response))
            return _forecast_cache
        raise WeatherError(f"Weather lookup failed — {_explain(response)}")

    data = response.json()
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    offset = int(data.get("utc_offset_seconds") or 0)

    def day0(key: str) -> Any:
        values = daily.get(key)
        return values[0] if isinstance(values, list) and values else None

    code = current.get("weather_code")
    description, short = describe_code(code)

    weather = WeatherRead(
        location=location.name,
        country=location.country,
        latitude=location.latitude,
        longitude=location.longitude,
        observed_at=_parse_local(current.get("time"), offset) or utcnow(),
        fetched_at=utcnow(),
        temperature=current.get("temperature_2m"),
        feels_like=current.get("apparent_temperature"),
        humidity=current.get("relative_humidity_2m"),
        wind_speed=current.get("wind_speed_10m"),
        precipitation=current.get("precipitation"),
        is_day=bool(current.get("is_day", 1)),
        weather_code=code,
        description=description,
        short=short,
        temp_max=day0("temperature_2m_max"),
        temp_min=day0("temperature_2m_min"),
        precipitation_chance=day0("precipitation_probability_max"),
        sunrise=_parse_local(day0("sunrise"), offset),
        sunset=_parse_local(day0("sunset"), offset),
        temperature_unit="°F" if fahrenheit else "°C",
        wind_unit="mph" if fahrenheit else "km/h",
        timezone=str(data.get("timezone") or ""),
        stale=False,
    )

    _forecast_cache = weather
    _forecast_fetched_at = utcnow()
    log.info(
        "[weather] %s: %.1f%s %s",
        weather.location,
        weather.temperature if weather.temperature is not None else float("nan"),
        weather.temperature_unit,
        weather.description,
    )
    return weather


def spoken_summary(weather: WeatherRead) -> str:
    """One or two sentences, for a speaker and a 128x64 screen."""
    parts: list[str] = []
    if weather.temperature is not None:
        rounded = round(weather.temperature)
        parts.append(f"{weather.description.lower()}, {rounded} degrees in {weather.location}")
    else:
        parts.append(f"{weather.description.lower()} in {weather.location}")

    if weather.feels_like is not None and weather.temperature is not None:
        if abs(weather.feels_like - weather.temperature) >= 2:
            parts.append(f"feels like {round(weather.feels_like)}")

    tail = ""
    if weather.temp_min is not None and weather.temp_max is not None:
        tail = f" Today {round(weather.temp_min)} to {round(weather.temp_max)}."
    if weather.precipitation_chance is not None and weather.precipitation_chance >= 30:
        tail += f" {weather.precipitation_chance}% chance of rain."

    body = ", ".join(parts)
    # Upper-case the first letter only. str.capitalize() would lower-case the
    # rest and turn "in Delhi" into "in delhi".
    sentence = body[:1].upper() + body[1:]
    return (sentence + "." + tail).strip()


def reset_cache() -> None:
    """For tests and for after a config change."""
    global _forecast_cache, _forecast_fetched_at, _location_cache
    _forecast_cache = None
    _forecast_fetched_at = None
    _location_cache = None
