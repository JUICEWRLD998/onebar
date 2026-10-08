import pytest

from onebar.check.numbers import extract, invented, trace_numbers
from onebar.facts.model import Fact, FactSet


def texts(s):
    return [h.text for h in extract(s)]


def test_extract_basic():
    assert texts("Storm 14:40, gusts 55km/h.") == ["14:40", "55km/h"]


def test_extract_signed_and_percent():
    assert texts("6C now, feels -3C, 80% rain") == ["6C", "-3C", "80%"]


def test_sign_only_when_not_glued_to_a_word():
    assert texts("ridge-3C") == ["3C"]
    assert texts("10-12") == ["10", "12"]


def test_extract_durations():
    assert texts("2h10m of light") == ["2h10m"]
    assert texts("about 2h left") == ["2h"]
    assert texts("10min") == ["10min"]


def test_slash_between_times_is_not_a_unit():
    assert texts("14:40/15:00") == ["14:40", "15:00"]


def test_digit_glued_to_letters_is_still_found():
    assert texts("A4") == ["4"]
    assert texts("Qwen3") == ["3"]


def test_decimals_and_units():
    assert texts("2.5km then 3") == ["2.5km", "3"]


def test_extract_none():
    assert extract("") == []
    assert extract("no numbers here") == []


def test_extract_positions():
    hit = extract("go 14:40 now")[0]
    assert (hit.start, hit.end) == (3, 8)


FACTS = FactSet(
    [
        Fact("storm_first", "14:40", hour="2026-10-08T14:00"),
        Fact("gust_max", "55km/h", hour="2026-10-08T15:00"),
        Fact("temp_now", "6C"),
        Fact("feels_min", "-3C", hour="2026-10-08T17:00"),
        Fact("storm_none", "no storm"),
    ]
)


def ok_map(reply, question="", facts=FACTS):
    return {t.text: t.ok for t in trace_numbers(reply, facts, question)}


def test_fact_tokens_accepted_with_sources():
    tr = trace_numbers("Storm 14:40, gusts 55km/h", FACTS, "")
    assert [t.ok for t in tr] == [True, True]
    assert tr[0].sources == (("storm_first", "2026-10-08T14:00"),)
    assert tr[1].sources == (("gust_max", "2026-10-08T15:00"),)


def test_invented_time_rejected():
    assert ok_map("Storm 16:00") == {"16:00": False}


def test_wrong_unit_rejected():
    assert ok_map("gusts 55mph") == {"55mph": False}


def test_space_before_unit_rejected():
    assert ok_map("gusts 55 km/h") == {"55": False}


def test_sign_loss_rejected():
    assert ok_map("feels 3C") == {"3C": False}
    assert ok_map("feels -3C") == {"-3C": True}


def test_bare_question_number_accepted():
    assert ok_map("ridge at 3", question="ridge by 3 then car ok?") == {"3": True}


def test_question_hour_maps_to_24h_times():
    q = "ridge by 3 then car ok?"
    for t in ("15:00", "03:00", "3:00"):
        assert ok_map(f"Reach ridge {t}", question=q) == {t: True}
    tr = trace_numbers("Reach ridge 15:00", FACTS, q)
    assert tr[0].sources == (("question", None),)


def test_question_hour_does_not_allow_other_forms():
    q = "ridge by 3 then car ok?"
    assert ok_map("15", question=q) == {"15": False}
    assert ok_map("15:30", question=q) == {"15:30": False}
    assert ok_map("3C", question=q) == {"3C": False}


def test_pm_question_allows_only_the_24h_form():
    q = "back by 5pm"
    assert ok_map("Back 17:00", question=q) == {"17:00": True}
    assert ok_map("Back 05:00", question=q) == {"05:00": False}


def test_question_clock_with_minutes():
    q = "back at 3:30"
    assert ok_map("15:30", question=q) == {"15:30": True}
    assert ok_map("03:30", question=q) == {"03:30": True}
    assert ok_map("15:00", question=q) == {"15:00": False}


def test_question_number_over_23_is_not_a_time():
    q = "wind over 55"
    assert ok_map("55", question=q) == {"55": True}
    assert ok_map("55:00", question=q) == {"55:00": False}
    assert ok_map("55km/h", question=q, facts=FactSet()) == {"55km/h": False}


def test_question_unit_number_accepted_as_written():
    assert ok_map("at 3000m", question="is 3000m ok") == {"3000m": True}


def test_same_token_from_two_facts_lists_both_sources():
    facts = FactSet([Fact("a", "14:40", hour="h1"), Fact("b", "14:40", hour="h2")])
    tr = trace_numbers("14:40", facts, "")
    assert {s[0] for s in tr[0].sources} == {"a", "b"}


def test_invented_helper_lists_failures_only():
    tr = trace_numbers("Storm 14:40 and 16:00 and 55mph", FACTS, "")
    assert invented(tr) == ["16:00", "55mph"]


def test_no_numbers_means_nothing_invented():
    assert invented(trace_numbers("No storm today.", FACTS, "")) == []


@pytest.mark.parametrize("bad", ["1", "00", "99%", "24:00x"])
def test_random_numbers_are_rejected(bad):
    assert not ok_map(f"x {bad}")[bad]
