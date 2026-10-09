import json
from datetime import datetime
from pathlib import Path

import pytest

from onebar import train_data as T
from onebar.dataset.serde import facts_to_json
from onebar.facts.engine import compute_facts
from onebar.model.prompt import STOP, render
from conftest import synth

TRAIN = Path(__file__).resolve().parents[1] / "data" / "train.jsonl"


def tok(text: str) -> list[int]:
    """Stand-in tokenizer: one token per character, the end-of-turn marker as one token."""
    out, i = [], 0
    while i < len(text):
        if text.startswith(STOP, i):
            out.append(9999)
            i += len(STOP)
        else:
            out.append(ord(text[i]))
            i += 1
    return out


def test_layout_shifts_targets_and_masks_the_prompt():
    ex = T.build_example(tok, "AB", "xy")
    # tokens: A B x y <end>
    assert ex.input_ids == [65, 66, 120, 121]
    assert ex.target_ids == [66, 120, 121, 9999]
    assert ex.weights == [0.0, 1.0, 1.0, 1.0]
    assert len(ex.input_ids) == len(ex.target_ids) == len(ex.weights) == ex.n_tokens
    assert ex.n_trained == 3


def test_trained_targets_are_exactly_the_reply_and_the_end_token():
    ex = T.build_example(tok, "PROMPT", "Storm 14:40.")
    trained = [t for t, w in zip(ex.target_ids, ex.weights) if w]
    assert trained == tok("Storm 14:40.") + [9999]


def test_prompt_is_the_serving_prompt_byte_for_byte():
    q = "storm before 3?"
    facts = compute_facts(synth(), datetime(2026, 10, 8, 10, 20), question=q)
    row = {"facts": facts_to_json(facts), "question": q, "reply": "No storm."}
    assert T.prompt_for(row) == render(facts, q)
    assert T.prompt_for(row).endswith("<think>\n\n</think>\n\n")


def test_normalise_gives_a_per_token_mean_over_the_batch():
    batch = [T.build_example(tok, "AB", "xy"), T.build_example(tok, "ABC", "z")]
    w = T.normalise(batch)
    assert sum(sum(x) for x in w) == pytest.approx(1.0)
    assert [len(a) for a in w] == [e.n_tokens for e in batch]
    assert w[0][0] == 0.0  # prompt positions stay masked


def test_estimate_cost():
    ex = [T.build_example(tok, "A" * 99, "B")] * 10
    per = ex[0].n_tokens
    assert T.estimate_cost(ex, epochs=2, train_usd_per_m=0.44) == pytest.approx(10 * per * 2 * 0.44 / 1e6)


@pytest.mark.skipif(not TRAIN.is_file(), reason="dataset not built")
def test_rows_in_the_built_dataset_all_produce_trainable_examples():
    rows = [json.loads(line) for line in TRAIN.read_text(encoding="utf-8").splitlines()][:300]
    for ex in T.build_examples(tok, rows):
        assert ex.n_trained >= 2 and ex.weights[-1] == 1.0
