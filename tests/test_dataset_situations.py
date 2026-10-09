import json
import random
from datetime import datetime

from onebar.check.checker import check
from onebar.dataset import questions as Q
from onebar.dataset import situations as S
from onebar.dataset.locations import Location
from onebar.dataset.serde import facts_from_json
from onebar.dataset.splits import split_of
from onebar.facts.engine import Trip, compute_facts
from onebar.template import build
from conftest import set_hour, synth

LOC = Location("osm:n1", "Alpha Peak", "peak", 46.55, 7.98, "alps_test", 3000.0)


def forecast(days=10, storm_days=()):
    fc = synth(start="2026-07-01", days=days)
    fc["utc_offset_seconds"] = 7200
    for d in storm_days:
        fc = set_hour(fc, f"2026-07-{d:02d}T15:00", weather_code=95)
    return fc


def run(seed=0, **kw):
    return S.sample_situations(LOC, forecast(), random.Random(seed), **kw)


def test_k_distinct_days_none_on_the_last_day_hours_in_range():
    sits = run(k=3)
    days = [s.at.date() for s in sits]
    assert len(sits) == 3 and len(set(days)) == 3
    assert all(d.day <= 9 for d in days)
    assert all(5 <= s.at.hour <= 17 for s in sits)


def test_sampling_is_deterministic_and_seed_sensitive():
    a, b, c = run(seed=3), run(seed=3), run(seed=4)
    assert a == b and a != c


def test_every_situation_has_forecast_coverage_for_the_whole_horizon():
    fc = forecast()
    for seed in range(40):
        for s in S.sample_situations(LOC, fc, random.Random(seed), k=3):
            f = compute_facts(fc, s.at, trip=s.trip)
            assert "now" in f and "gust_max" in f


def test_storm_steering_picks_a_storm_hour_when_one_exists():
    fc = forecast(storm_days=(2, 4, 6, 8))
    for seed in range(60):
        sits = S.sample_situations(LOC, fc, random.Random(seed), k=3, storm_bias=1.0)
        # four storm days exist and only three situations are asked for, so every one must be steered to a storm
        assert all("storm_first" in compute_facts(fc, s.at) for s in sits), sits
        assert len({s.at.date() for s in sits}) == 3


def test_no_storm_anywhere_still_yields_situations():
    assert len(run(storm_bias=1.0)) == 3


def test_zero_bias_does_not_steer():
    fc = forecast(storm_days=(2, 4, 6, 8))
    stormy = lambda bias: sum(
        "storm_first" in compute_facts(fc, s.at)
        for seed in range(60)
        for s in S.sample_situations(LOC, fc, random.Random(seed), k=3, storm_bias=bias)
    )
    assert stormy(1.0) > stormy(0.0)


def test_trip_return_is_two_to_nine_hours_out_on_the_same_day():
    seen = 0
    for seed in range(80):
        for s in S.sample_situations(LOC, forecast(), random.Random(seed), k=3, trip_p=1.0):
            if s.trip is None:
                continue  # crossed midnight, so no trip
            seen += 1
            back = datetime.combine(s.at.date(), s.trip.return_by)
            assert 2 * 3600 <= (back - s.at).total_seconds() <= 9 * 3600
            assert s.trip.return_by.minute % 15 == 0
    assert seen > 50


def test_trip_probability_zero_gives_no_trips():
    assert all(s.trip is None for s in run(trip_p=0.0))


def test_row_roundtrips_to_the_same_facts_and_is_json_clean():
    fc = forecast(storm_days=(3,))
    rng = random.Random(1)
    sit = S.Situation(LOC, datetime(2026, 7, 3, 10, 20), Trip(datetime(2026, 7, 3, 17, 0).time()))
    seed = next(s for s in Q.SEEDS if s.needs_time)
    row = json.loads(json.dumps(S.build_row(sit, fc, seed, rng)))
    assert row["id"] == "osm:n1|2026-07-03T10:20"
    assert row["split"] == split_of(LOC.lat, LOC.lon)
    assert row["trip"] == {"return_by": "17:00", "descent_min": 90}
    assert row["question"] == row["seed_question"] and row["paraphrased"] is False
    assert row["loc"]["name"] == "Alpha Peak"
    facts = facts_from_json(row["facts"])
    again = compute_facts(fc, sit.at, trip=sit.trip, question=row["question"])
    assert [(f.key, f.token) for f in facts] == [(f.key, f.token) for f in again]
    assert "target" in facts  # the time slot produced a target fact


def test_row_without_trip_and_timeless_seed():
    fc = forecast()
    sit = S.Situation(LOC, datetime(2026, 7, 3, 10, 20), None)
    seed = next(s for s in Q.SEEDS if not s.needs_time)
    row = S.build_row(sit, fc, seed, random.Random(0))
    assert row["trip"] is None and "target" not in {f["key"] for f in row["facts"]}
    assert row["intents"]


def test_template_answers_every_generated_row_and_the_checker_accepts_it():
    fc = forecast(storm_days=(2, 5))
    rng = random.Random(9)
    for _ in range(300):
        sit = S.sample_situations(LOC, fc, rng, k=1)[0]
        row = S.build_row(sit, fc, Q.draw_seed(rng), rng)
        facts = facts_from_json(row["facts"])
        reply = build(facts, row["question"])
        assert check(reply, facts, row["question"]).passed, (row["question"], reply)
