import pytest

from onebar.temporal import activities as A
from conftest import synth


def deps(ttl, calls):
    def get(url):
        calls.append(url)
        fc = synth()
        fc["utc_offset_seconds"] = 0
        return fc

    return A.Deps(sender=None, get_forecast=get, cache_ttl_s=ttl)


def test_a_second_request_for_the_same_place_is_served_from_the_cache():
    calls = []
    d = deps(600, calls)
    a, b = A._forecast(d, 46.55, 7.98), A._forecast(d, 46.5504, 7.9796)  # same place at 2 decimals
    assert a is b and len(calls) == 1


def test_a_different_place_is_fetched_separately():
    calls = []
    d = deps(600, calls)
    A._forecast(d, 46.55, 7.98)
    A._forecast(d, 47.55, 7.98)
    assert len(calls) == 2


def test_an_expired_entry_is_refetched(monkeypatch):
    calls = []
    d = deps(600, calls)
    t = [1000.0]
    monkeypatch.setattr(A._time, "monotonic", lambda: t[0])
    A._forecast(d, 46.55, 7.98)
    t[0] += 599
    A._forecast(d, 46.55, 7.98)
    assert len(calls) == 1
    t[0] += 2
    A._forecast(d, 46.55, 7.98)
    assert len(calls) == 2


def test_ttl_zero_never_caches():
    calls = []
    d = deps(0, calls)
    A._forecast(d, 46.55, 7.98)
    A._forecast(d, 46.55, 7.98)
    assert len(calls) == 2


def test_a_failed_fetch_is_not_cached():
    from onebar.facts.open_meteo import ForecastError

    state = {"fail": True}

    def get(url):
        if state["fail"]:
            raise OSError("down")
        fc = synth()
        fc["utc_offset_seconds"] = 0
        return fc

    d = A.Deps(sender=None, get_forecast=get, cache_ttl_s=600)
    with pytest.raises(ForecastError):
        A._forecast(d, 1.0, 2.0)
    state["fail"] = False
    assert A._forecast(d, 1.0, 2.0)["utc_offset_seconds"] == 0
