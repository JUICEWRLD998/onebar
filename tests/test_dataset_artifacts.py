"""Invariants of the built dataset files. Skipped when the files have not been built (a fresh clone without data/)."""
import json
from pathlib import Path

import pytest

from onebar.check.checker import check
from onebar.check.intents import classify, parse_target
from onebar.check.numbers import extract
from onebar.dataset import teacher
from onebar.dataset.serde import facts_from_json
from onebar.dataset.splits import cell, split_of
from onebar.template import build

ROOT = Path(__file__).resolve().parents[1]
FILES = {"train": ROOT / "data" / "train.jsonl", "val": ROOT / "data" / "val.jsonl", "test": ROOT / "eval" / "test.jsonl"}

pytestmark = pytest.mark.skipif(not all(p.is_file() for p in FILES.values()), reason="dataset not built")


@pytest.fixture(scope="module")
def data():
    return {k: [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()] for k, p in FILES.items()}


def test_sizes_meet_the_phase_exit(data):
    assert len(data["train"]) + len(data["val"]) >= 2000
    assert len(data["test"]) >= 200


def test_row_ids_are_unique_across_all_files(data):
    ids = [r["id"] for rows in data.values() for r in rows]
    assert len(ids) == len(set(ids))


def test_each_row_sits_in_the_split_its_coordinates_hash_to(data):
    for name, rows in data.items():
        for r in rows:
            assert r["split"] == name == split_of(r["loc"]["lat"], r["loc"]["lon"]), r["id"]


def test_no_location_and_no_map_cell_is_in_two_splits(data):
    locs = {name: {r["loc"]["id"] for r in rows} for name, rows in data.items()}
    cells = {name: {cell(r["loc"]["lat"], r["loc"]["lon"]) for r in rows} for name, rows in data.items()}
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        assert not locs[a] & locs[b], (a, b)
        assert not cells[a] & cells[b], (a, b)


def test_every_training_reply_passes_the_checker_and_reads_naturally(data):
    for name in ("train", "val"):
        for r in data[name]:
            facts = facts_from_json(r["facts"])
            res = check(r["reply"], facts, r["question"])
            assert res.passed, (r["id"], r["reply"], res.reasons)
            assert res.septets <= 160 and res.septets == r["septets"]
            assert teacher.natural(r["reply"]), (r["id"], r["reply"])


def test_the_template_answers_every_row_of_every_split(data):
    for rows in data.values():
        for r in rows:
            facts = facts_from_json(r["facts"])
            assert check(build(facts, r["question"]), facts, r["question"]).passed, r["id"]


def test_facts_agree_with_the_question_that_will_be_asked(data):
    """Serving recomputes facts from the question text, so a `target` fact must exist exactly when the question names a time."""
    for rows in data.values():
        for r in rows:
            has_target = any(f["key"] == "target" for f in r["facts"])
            assert has_target == (parse_target(r["question"]) is not None), (r["id"], r["question"])


def test_paraphrases_kept_every_number_and_the_intents_of_their_seed(data):
    n = 0
    for rows in data.values():
        for r in rows:
            assert r["intents"] == classify(r["question"]), r["id"]
            if r["paraphrased"]:
                n += 1
                assert sorted(h.text.lower() for h in extract(r["question"])) == sorted(
                    h.text.lower() for h in extract(r["seed_question"])
                ), r["id"]
    assert n > 0


def test_the_data_exercises_storms_trips_and_every_intent(data):
    rows = data["train"] + data["val"]
    assert sum(any(f["key"] == "storm_first" for f in r["facts"]) for r in rows) / len(rows) > 0.05  # storms are rare in real forecasts
    assert sum(r["trip"] is not None for r in rows) / len(rows) > 0.3
    assert {i for r in rows for i in r["intents"]} >= {
        "storm", "rain", "wind", "daylight", "temperature", "turnaround", "go_nogo", "general"
    }
