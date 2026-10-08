from datetime import datetime, time, timedelta

from onebar.check.checker import check
from onebar.check.gsm7 import LIMIT, analyze
from onebar.facts.engine import Trip, compute_facts
from onebar.facts.model import Fact, FactSet
from onebar.template import FALLBACK, build

from conftest import set_hour, synth

QUESTIONS = [
    "storm?",
    "will it rain on the summit",
    "how windy is it up top",
    "when is sunset",
    "how cold will it get",
    "should I turn back",
    "ridge by 3 then car ok?",
    "storm before I'm back at the car?",
    "is it safe to go",
    "will it be dark by 6",
    "hello",
    "wind and storm and cold?",
    "storm? windy? dark? cold? rain? turn back? ok?",
    "back by 5pm ok?",
]
TRIPS = [None, Trip(return_by=time(17, 0))]
HOURS = [(10, 20), (16, 50), (22, 30)]


def _storm_variant(fc: dict, at: datetime) -> dict:
    when = (at + timedelta(hours=3)).strftime("%Y-%m-%dT%H:00")
    fc = set_hour(fc, when, weather_code=95, precipitation=1.0, precipitation_probability=80)
    return set_hour(fc, when, wind_gusts_10m=62.0)


def _assert_valid(text: str, facts: FactSet, question: str, ctx):
    assert text, ctx
    assert analyze(text).fits, (ctx, text)
    res = check(text, facts, question)
    assert res.passed, (ctx, text, res.reasons)


def test_template_passes_checker_on_every_fixture_question_time_and_trip(real_fixtures):
    cases = 0
    for name, fc, base in real_fixtures:
        for hh, mm in HOURS:
            at = base.replace(hour=hh, minute=mm)
            for variant in (fc, _storm_variant(fc, at)):
                for trip in TRIPS:
                    for q in QUESTIONS:
                        facts = compute_facts(variant, at, trip=trip, question=q)
                        _assert_valid(build(facts, q), facts, q, (name, at, trip, q))
                        cases += 1
    assert cases == 20 * 3 * 2 * 2 * len(QUESTIONS)


AT = datetime(2026, 10, 8, 10, 20)


def test_storm_before_the_car_says_before():
    fc = set_hour(synth(), "2026-10-08T14:00", weather_code=95)
    q = "storm before I'm back at the car?"
    facts = compute_facts(fc, AT, trip=Trip(return_by=time(17, 0)), question=q)
    text = build(facts, q)
    assert "before 17:00" in text and "Storm from 14:00" in text


def test_storm_after_the_car_says_after():
    fc = set_hour(synth(), "2026-10-08T19:00", weather_code=95)
    q = "storm before I'm back at the car?"
    facts = compute_facts(fc, AT, trip=Trip(return_by=time(17, 0)), question=q)
    assert "after 17:00" in build(facts, q)


def test_no_storm_text():
    facts = compute_facts(synth(), AT, question="storm?")
    assert build(facts, "storm?").startswith("No storm")


def test_go_nogo_verdicts():
    q = "ridge by 3 then car ok?"
    stormy = compute_facts(set_hour(synth(), "2026-10-08T14:00", weather_code=95), AT, question=q)
    assert build(stormy, q).startswith("No-go.")
    later = compute_facts(set_hour(synth(), "2026-10-08T20:00", weather_code=95), AT, question=q)
    assert build(later, q).startswith("Caution.")
    gusty = compute_facts(set_hour(synth(), "2026-10-08T13:00", wind_gusts_10m=65.0), AT, question=q)
    assert build(gusty, q).startswith("Caution.")
    calm = compute_facts(synth(), AT, question=q)
    assert build(calm, q).startswith("Looks OK.")


def test_no_verdict_without_storm_data():
    fc = synth()
    del fc["hourly"]["weather_code"]
    del fc["hourly"]["cape"]
    facts = compute_facts(fc, AT, question="is it safe to go")
    text = build(facts, "is it safe to go")
    assert "Looks OK" not in text and "Gusts" in text


def test_turn_now_and_turn_by_wording():
    q = "should I turn back"
    soon = compute_facts(synth(), datetime(2026, 10, 8, 16, 0), trip=Trip(return_by=time(17, 0)), question=q)
    assert "Turn now" in build(soon, q)
    early = compute_facts(synth(), AT, trip=Trip(return_by=time(17, 0)), question=q)
    assert "Turn by 15:30" in build(early, q)


def test_dark_wording():
    q = "when is sunset"
    facts = compute_facts(synth(), datetime(2026, 10, 8, 20, 0), question=q)
    text = build(facts, q)
    assert text.startswith("Dark now") and "07:30" in text


def test_daylight_wording():
    q = "when is sunset"
    text = build(compute_facts(synth(), AT, question=q), q)
    assert "Sunset 18:30" in text and "8h10m" in text


def test_temperature_wording_keeps_the_sign():
    fc = set_hour(synth(), "2026-10-08T17:00", apparent_temperature=-3.2)
    q = "how cold will it get"
    assert "-3C" in build(compute_facts(fc, AT, question=q), q)


def test_general_question_gets_storm_and_extras():
    facts = compute_facts(synth(), AT, question="hello")
    text = build(facts, "hello")
    assert "No storm" in text and "Gusts to" in text and "Sunset" in text


def test_no_usable_facts_returns_the_plain_fallback():
    facts = FactSet([Fact("now", "10:20")])
    text = build(facts, "storm?")
    assert text == FALLBACK
    assert analyze(text).fits and len(text) <= LIMIT


def test_never_exceeds_160_even_with_every_intent():
    q = QUESTIONS[12]
    facts = compute_facts(set_hour(synth(), "2026-10-08T14:00", weather_code=95), AT,
                          trip=Trip(return_by=time(17, 0)), question=q)
    text = build(facts, q)
    assert analyze(text).septets <= LIMIT
    assert check(text, facts, q).passed
