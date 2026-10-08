"""Shared test helpers: a controllable synthetic forecast and the frozen real ones."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures" / "forecasts"

_DEFAULTS = {
    "temperature_2m": 10.0,
    "apparent_temperature": 8.0,
    "precipitation_probability": 0,
    "precipitation": 0.0,
    "weather_code": 1,
    "wind_speed_10m": 10.0,
    "wind_gusts_10m": 20.0,
    "cape": 0.0,
}


def synth(start: str = "2026-10-08", days: int = 2, elevation: float | None = 3219.0,
          sunrise: str = "07:30", sunset: str = "18:30") -> dict:
    """Flat calm forecast in Open-Meteo shape (test input, not a claim about any real place)."""
    day0 = datetime.fromisoformat(start)
    times = [(day0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(24 * days)]
    hourly = {"time": times}
    for key, value in _DEFAULTS.items():
        hourly[key] = [value] * len(times)
    daily = {
        "time": [(day0 + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days)],
        "sunrise": [(day0 + timedelta(days=d)).strftime("%Y-%m-%d") + "T" + sunrise for d in range(days)],
        "sunset": [(day0 + timedelta(days=d)).strftime("%Y-%m-%d") + "T" + sunset for d in range(days)],
    }
    out = {"hourly": hourly, "daily": daily}
    if elevation is not None:
        out["elevation"] = elevation
    return out


def set_hour(fc: dict, hour_iso: str, **values) -> dict:
    """Return a copy of fc with the given hourly values changed at one hour."""
    fc = copy.deepcopy(fc)
    i = fc["hourly"]["time"].index(hour_iso)
    for key, value in values.items():
        fc["hourly"][key][i] = value
    return fc


def load_real_fixtures() -> list[tuple[str, dict, datetime]]:
    """(name, forecast, 10:20 local on the forecast's first day) for each frozen real forecast."""
    out = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        blob = json.loads(path.read_text(encoding="utf-8"))
        fc = blob["forecast"]
        first = datetime.fromisoformat(fc["hourly"]["time"][0])
        out.append((blob["meta"]["name"], fc, first.replace(hour=10, minute=20)))
    return out


@pytest.fixture
def calm():
    return synth()


@pytest.fixture(scope="session")
def real_fixtures():
    fixtures = load_real_fixtures()
    assert len(fixtures) == 20
    return fixtures
