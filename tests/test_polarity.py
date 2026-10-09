"""A reply must not deny a storm or rain that the facts contain, nor announce one the facts rule out."""
import pytest

from onebar.check.checker import check
from onebar.check.polarity import contradictions
from onebar.facts.model import Fact, FactSet

STORM = FactSet([Fact("storm_first", "14:40"), Fact("rain_first", "13:00"), Fact("gust_max", "30km/h")])
CALM = FactSet([Fact("storm_none", "no storm"), Fact("rain_none", "no rain"), Fact("gust_max", "30km/h")])

# Each reply is wrong against STORM (planted control: all must be flagged).
DENIES_STORM = [
    "No thunderstorms today. First thunderstorm hour: 14:40.",
    "No storm today.",
    "No storm. Gusts 30km/h.",
    "There is no storm risk.",
    "Not a storm in sight.",
    "No lightning expected. Storm from 14:40.",
    "Thunder is unlikely.",
    "No storm. Rain from 13:00.",
]
DENIES_RAIN = ["No rain today.", "Dry, no rain. Storm from 14:40.", "Rain is unlikely."]
# Each reply is wrong against CALM.
ANNOUNCES_STORM = ["Storm from 14:40.", "Thunderstorm risk this afternoon.", "Looks stormy. Gusts 30km/h."]
ANNOUNCES_RAIN = ["Rain from 13:00.", "Showers likely."]


@pytest.mark.parametrize("text", DENIES_STORM)
def test_denying_a_storm_that_exists_is_flagged(text):
    assert "storm" in contradictions(text, STORM)


@pytest.mark.parametrize("text", DENIES_RAIN)
def test_denying_rain_that_exists_is_flagged(text):
    assert "rain" in contradictions(text, STORM)


@pytest.mark.parametrize("text", ANNOUNCES_STORM)
def test_announcing_a_storm_the_facts_rule_out_is_flagged(text):
    assert "storm" in contradictions(text, CALM)


@pytest.mark.parametrize("text", ANNOUNCES_RAIN)
def test_announcing_rain_the_facts_rule_out_is_flagged(text):
    assert "rain" in contradictions(text, CALM)


@pytest.mark.parametrize(
    "text",
    [
        "Storm from 14:40.",
        "Storm from 14:40, after 14:00. Rain from 13:00.",
        "No storm before 14:00. Storm from 14:40.",  # qualified denial is true
        "No storm until 14:40.",
        "No-go. Storm from 14:40.",
        "Gusts 30km/h.",  # silence is not a contradiction
        "Caution. Rain from 13:00, storm 14:40.",
    ],
)
def test_true_or_silent_replies_are_not_flagged_against_a_storm(text):
    assert contradictions(text, STORM) == ()


@pytest.mark.parametrize(
    "text",
    ["No storm expected.", "No storm. No rain.", "Rain chance is 0%.", "Storm chance 0%.", "Looks OK. Gusts 30km/h.", "Storm unlikely. No rain.", "Thunderstorm: no storm."],
)
def test_true_or_silent_replies_are_not_flagged_against_calm(text):
    assert contradictions(text, CALM) == ()


def test_missing_data_means_nothing_to_contradict():
    assert contradictions("No storm. Rain soon.", FactSet([Fact("gust_max", "30km/h")])) == ()


def test_checker_reports_contradiction_as_a_reason():
    r = check("No thunderstorms today. First thunderstorm hour: 14:40.", STORM, "storm today?")
    assert not r.passed
    assert "contradiction:storm" in r.reasons
    assert check("Storm from 14:40.", STORM, "storm today?").passed
