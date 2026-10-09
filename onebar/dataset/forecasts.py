"""Past forecasts for the dataset, from Open-Meteo's historical forecast API.

Each fact set is built from a forecast the model service actually issued for that place and day, not from invented
weather. One call per location covers a short window of days; every situation for that location is cut from it.
Responses are cached on disk (Open-Meteo asks for fair use), so a rerun costs no calls.
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from onebar.facts.open_meteo import DAILY, HOURLY, REQUIRED_HOURLY, ForecastError

BASE = "https://historical-forecast-api.open-meteo.com/v1/forecast"
WINDOW_DAYS = 10
EARLIEST = date(2025, 5, 1)
LATEST_END = date(2026, 9, 25)  # leaves slack: the archive lags the present by a few days


def window_url(lat: float, lon: float, start: date, days: int = WINDOW_DAYS) -> str:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"coordinates out of range: {lat},{lon}")
    end = start + timedelta(days=days - 1)
    return (
        f"{BASE}?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
        f"&hourly={HOURLY}&daily={DAILY}&timezone=auto"
    )


def pick_start(location_id: str, seed: int, days: int = WINDOW_DAYS) -> date:
    """A stable pseudo-random window start for this location."""
    rng = random.Random(f"{seed}:{location_id}")
    last_start = LATEST_END - timedelta(days=days - 1)
    return EARLIEST + timedelta(days=rng.randrange((last_start - EARLIEST).days + 1))


def _http_get(url: str, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "onebar-hackathon/0.1 (dataset build)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def validate(data: object) -> dict:
    if not isinstance(data, dict) or data.get("error"):
        raise ForecastError(f"Open-Meteo error: {data.get('reason') if isinstance(data, dict) else 'bad response'}")
    hourly = data.get("hourly")
    if not isinstance(hourly, dict) or any(k not in hourly for k in REQUIRED_HOURLY):
        raise ForecastError("response is missing hourly data")
    if data.get("utc_offset_seconds") is None or not data.get("daily"):
        raise ForecastError("response is missing the utc offset or daily sun times")
    return data


def fetch_window(
    location_id: str,
    lat: float,
    lon: float,
    start: date,
    cache_dir: Path,
    get: Callable[[str], dict] = _http_get,
    retries: int = 5,
) -> dict:
    safe = location_id.replace(":", "_")
    path = cache_dir / f"{safe}_{start}.json"
    if path.is_file():
        return validate(json.loads(path.read_text(encoding="utf-8")))
    url = window_url(lat, lon, start)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            data = validate(get(url))
            break
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code != 429 and exc.code < 500:
                raise ForecastError(f"HTTP {exc.code} for {location_id}") from exc
        except (OSError, ForecastError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(2 * (attempt + 1))
    else:
        raise ForecastError(f"no forecast for {location_id}: {last}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return data
