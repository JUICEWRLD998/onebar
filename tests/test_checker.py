from datetime import datetime, time

import pytest

from onebar.check.checker import check
from onebar.facts.engine import Trip, compute_facts
from onebar.facts.model import Fact, FactSet

from conftest import set_hour, synth

AT = datetime(2026, 10, 8, 10, 20)


def scenario(question: str) -> FactSet:
    """Calm day with a storm at 14:00, 55km/h gusts at 15:00, -3C feels at 17:00, trip back 17:00."""
    fc = synth()
    fc = set_hour(fc, "2026-10-08T10:00", temperature_2m=5.6)
    fc = set_hour(fc, "2026-10-08T14:00", weather_code=95, precipitation_probability=80, precipitation=1.0)
    fc = set_hour(fc, "2026-10-08T15:00", wind_gusts_10m=54.5)
    fc = set_hour(fc, "2026-10-08T17:00", apparent_temperature=-3.2)
    return compute_facts(fc, AT, trip=Trip(return_by=time(17, 0)), question=question)


GOOD = [
    ("storm before I'm back at the car?",
     "Storm from 14:00, gusts 55km/h at 15:00. Be at the car by 15:30 to stay ahead of it."),
    ("when is sunset", "Sunset 18:30, 8h10m of light left."),
    ("how windy is it up top", "Gusts up to 55km/h around 15:00."),
    ("how cold will it get", "6C now, feels down to -3C by evening."),
    ("ridge by 3 then car ok?",
     "Storm from 14:00 and gusts 55km/h. Ridge by 15:00 is too late. Turn by 15:30."),
    ("will it rain", "Rain from 14:00, 80% chance."),
]


@pytest.mark.parametrize("question,reply", GOOD)
def test_good_replies_pass(question, reply):
    res = check(reply, scenario(question), question)
    assert res.passed, res.reasons
    assert res.reasons == ()
    assert res.septets <= 160


def test_trace_maps_each_number_to_its_fact_and_hour():
    q = "how windy is it up top"
    res = check("Gusts up to 55km/h around 15:00.", scenario(q), q)
    by_text = {n.text: n for n in res.numbers}
    assert by_text["55km/h"].sources == (("gust_max", "2026-10-08T15:00"),)
    assert ("gust_max_at", "2026-10-08T15:00") in by_text["15:00"].sources
    assert res.intents == ("wind",)


# --- planted positive control: ten replies, one defect each. 10/10 must fail. ---------------------
PLANTED = [
    ("too_long", "storm?", "Storm from 14:00. " + "x" * 150),
    ("too_long", "storm?", "a" * 159 + "["),
    ("charset", "storm?", "Storm from 14:00 \U0001F329"),
    ("charset", "how cold will it get", "Feels -3°C by evening."),
    ("charset", "storm?", "Storm from 14:00, don’t go."),
    ("invented_number", "storm?", "Storm from 16:00, gusts 55km/h."),
    ("invented_number", "how windy is it up top", "Gusts up to 55mph around 15:00."),
    ("invented_number", "how cold will it get", "6C now, feels 3C later."),
    ("missing_fact", "when is sunset", "It gets dark early today, plan ahead."),
    ("empty", "storm?", "   "),
]


@pytest.mark.parametrize("code,question,reply", PLANTED)
def test_planted_defect_is_rejected(code, question, reply):
    res = check(reply, scenario(question), question)
    assert not res.passed
    assert any(r.split(":")[0] == code for r in res.reasons), res.reasons


def test_planted_control_is_exactly_ten_and_all_fail():
    assert len(PLANTED) == 10
    failed = sum(not check(r, scenario(q), q).passed for _, q, r in PLANTED)
    assert failed == 10


def test_a_checker_that_accepts_everything_would_be_caught():
    # the good set must pass while the planted set fails: both directions are exercised
    assert all(check(r, scenario(q), q).passed for q, r in GOOD)
    assert not any(check(r, scenario(q), q).passed for _, q, r in PLANTED)


# --- finer behaviour -------------------------------------------------------------------------------
def test_boundary_160_passes_161_fails():
    facts = FactSet([Fact("storm_none", "no storm")])
    ok = "no storm " + "a" * 151
    assert len(ok) == 160 and check(ok, facts, "storm?").passed
    bad = "no storm " + "a" * 152
    res = check(bad, facts, "storm?")
    assert not res.passed and "too_long:161" in res.reasons


def test_question_number_is_allowed_in_reply():
    facts = FactSet([Fact("storm_none", "no storm")])
    res = check("No storm before 15:00.", facts, "storm by 3?")
    assert res.passed, res.reasons


def test_missing_required_fact_reason_names_the_group():
    q = "when is sunset"
    res = check("Dark soon.", scenario(q), q)
    assert "missing_fact:sunset" in res.reasons


def test_alternative_in_group_is_enough():
    facts = FactSet([Fact("dark_now", "dark"), Fact("sunset", "18:30")])
    assert check("It is dark now.", facts, "when is sunset").passed
    assert check("Sunset 18:30.", facts, "when is sunset").passed


def test_group_with_no_facts_is_not_demanded():
    facts = FactSet([Fact("now", "10:20")])
    assert check("Cannot say.", facts, "when is sunset").passed


def test_storm_none_token_matches_case_insensitively():
    facts = FactSet([Fact("storm_none", "no storm")])
    assert check("No storm expected.", facts, "storm?").passed
    assert not check("All good.", facts, "storm?").passed


def test_time_token_must_match_whole_number():
    facts = FactSet([Fact("sunset", "18:30")])
    assert not check("Sunset 118:30.", facts, "when is sunset").passed
    assert not check("Sunset around 18:300.", facts, "when is sunset").passed


def test_all_reasons_are_reported_together():
    res = check("\U0001F329 16:00", scenario("storm?"), "storm?")
    codes = {r.split(":")[0] for r in res.reasons}
    assert {"charset", "invented_number", "missing_fact"} <= codes
