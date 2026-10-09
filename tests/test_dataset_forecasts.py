import json
import urllib.error
from datetime import date, timedelta

import pytest

from onebar.dataset import forecasts as F
from onebar.facts.open_meteo import ForecastError
from conftest import synth


def good():
    fc = synth(days=3)
    fc["utc_offset_seconds"] = 7200
    return fc


def http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, None)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(F.time, "sleep", lambda s: None)


def test_url_covers_the_window_and_all_variables():
    url = F.window_url(46.55, 7.98, date(2025, 7, 10), days=10)
    assert "start_date=2025-07-10" in url and "end_date=2025-07-19" in url
    for var in ("cape", "wind_gusts_10m", "precipitation_probability", "sunset", "timezone=auto"):
        assert var in url


def test_url_rejects_bad_coordinates():
    with pytest.raises(ValueError):
        F.window_url(91, 0, date(2025, 7, 10))


def test_pick_start_is_stable_in_range_and_varies():
    a = F.pick_start("osm:n1", seed=7)
    assert a == F.pick_start("osm:n1", seed=7)
    starts = {F.pick_start(f"osm:n{i}", seed=7) for i in range(200)}
    assert len(starts) > 50
    assert all(F.EARLIEST <= s and s + timedelta(days=F.WINDOW_DAYS - 1) <= F.LATEST_END for s in starts)


def test_fetch_caches_to_disk_and_second_call_makes_no_request(tmp_path):
    calls = []

    def get(url):
        calls.append(url)
        return good()

    a = F.fetch_window("osm:n5", 1.0, 2.0, date(2025, 7, 1), tmp_path, get=get)
    b = F.fetch_window("osm:n5", 1.0, 2.0, date(2025, 7, 1), tmp_path, get=get)
    assert a == b and len(calls) == 1
    assert (tmp_path / "osm_n5_2025-07-01.json").is_file()


def test_transient_errors_are_retried(tmp_path):
    seq = [http_error(429), OSError("reset"), good()]

    def get(url):
        out = seq.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    assert F.fetch_window("osm:n6", 1.0, 2.0, date(2025, 7, 1), tmp_path, get=get)["utc_offset_seconds"] == 7200


def test_client_error_fails_fast_without_retry(tmp_path):
    calls = []

    def get(url):
        calls.append(1)
        raise http_error(400)

    with pytest.raises(ForecastError, match="HTTP 400"):
        F.fetch_window("osm:n7", 1.0, 2.0, date(2025, 7, 1), tmp_path, get=get)
    assert len(calls) == 1


def test_persistent_failure_raises_and_writes_nothing(tmp_path):
    def get(url):
        raise OSError("down")

    with pytest.raises(ForecastError, match="osm:n8"):
        F.fetch_window("osm:n8", 1.0, 2.0, date(2025, 7, 1), tmp_path, get=get, retries=2)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"error": True, "reason": "x"},
        {"hourly": {"time": []}},
        {"hourly": {"time": [], "temperature_2m": []}},
        {"hourly": {"time": [], "temperature_2m": []}, "utc_offset_seconds": 0},
    ],
)
def test_incomplete_responses_are_rejected(bad):
    with pytest.raises(ForecastError):
        F.validate(bad)


def test_corrupt_cache_is_not_silently_trusted(tmp_path):
    (tmp_path / "osm_n9_2025-07-01.json").write_text(json.dumps({"hourly": {}}), encoding="utf-8")
    with pytest.raises(ForecastError):
        F.fetch_window("osm:n9", 1.0, 2.0, date(2025, 7, 1), tmp_path, get=lambda u: good())
