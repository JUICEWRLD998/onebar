from datetime import datetime, time

from onebar.facts.engine import Trip, compute_facts
from onebar.facts.model import Fact
from onebar.model import prompt
from conftest import synth, set_hour

AT = datetime(2026, 10, 8, 10, 20)


def facts(question="storm before 3?", trip=None):
    return compute_facts(synth(), AT, trip=trip, question=question)


def test_facts_block_shows_every_token_and_no_internal_key():
    f = facts(trip=Trip(time(17, 0)))
    block = prompt.facts_block(f)
    for fact in f:
        assert fact.token in block
    for key in ("gust_max", "storm_none", "car_by", "turn_by", "pop_max"):
        assert key not in block


def test_every_engine_fact_key_has_a_label():
    storm = set_hour(synth(), "2026-10-08T14:00", weather_code=95)
    f = compute_facts(storm, AT, trip=Trip(time(17, 0)), question="by 3?")
    f = f.with_fact(Fact("dark_now", "dark", True)).with_fact(Fact("turn_now", "turn now"))
    missing = [x.key for x in f if x.key not in prompt.LABELS]
    assert missing == []


def test_render_is_a_closed_think_qwen_prompt():
    out = prompt.render(facts(), "storm before 3?")
    assert out.startswith("<|im_start|>system\n")
    assert out.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert "Question: storm before 3?" in out
    assert out.count("<|im_start|>") == 3


def test_retry_prompt_quotes_the_draft_and_explains_reasons_without_keys():
    out = prompt.render(
        facts(), "storm?", previous="No storm 99%", reasons=("invented_number:99%", "missing_fact:gust_max|storm_first")
    )
    assert "'No storm 99%'" in out
    assert "not in the facts" in out and "99%" in out
    assert "strongest wind gust in the next hours" in out
    assert "gust_max" not in out


def test_first_prompt_has_no_retry_text():
    assert "rejected" not in prompt.render(facts(), "storm?")


def test_explain_unknown_code_passes_through():
    assert prompt.explain("weird") == "weird"
