import json
import os

import pytest

from onebar.facts.open_meteo import ForecastError, fetch_forecast, forecast_url

from conftest import FIXTURE_DIR, synth


def test_url_has_every_variable_and_auto_timezone():
    url = forecast_url(46.55, 7.98)
    for name in ("temperature_2m", "apparent_temperature", "precipitation_probability",
                 "precipitation", "weather_code", "wind_speed_10m", "wind_gusts_10m", "cape",
                 "sunrise", "sunset", "timezone=auto", "latitude=46.55", "longitude=7.98"):
        assert name in url


@pytest.mark.parametrize("lat,lon", [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_bad_coordinates_rejected(lat, lon):
    with pytest.raises(ValueError):
        forecast_url(lat, lon)


def test_fetch_uses_injected_getter_and_returns_data():
    seen = []
    data = fetch_forecast(46.55, 7.98, get=lambda u: seen.append(u) or synth())
    assert "hourly" in data and seen and seen[0].startswith("https://api.open-meteo.com/")


def test_network_failure_becomes_forecast_error():
    def boom(_):
        raise TimeoutError("slow")

    with pytest.raises(ForecastError, match="slow"):
        fetch_forecast(0, 0, get=boom)


def test_api_error_payload_becomes_forecast_error():
    with pytest.raises(ForecastError, match="bad coords"):
        fetch_forecast(0, 0, get=lambda u: {"error": True, "reason": "bad coords"})


@pytest.mark.parametrize("payload", [[], {}, {"hourly": {}}, {"hourly": {"time": []}}])
def test_malformed_payload_rejected(payload):
    with pytest.raises(ForecastError):
        fetch_forecast(0, 0, get=lambda u: payload)


def test_frozen_real_response_is_accepted():
    path = next(FIXTURE_DIR.glob("01_*.json"))
    blob = json.loads(path.read_text(encoding="utf-8"))
    assert fetch_forecast(blob["meta"]["lat"], blob["meta"]["lon"], get=lambda u: blob["forecast"])


@pytest.mark.skipif(os.environ.get("ONEBAR_LIVE") != "1", reason="set ONEBAR_LIVE=1 for the live call")
def test_live_call():
    data = fetch_forecast(46.55, 7.98)
    assert len(data["hourly"]["time"]) == 72
