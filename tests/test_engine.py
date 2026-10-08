from datetime import datetime, time

import pytest

from onebar.check.gsm7 import analyze
from onebar.check.intents import RawTime
from onebar.check.numbers import extract
from onebar.facts.engine import Trip, compute_facts, resolve_target

from conftest import set_hour, synth

AT = datetime(2026, 10, 8, 10, 20)


def tok(fs, key):
    return fs.token(key)


def test_basic_calm_day(calm):
    fs = compute_facts(calm, AT)
    assert tok(fs, "now") == "10:20"
    assert tok(fs, "temp_now") == "10C"
    assert tok(fs, "feels_min") == "8C"
    assert tok(fs, "gust_max") == "20km/h"
    assert tok(fs, "pop_max") == "0%"
    assert tok(fs, "storm_none") == "no storm"
    assert "storm_first" not in fs
    assert tok(fs, "rain_none") == "no rain"
    assert tok(fs, "elevation") == "3219m"


def test_storm_by_weather_code(calm):
    fs = compute_facts(set_hour(calm, "2026-10-08T14:00", weather_code=95), AT)
    assert tok(fs, "storm_first") == "14:00"
    assert fs.get("storm_first").hour == "2026-10-08T14:00"
    assert "storm_none" not in fs


@pytest.mark.parametrize("code", [95, 96, 99])
def test_storm_codes(calm, code):
    fs = compute_facts(set_hour(calm, "2026-10-08T13:00", weather_code=code), AT)
    assert tok(fs, "storm_first") == "13:00"


def test_code_94_and_100_are_not_storms(calm):
    for code in (94, 100, 80):
        fs = compute_facts(set_hour(calm, "2026-10-08T13:00", weather_code=code), AT)
        assert "storm_first" not in fs


def test_storm_by_cape_needs_probability(calm):
    hot = set_hour(calm, "2026-10-08T15:00", cape=1200.0, precipitation_probability=70)
    assert tok(compute_facts(hot, AT), "storm_first") == "15:00"
    dry = set_hour(calm, "2026-10-08T15:00", cape=1200.0, precipitation_probability=50)
    assert "storm_first" not in compute_facts(dry, AT)
    low = set_hour(calm, "2026-10-08T15:00", cape=900.0, precipitation_probability=90)
    assert "storm_first" not in compute_facts(low, AT)


def test_first_storm_hour_wins(calm):
    fc = set_hour(calm, "2026-10-08T17:00", weather_code=95)
    fc = set_hour(fc, "2026-10-08T13:00", weather_code=96)
    assert tok(compute_facts(fc, AT), "storm_first") == "13:00"


def test_storm_before_now_hour_ignored_but_current_hour_counts(calm):
    past = set_hour(calm, "2026-10-08T09:00", weather_code=95)
    assert "storm_first" not in compute_facts(past, AT)
    now = set_hour(calm, "2026-10-08T10:00", weather_code=95)
    assert tok(compute_facts(now, AT), "storm_first") == "10:00"


def test_horizon_edges(calm):
    inside = set_hour(calm, "2026-10-08T21:00", weather_code=95)
    outside = set_hour(calm, "2026-10-08T22:00", weather_code=95)
    assert "storm_first" in compute_facts(inside, AT)
    assert "storm_first" not in compute_facts(outside, AT)
    short = set_hour(calm, "2026-10-08T14:00", weather_code=95)
    assert "storm_first" not in compute_facts(short, AT, horizon_h=3)


def test_gust_max_and_time(calm):
    fc = set_hour(calm, "2026-10-08T12:00", wind_gusts_10m=40.0)
    fc = set_hour(fc, "2026-10-08T15:00", wind_gusts_10m=54.5)
    fs = compute_facts(fc, AT)
    assert tok(fs, "gust_max") == "55km/h"
    assert tok(fs, "gust_max_at") == "15:00"
    assert fs.get("gust_max").hour == "2026-10-08T15:00"


def test_gust_tie_takes_earliest(calm):
    fc = set_hour(calm, "2026-10-08T12:00", wind_gusts_10m=50.0)
    fc = set_hour(fc, "2026-10-08T15:00", wind_gusts_10m=50.0)
    assert tok(compute_facts(fc, AT), "gust_max_at") == "12:00"


def test_pop_max(calm):
    fc = set_hour(calm, "2026-10-08T16:00", precipitation_probability=80)
    fs = compute_facts(fc, AT)
    assert tok(fs, "pop_max") == "80%"
    assert fs.get("pop_max").hour == "2026-10-08T16:00"


def test_rain_first_needs_amount_and_probability(calm):
    ok = set_hour(calm, "2026-10-08T13:00", precipitation=0.3, precipitation_probability=60)
    assert tok(compute_facts(ok, AT), "rain_first") == "13:00"
    light = set_hour(calm, "2026-10-08T13:00", precipitation=0.1, precipitation_probability=90)
    assert "rain_first" not in compute_facts(light, AT)
    unlikely = set_hour(calm, "2026-10-08T13:00", precipitation=2.0, precipitation_probability=40)
    assert "rain_first" not in compute_facts(unlikely, AT)


def test_temperature_facts(calm):
    fc = set_hour(calm, "2026-10-08T10:00", temperature_2m=5.6)
    fc = set_hour(fc, "2026-10-08T17:00", apparent_temperature=-3.2)
    fs = compute_facts(fc, AT)
    assert tok(fs, "temp_now") == "6C"
    assert tok(fs, "feels_min") == "-3C"
    assert fs.get("feels_min").hour == "2026-10-08T17:00"


def test_sun_daytime(calm):
    fs = compute_facts(calm, AT)
    assert tok(fs, "sunset") == "18:30"
    assert tok(fs, "sunrise") == "07:30"
    assert fs.get("sunrise").value == datetime(2026, 10, 9, 7, 30)
    assert tok(fs, "daylight_left") == "8h10m"
    assert "dark_now" not in fs


def test_sun_after_sunset(calm):
    fs = compute_facts(calm, datetime(2026, 10, 8, 19, 0))
    assert tok(fs, "dark_now") == "dark"
    assert "daylight_left" not in fs
    assert fs.get("sunset").value == datetime(2026, 10, 9, 18, 30)
    assert tok(fs, "sunrise") == "07:30"


def test_sun_before_sunrise(calm):
    fs = compute_facts(calm, datetime(2026, 10, 8, 5, 0))
    assert tok(fs, "dark_now") == "dark"
    assert fs.get("sunrise").value == datetime(2026, 10, 8, 7, 30)
    assert fs.get("sunset").value == datetime(2026, 10, 8, 18, 30)


def test_exact_sunset_is_dark(calm):
    assert "dark_now" in compute_facts(calm, datetime(2026, 10, 8, 18, 30))
    assert "dark_now" not in compute_facts(calm, datetime(2026, 10, 8, 18, 29))


def test_missing_sun_data_skips_sun_facts(calm):
    calm["daily"]["sunset"] = [None, None]
    calm["daily"]["sunrise"] = [None, None]
    fs = compute_facts(calm, AT)
    for key in ("sunset", "sunrise", "dark_now", "daylight_left"):
        assert key not in fs


def test_elevation_missing(calm):
    del calm["elevation"]
    assert "elevation" not in compute_facts(calm, AT)


def test_trip_car_and_turn_by(calm):
    fs = compute_facts(calm, AT, trip=Trip(return_by=time(17, 0)))
    assert tok(fs, "car_by") == "17:00"
    assert tok(fs, "turn_by") == "15:30"
    assert "turn_now" not in fs


def test_trip_descent_minutes(calm):
    fs = compute_facts(calm, AT, trip=Trip(return_by=time(17, 0), descent_min=60))
    assert tok(fs, "turn_by") == "16:00"


def test_trip_past_turn_by_becomes_turn_now(calm):
    fs = compute_facts(calm, datetime(2026, 10, 8, 16, 0), trip=Trip(return_by=time(17, 0)))
    assert tok(fs, "turn_now") == "turn now"
    assert "turn_by" not in fs
    assert tok(fs, "car_by") == "17:00"


def test_trip_return_already_passed_rolls_to_tomorrow(calm):
    fs = compute_facts(calm, datetime(2026, 10, 8, 17, 30), trip=Trip(return_by=time(17, 0)))
    assert fs.get("car_by").value == datetime(2026, 10, 9, 17, 0)


def test_no_trip_no_trip_facts(calm):
    fs = compute_facts(calm, AT)
    for key in ("car_by", "turn_by", "turn_now"):
        assert key not in fs


def test_target_from_question(calm):
    fs = compute_facts(calm, AT, question="ridge by 3 then car ok?")
    assert tok(fs, "target") == "15:00"
    assert fs.get("target").value == datetime(2026, 10, 8, 15, 0)


def test_no_target_without_a_time(calm):
    assert "target" not in compute_facts(calm, AT, question="storm?")


@pytest.mark.parametrize(
    "raw,at,want",
    [
        (RawTime(3, 0, None), datetime(2026, 10, 8, 10, 20), datetime(2026, 10, 8, 15, 0)),
        (RawTime(3, 0, None), datetime(2026, 10, 8, 16, 0), datetime(2026, 10, 9, 3, 0)),
        (RawTime(3, 0, None), datetime(2026, 10, 8, 2, 0), datetime(2026, 10, 8, 3, 0)),
        (RawTime(3, 0, "pm"), datetime(2026, 10, 8, 10, 20), datetime(2026, 10, 8, 15, 0)),
        (RawTime(3, 0, "am"), datetime(2026, 10, 8, 10, 20), datetime(2026, 10, 9, 3, 0)),
        (RawTime(12, 0, "am"), datetime(2026, 10, 8, 10, 20), datetime(2026, 10, 9, 0, 0)),
        (RawTime(12, 0, "pm"), datetime(2026, 10, 8, 10, 20), datetime(2026, 10, 8, 12, 0)),
        (RawTime(15, 30, None), datetime(2026, 10, 8, 10, 20), datetime(2026, 10, 8, 15, 30)),
        (RawTime(12, 0, None), datetime(2026, 10, 8, 10, 20), datetime(2026, 10, 8, 12, 0)),
    ],
)
def test_resolve_target(raw, at, want):
    assert resolve_target(raw, at) == want


def test_forecast_must_cover_the_time(calm):
    with pytest.raises(ValueError):
        compute_facts(calm, datetime(2026, 10, 12, 10, 0))
    with pytest.raises(ValueError):
        compute_facts(calm, datetime(2026, 10, 7, 23, 0))


def test_last_forecast_hour_still_works(calm):
    fs = compute_facts(calm, datetime(2026, 10, 9, 23, 30))
    assert tok(fs, "now") == "23:30"


def test_nulls_are_ignored(calm):
    fc = set_hour(calm, "2026-10-08T12:00", wind_gusts_10m=None, weather_code=None, cape=None)
    fs = compute_facts(fc, AT)
    assert tok(fs, "gust_max") == "20km/h"


def test_all_null_series_omits_the_fact():
    fc = synth()
    fc["hourly"]["wind_gusts_10m"] = [None] * len(fc["hourly"]["time"])
    fs = compute_facts(fc, AT)
    assert "gust_max" not in fs and "gust_max_at" not in fs


def test_missing_series_omits_the_fact():
    fc = synth()
    del fc["hourly"]["precipitation_probability"]
    fs = compute_facts(fc, AT)
    assert "pop_max" not in fs


def test_deterministic(calm):
    a = compute_facts(calm, AT, question="car by 3?")
    b = compute_facts(calm, AT, question="car by 3?")
    assert [(f.key, f.token) for f in a] == [(f.key, f.token) for f in b]


def test_real_fixtures_compute_and_tokens_are_clean(real_fixtures):
    storm_free = 0
    for name, fc, at in real_fixtures:
        fs = compute_facts(fc, at, trip=Trip(return_by=time(17, 0)), question="by 3?")
        for key in ("now", "temp_now", "feels_min", "gust_max", "pop_max", "sunset", "elevation",
                    "car_by", "turn_by", "target"):
            assert key in fs, f"{name} missing {key}"
        assert ("storm_first" in fs) != ("storm_none" in fs), name
        storm_free += "storm_none" in fs
        for fact in fs:
            assert analyze(fact.token).fits, (name, fact.key, fact.token)
            hits = extract(fact.token)
            assert len(hits) <= 1, (name, fact.key, fact.token)
            if hits:
                assert hits[0].text == fact.token, (name, fact.key, fact.token)
    assert storm_free >= 15  # real October forecasts: few storms
