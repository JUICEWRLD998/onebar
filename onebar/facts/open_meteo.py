"""Open-Meteo forecast client. The HTTP getter is injected so tests and the pipeline stay offline-safe."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable

BASE = "https://api.open-meteo.com/v1/forecast"
HOURLY = (
    "temperature_2m,apparent_temperature,precipitation_probability,precipitation,"
    "weather_code,wind_speed_10m,wind_gusts_10m,cape"
)
DAILY = "sunrise,sunset"
REQUIRED_HOURLY = ("time", "temperature_2m")


class ForecastError(RuntimeError):
    pass


def forecast_url(lat: float, lon: float, days: int = 3) -> str:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"coordinates out of range: {lat},{lon}")
    return (
        f"{BASE}?latitude={lat}&longitude={lon}&hourly={HOURLY}&daily={DAILY}"
        f"&timezone=auto&forecast_days={days}"
    )


def _http_get(url: str, timeout: float = 20.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "onebar/0.1 (+https://github.com/JUICEWRLD998/onebar)"})
    for attempt in range(4):  # Open-Meteo answers 429/5xx now and then, more often to shared cloud IPs
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise AssertionError("unreachable")


def fetch_forecast(
    lat: float,
    lon: float,
    days: int = 3,
    get: Callable[[str], dict] = _http_get,
) -> dict:
    url = forecast_url(lat, lon, days)
    try:
        data = get(url)
    except Exception as exc:  # network, HTTP or JSON errors all mean "no forecast"
        print(f"forecast fetch failed: {type(exc).__name__}: {exc}", flush=True)
        raise ForecastError(f"Open-Meteo request failed: {exc}") from exc
    if not isinstance(data, dict) or data.get("error"):
        reason = data.get("reason") if isinstance(data, dict) else "bad response"
        raise ForecastError(f"Open-Meteo error: {reason}")
    hourly = data.get("hourly")
    if not isinstance(hourly, dict) or any(k not in hourly for k in REQUIRED_HOURLY):
        raise ForecastError("Open-Meteo response is missing hourly data")
    return data


def local_now(forecast: dict, now_utc: datetime | None = None) -> datetime:
    """The place's own wall-clock time, as a naive datetime on the forecast's clock (timezone=auto)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    offset = forecast.get("utc_offset_seconds")
    if offset is None:
        raise ForecastError("forecast has no utc_offset_seconds")
    return now_utc.astimezone(timezone(timedelta(seconds=offset))).replace(tzinfo=None)
