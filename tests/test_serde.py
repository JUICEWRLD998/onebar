import json
from datetime import datetime, time

from onebar.dataset.serde import facts_from_json, facts_to_json
from onebar.facts.engine import Trip, compute_facts
from onebar.facts.model import Fact, FactSet
from onebar.template import build
from conftest import load_real_fixtures, set_hour, synth

AT = datetime(2026, 10, 8, 10, 20)


def test_roundtrip_preserves_keys_tokens_values_and_hours():
    fc = set_hour(synth(), "2026-10-08T14:00", weather_code=95)
    f = compute_facts(fc, AT, trip=Trip(time(17, 0)), question="by 3pm?")
    g = facts_from_json(json.loads(json.dumps(facts_to_json(f))))
    assert [(x.key, x.token, x.value, x.hour) for x in f] == [(x.key, x.token, x.value, x.hour) for x in g]
    assert isinstance(g.get("storm_first").value, datetime)
    assert isinstance(g.get("gust_max").value, float)
    assert g.get("dark_now") is None


def test_roundtrip_keeps_bool_none_and_int_distinct():
    f = FactSet([Fact("a", "x", True), Fact("b", "y", None), Fact("c", "z", 5), Fact("d", "w", 2.5)])
    g = facts_from_json(json.loads(json.dumps(facts_to_json(f))))
    assert [x.value for x in g] == [True, None, 5, 2.5]
    assert [type(x.value) for x in g] == [bool, type(None), int, float]


def test_template_gives_the_same_reply_before_and_after_a_roundtrip():
    for name, fc, at in load_real_fixtures():
        for storm in (False, True):
            f = compute_facts(set_hour(fc, at.strftime("%Y-%m-%dT14:00"), weather_code=95) if storm else fc,
                              at, trip=Trip(time(17, 0)), question="storm by 3pm, turn around?")
            g = facts_from_json(json.loads(json.dumps(facts_to_json(f))))
            assert build(f, "storm by 3pm, turn around?") == build(g, "storm by 3pm, turn around?"), name
