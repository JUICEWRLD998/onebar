from datetime import datetime

import pytest

from onebar.facts import render
from onebar.facts.model import Fact, FactSet


def test_clock_zero_pads():
    assert render.clock(datetime(2026, 10, 8, 9, 5)) == "09:05"
    assert render.clock(datetime(2026, 10, 8, 14, 40)) == "14:40"
    assert render.clock(datetime(2026, 10, 8, 0, 0)) == "00:00"


@pytest.mark.parametrize("x,want", [(79.5, "80%"), (79.4, "79%"), (0, "0%"), (100, "100%")])
def test_percent(x, want):
    assert render.percent(x) == want


@pytest.mark.parametrize("x,want", [(54.5, "55km/h"), (0.2, "0km/h"), (21.0, "21km/h")])
def test_speed(x, want):
    assert render.speed(x) == want


@pytest.mark.parametrize(
    "x,want", [(5.6, "6C"), (0.5, "1C"), (-0.5, "0C"), (-3.2, "-3C"), (-3.5, "-3C"), (20.0, "20C")]
)
def test_temp_rounds_half_up_with_sign(x, want):
    assert render.temp(x) == want


def test_metres():
    assert render.metres(3219.0) == "3219m"
    assert render.metres(0.4) == "0m"


@pytest.mark.parametrize(
    "mins,want", [(0, "0m"), (45, "45m"), (60, "1h"), (130, "2h10m"), (59.6, "1h"), (125.4, "2h5m")]
)
def test_duration(mins, want):
    assert render.duration(mins) == want


def test_duration_rejects_negative():
    with pytest.raises(ValueError):
        render.duration(-1)


def test_factset_basics():
    a = Fact("a", "1m")
    b = Fact("b", "2m")
    fs = FactSet([a, b])
    assert "a" in fs and "z" not in fs
    assert len(fs) == 2
    assert fs.token("b") == "2m" and fs.token("z") is None
    assert fs.keys() == ["a", "b"]
    assert fs.without("a").keys() == ["b"]
    assert fs.with_fact(Fact("c", "3m")).keys() == ["a", "b", "c"]
    assert [f.key for f in fs] == ["a", "b"]


def test_factset_rejects_duplicate_keys():
    with pytest.raises(ValueError):
        FactSet([Fact("a", "1m"), Fact("a", "2m")])
