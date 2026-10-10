"""The browser's copy of the forecast and the place lookup: validated, scoped to one session, short-lived."""
import copy
import json

import pytest

from onebar.channels.hints import HintStore
from onebar.facts.open_meteo import clean_forecast
from onebar.temporal import activities as A

from conftest import FIXTURE_DIR

REAL = json.loads((FIXTURE_DIR.parent / "open_meteo_46.55_7.98.json").read_text())
LAT, LON = 46.55, 7.98
ME, OTHER = "onebar-web:sess-aaaaaaaa", "onebar-web:sess-bbbbbbbb"


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def store(tmp_path, clock=None):
    return HintStore(tmp_path / "hints", ttl_s=1800, clock=clock or Clock())


def fc_hint(data=None, lat=LAT, lon=LON):
    return {"forecast": {"lat": lat, "lon": lon, "data": copy.deepcopy(REAL if data is None else data)}}


# --- clean_forecast: the shape check -----------------------------------------------------------------------------

def test_a_real_open_meteo_response_passes_and_keeps_only_what_the_engine_reads():
    raw = copy.deepcopy(REAL)
    raw["evil"] = "<script>"
    raw["hourly"]["extra_field"] = [1] * len(raw["hourly"]["time"])
    out = clean_forecast(raw, LAT, LON)
    assert "evil" not in out and "extra_field" not in out["hourly"]
    assert out["hourly"]["temperature_2m"] == REAL["hourly"]["temperature_2m"]
    assert out["daily"]["sunset"] == REAL["daily"]["sunset"]
    assert out["utc_offset_seconds"] == REAL["utc_offset_seconds"] and out["elevation"] == REAL["elevation"]


def _broken(mutate):
    raw = copy.deepcopy(REAL)
    mutate(raw)
    return raw


# Planted defects: each one must be refused. If any slips through, the check is decorative.
PLANTED = {
    "error payload": lambda d: d.update(error=True, reason="limit"),
    "missing variable": lambda d: d["hourly"].pop("wind_gusts_10m"),
    "short column": lambda d: d["hourly"]["cape"].pop(),
    "text where a number goes": lambda d: d["hourly"]["wind_gusts_10m"].__setitem__(3, "55"),
    "boolean where a number goes": lambda d: d["hourly"]["temperature_2m"].__setitem__(0, True),
    "infinite number": lambda d: d["hourly"]["temperature_2m"].__setitem__(0, float("inf")),
    "bad hour stamp": lambda d: d["hourly"]["time"].__setitem__(0, "tomorrow"),
    "bad sunset stamp": lambda d: d["daily"]["sunset"].__setitem__(0, "18:41"),
    "another place": lambda d: d.update(latitude=47.5),
    "offset out of range": lambda d: d.update(utc_offset_seconds=99 * 3600),
    "offset not a whole number": lambda d: d.update(utc_offset_seconds="7200"),
    "no hours": lambda d: [d["hourly"][k].clear() for k in d["hourly"]],
    "no daily block": lambda d: d.pop("daily"),
}


def test_planted_control_has_thirteen_defects():
    assert len(PLANTED) == 13


@pytest.mark.parametrize("name", sorted(PLANTED))
def test_every_planted_defect_is_refused(name):
    with pytest.raises(ValueError):
        clean_forecast(_broken(PLANTED[name]), LAT, LON)


def test_nulls_in_a_column_are_allowed_because_open_meteo_sends_them():
    raw = _broken(lambda d: d["hourly"]["precipitation_probability"].__setitem__(5, None))
    assert clean_forecast(raw, LAT, LON)["hourly"]["precipitation_probability"][5] is None


# --- HintStore ---------------------------------------------------------------------------------------------------

def test_a_saved_forecast_comes_back_for_the_same_session_and_place(tmp_path):
    s = store(tmp_path)
    assert s.save(ME, fc_hint()) is True
    got = s.forecast(ME, LAT, LON)
    assert got is not None and got["hourly"]["time"] == REAL["hourly"]["time"]


def test_another_session_never_sees_it(tmp_path):
    s = store(tmp_path)
    s.save(ME, fc_hint())
    assert s.forecast(OTHER, LAT, LON) is None


def test_another_place_never_gets_it(tmp_path):
    s = store(tmp_path)
    s.save(ME, fc_hint())
    assert s.forecast(ME, 46.56, LON) is None


def test_it_expires(tmp_path):
    clock = Clock()
    s = store(tmp_path, clock)
    s.save(ME, fc_hint())
    clock.t += 1801
    assert s.forecast(ME, LAT, LON) is None


def test_a_bad_forecast_is_dropped_and_nothing_is_stored(tmp_path):
    s = store(tmp_path)
    assert s.save(ME, fc_hint(_broken(PLANTED["text where a number goes"]))) is False
    assert s.forecast(ME, LAT, LON) is None


def test_garbage_hints_are_dropped(tmp_path):
    s = store(tmp_path)
    for raw in (None, "x", [], {}, {"forecast": "x"}, {"place": {"query": "Zermatt"}},
                {"forecast": {"lat": "a", "lon": 1, "data": REAL}}):
        assert s.save(ME, raw) is False


def test_a_place_lookup_is_matched_on_the_words_typed(tmp_path):
    s = store(tmp_path)
    s.save(ME, {"place": {"query": "Zermatt", "name": "Zermatt, Switzerland", "lat": 46.02, "lon": 7.75}})
    hit = s.place(ME, "  zermatt ")
    assert hit is not None and hit.name == "Zermatt, Switzerland" and (hit.lat, hit.lon) == (46.02, 7.75)
    assert s.place(ME, "Banff") is None
    assert s.place(OTHER, "Zermatt") is None


@pytest.mark.parametrize("place", [
    {"query": "Zermatt", "name": "Zermatt", "lat": 95, "lon": 7.75},
    {"query": "Zermatt", "name": "", "lat": 46.02, "lon": 7.75},
    {"query": "Zermatt", "name": "x" * 201, "lat": 46.02, "lon": 7.75},
    {"query": "Zermatt", "name": "Zer\nmatt", "lat": 46.02, "lon": 7.75},
    {"query": "", "name": "Zermatt", "lat": 46.02, "lon": 7.75},
])
def test_bad_place_hints_are_refused(tmp_path, place):
    s = store(tmp_path)
    assert s.save(ME, {"place": place}) is False


def test_a_later_hint_keeps_the_earlier_part_it_does_not_replace(tmp_path):
    s = store(tmp_path)
    s.save(ME, {"place": {"query": "Zermatt", "name": "Zermatt, Switzerland", "lat": LAT, "lon": LON}})
    s.save(ME, fc_hint())
    assert s.place(ME, "Zermatt") is not None and s.forecast(ME, LAT, LON) is not None


def test_file_names_do_not_carry_the_session(tmp_path):
    s = store(tmp_path)
    s.save(ME, fc_hint())
    names = [p.name for p in (tmp_path / "hints").iterdir()]
    assert names and all("sess" not in n for n in names)


# --- the activity uses it before the server's own call -------------------------------------------------------------

def _down(_url):
    raise TimeoutError("server-side forecast is throttled")


def test_the_activity_answers_from_the_browser_copy_when_the_server_cannot_fetch(tmp_path):
    s = store(tmp_path)
    s.save(ME, fc_hint())
    deps = A.Deps(sender=None, get_forecast=_down, hints=s)
    assert A._forecast(deps, LAT, LON, ME)["utc_offset_seconds"] == REAL["utc_offset_seconds"]


def test_without_a_matching_hint_the_server_call_still_decides(tmp_path):
    s = store(tmp_path)
    s.save(OTHER, fc_hint())
    deps = A.Deps(sender=None, get_forecast=_down, hints=s)
    with pytest.raises(A.ForecastError):
        A._forecast(deps, LAT, LON, ME)


def test_a_browser_copy_never_enters_the_shared_cache(tmp_path):
    s = store(tmp_path)
    s.save(ME, fc_hint())
    deps = A.Deps(sender=None, get_forecast=_down, hints=s)
    A._forecast(deps, LAT, LON, ME)
    with pytest.raises(A.ForecastError):  # another session at the same spot still needs a real fetch
        A._forecast(deps, LAT, LON, OTHER)


def test_place_resolves_from_the_hint_without_a_network_call(tmp_path, monkeypatch):
    s = store(tmp_path)
    s.save(ME, {"place": {"query": "Zermatt", "name": "Zermatt, Switzerland", "lat": LAT, "lon": LON}})
    s.save(ME, fc_hint())

    def no_geocode(_url):
        raise AssertionError("geocoder called although the browser already looked the place up")

    monkeypatch.setattr(A, "_wid", lambda: ME)
    acts = A.Activities(A.Deps(sender=None, get_forecast=_down, get_geocode=no_geocode, hints=s))
    res = acts.resolve_place(A.PlaceReq(place="Zermatt", coords=None))
    assert res.ok and res.place == "Zermatt, Switzerland" and res.offset_s == REAL["utc_offset_seconds"]
