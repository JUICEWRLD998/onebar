import random
import re
from collections import Counter
from datetime import datetime, timedelta

import pytest

from onebar.check.intents import classify, parse_target
from onebar.dataset import questions as Q
from onebar.facts.engine import resolve_target

INTENTS = {"storm", "rain", "wind", "daylight", "temperature", "turnaround", "go_nogo", "general"}


def test_seed_ids_and_texts_are_unique():
    assert len({s.id for s in Q.SEEDS}) == len(Q.SEEDS) >= 40
    assert len({s.text for s in Q.SEEDS}) == len(Q.SEEDS)


def test_seeds_carry_no_digits_except_through_the_time_slot():
    for s in Q.SEEDS:
        assert not re.search(r"\d", s.text), s.text


def test_every_intent_is_covered_by_at_least_three_seeds():
    cover = Counter(i for s in Q.SEEDS for i in classify(s.text.format(t="3pm")))
    assert set(cover) == INTENTS
    assert min(cover.values()) >= 3, cover


def test_time_seeds_are_a_real_share_of_the_pool():
    n = sum(s.needs_time for s in Q.SEEDS)
    assert 8 <= n <= len(Q.SEEDS) // 2


@pytest.mark.parametrize("hour", [5, 7, 9, 10, 12, 14, 16, 17])
def test_filled_times_read_back_as_a_future_time_the_same_day(hour):
    at = datetime(2026, 7, 14, hour, 20)
    rng = random.Random(hour)
    for s in (x for x in Q.SEEDS if x.needs_time):
        for _ in range(60):
            q = Q.fill(s, at, rng)
            raw = parse_target(q)
            assert raw is not None, q
            target = resolve_target(raw, at)
            assert target.date() == at.date(), q
            assert timedelta(minutes=70) <= target - at <= timedelta(hours=7, minutes=45), (q, target)
            assert target.minute in (0, 30)


def test_fill_leaves_timeless_seeds_unchanged():
    s = next(x for x in Q.SEEDS if not x.needs_time)
    assert Q.fill(s, datetime(2026, 7, 14, 10, 0), random.Random(0)) == s.text


def test_time_phrase_forms():
    assert Q.time_phrases(datetime(2026, 1, 1, 15, 0)) == ["3", "3pm", "3 pm", "15:00", "15:00"]
    assert Q.time_phrases(datetime(2026, 1, 1, 9, 30)) == ["9:30", "9:30am", "09:30"]
    assert Q.time_phrases(datetime(2026, 1, 1, 12, 0))[1] == "12pm"


def test_fill_is_deterministic_for_a_seeded_rng():
    s = next(x for x in Q.SEEDS if x.needs_time)
    at = datetime(2026, 7, 14, 10, 0)
    assert Q.fill(s, at, random.Random(5)) == Q.fill(s, at, random.Random(5))
