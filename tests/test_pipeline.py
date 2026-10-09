from datetime import datetime, time, timedelta, timezone

import pytest

from onebar import pipeline
from onebar.check.checker import check
from onebar.facts.engine import Trip
from onebar.facts.open_meteo import ForecastError, local_now
from onebar.model.client import ModelError
from conftest import set_hour, synth

AT = datetime(2026, 10, 8, 10, 20)
Q = "storm before 3?"
GOOD = "No storm."
BAD_NUMBER = "No storm until 99:99."


class Script:
    """A fake model: returns or raises the scripted outcomes in order, and records its prompts."""

    def __init__(self, *outcomes):
        self.outcomes, self.prompts = list(outcomes), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def run(draft, forecast=None, question=Q, trip=None):
    return pipeline.answer(question, AT, forecast or synth(), draft, trip=trip)


def test_first_draft_passes():
    d = Script(GOOD)
    r = run(d)
    assert (r.text, r.path) == (GOOD, "model")
    assert len(d.prompts) == 1 and len(r.attempts) == 1
    assert r.result.passed


def test_failed_draft_gets_one_retry_with_the_reasons():
    d = Script(BAD_NUMBER, GOOD)
    r = run(d)
    assert (r.text, r.path) == (GOOD, "model-retry")
    assert len(d.prompts) == 2
    assert BAD_NUMBER in d.prompts[1] and "not in the facts" in d.prompts[1]
    assert [a.source for a in r.attempts] == ["model", "model-retry"]
    assert r.attempts[0].result.passed is False


def test_two_failures_fall_back_to_the_template():
    d = Script(BAD_NUMBER, "Storm at 88:88.")
    r = run(d)
    assert r.path == "template"
    assert [a.source for a in r.attempts] == ["model", "model-retry", "template"]
    assert r.result.passed and r.text == r.attempts[-1].text
    assert len(d.prompts) == 2


def test_model_error_goes_straight_to_the_template_without_a_retry():
    d = Script(ModelError("TimeoutError: slow"))
    r = run(d)
    assert r.path == "template" and len(d.prompts) == 1
    assert r.attempts[0].error == "TimeoutError: slow" and r.attempts[0].result is None
    assert r.result.passed


def test_error_on_the_retry_still_ends_in_the_template():
    d = Script(BAD_NUMBER, ModelError("boom"))
    r = run(d)
    assert r.path == "template"
    assert [a.source for a in r.attempts] == ["model", "model-retry", "template"]
    assert r.attempts[1].error == "boom"


def test_no_model_means_template_only():
    r = run(None)
    assert r.path == "template" and len(r.attempts) == 1 and r.result.passed


def test_reply_text_is_exactly_what_the_checker_passed():
    fc = set_hour(synth(), "2026-10-08T14:00", weather_code=95)
    for draft in (Script("Storm from 14:00."), Script(BAD_NUMBER, "Storm from 14:00."), Script(BAD_NUMBER, BAD_NUMBER), None):
        r = run(draft, fc)
        facts = r.facts
        assert check(r.text, facts, Q).passed
        assert r.result == check(r.text, facts, Q)


def test_latency_uses_the_injected_clock():
    ticks = iter(range(100))
    r = pipeline.answer_from_facts(Q, pipeline.compute_facts(synth(), AT, question=Q), Script(GOOD), clock=lambda: float(next(ticks)))
    assert r.latency_s > 0 and r.attempts[0].latency_s > 0


def test_trip_facts_reach_the_template():
    r = run(None, question="turn around time?", trip=Trip(time(17, 0)))
    assert "15:30" in r.text


def test_forecast_gap_raises_value_error():
    with pytest.raises(ValueError, match="does not cover"):
        pipeline.answer(Q, datetime(2030, 1, 1, 10, 0), synth(), None)


def test_local_now_applies_the_forecast_offset():
    utc = datetime(2026, 10, 8, 8, 30, tzinfo=timezone.utc)
    assert local_now({"utc_offset_seconds": 7200}, utc) == datetime(2026, 10, 8, 10, 30)
    assert local_now({"utc_offset_seconds": -5 * 3600}, utc) == datetime(2026, 10, 8, 3, 30)
    assert local_now({"utc_offset_seconds": 20700}, utc).minute == 15  # +05:45 Nepal


def test_local_now_without_offset_is_an_error():
    with pytest.raises(ForecastError):
        local_now({})
