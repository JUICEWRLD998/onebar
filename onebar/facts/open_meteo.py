"""Open-Meteo forecast client. The HTTP getter is injected so tests and the pipeline stay offline-safe."""
from __future__ import annotations

import json
import math
import re
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


_HOUR_RX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
_DAY_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GRID_TOLERANCE_DEG = 0.25  # Open-Meteo snaps to its model grid; the returned point is never this far off
MAX_HOURS = 16 * 24


def _is_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _column(values: object, n: int, name: str, ok: Callable[[object], bool]) -> list:
    if not isinstance(values, list) or len(values) != n:
        raise ValueError(f"forecast column {name} has the wrong length")
    if not all(ok(v) for v in values):
        raise ValueError(f"forecast column {name} holds a value of the wrong kind")
    return list(values)


def clean_forecast(data: object, lat: float, lon: float) -> dict:
    """A forecast that did not come from this server's own fetch (the visitor's browser fetched forecast_url(lat, lon)),
    checked for shape and cut down to the fields the facts engine reads. Raises ValueError."""
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("forecast is not a forecast")
    if not (_is_num(data.get("latitude")) and _is_num(data.get("longitude"))):
        raise ValueError("forecast has no coordinates")
    if abs(data["latitude"] - lat) > GRID_TOLERANCE_DEG or abs(data["longitude"] - lon) > GRID_TOLERANCE_DEG:
        raise ValueError("forecast is for another place")
    offset = data.get("utc_offset_seconds")
    if not isinstance(offset, int) or isinstance(offset, bool) or abs(offset) > 14 * 3600:
        raise ValueError("forecast has no usable utc_offset_seconds")
    hourly, daily = data.get("hourly"), data.get("daily")
    if not isinstance(hourly, dict) or not isinstance(daily, dict):
        raise ValueError("forecast is missing hourly or daily data")
    times = hourly.get("time")
    if not isinstance(times, list) or not 0 < len(times) <= MAX_HOURS:
        raise ValueError("forecast has no hours")
    n = len(times)
    out_h = {"time": _column(times, n, "time", lambda v: isinstance(v, str) and bool(_HOUR_RX.match(v)))}
    for key in HOURLY.split(","):
        out_h[key] = _column(hourly.get(key), n, key, lambda v: v is None or _is_num(v))
    days = daily.get("time")
    if not isinstance(days, list) or not 0 < len(days) <= 16:
        raise ValueError("forecast has no days")
    out_d = {"time": _column(days, len(days), "daily time", lambda v: isinstance(v, str) and bool(_DAY_RX.match(v)))}
    for key in DAILY.split(","):
        out_d[key] = _column(daily.get(key), len(days), key, lambda v: isinstance(v, str) and bool(_HOUR_RX.match(v)))
    out = {"latitude": data["latitude"], "longitude": data["longitude"], "utc_offset_seconds": offset,
           "hourly": out_h, "daily": out_d}
    if _is_num(data.get("elevation")):
        out["elevation"] = data["elevation"]
    return out


def local_now(forecast: dict, now_utc: datetime | None = None) -> datetime:
    """The place's own wall-clock time, as a naive datetime on the forecast's clock (timezone=auto)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    offset = forecast.get("utc_offset_seconds")
    if offset is None:
        raise ForecastError("forecast has no utc_offset_seconds")
    return now_utc.astimezone(timezone(timedelta(seconds=offset))).replace(tzinfo=None)
