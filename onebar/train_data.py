"""SFT examples: the exact serving prompt as context, the teacher's reply plus the end-of-turn token as the target.

Next-token layout: input = tokens[:-1], target = tokens[1:]. Weights are 0 where the target is a prompt token and
1 where it is the reply or the end-of-turn token, so the model is trained on its answer only. Batch weights are
scaled to a per-token mean so the learning rate does not depend on reply length.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from onebar.dataset.serde import facts_from_json
from onebar.model.prompt import STOP, render

Tokenize = Callable[[str], list[int]]


@dataclass(frozen=True)
class Example:
    input_ids: list[int]
    target_ids: list[int]
    weights: list[float]

    @property
    def n_tokens(self) -> int:
        return len(self.input_ids)

    @property
    def n_trained(self) -> int:
        return int(sum(self.weights))


def prompt_for(row: dict) -> str:
    """The same string the pipeline sends at serving time (model.prompt.render)."""
    return render(facts_from_json(row["facts"]), row["question"])


def build_example(tokenize: Tokenize, prompt: str, reply: str) -> Example:
    p = tokenize(prompt)
    c = tokenize(reply + STOP)
    tokens = p + c
    return Example(
        input_ids=tokens[:-1],
        target_ids=tokens[1:],
        weights=[0.0] * (len(p) - 1) + [1.0] * len(c),
    )


def build_examples(tokenize: Tokenize, rows: list[dict]) -> list[Example]:
    return [build_example(tokenize, prompt_for(r), r["reply"]) for r in rows]


def normalise(batch: list[Example]) -> list[list[float]]:
    """Per-token mean over the whole batch."""
    total = sum(e.n_trained for e in batch) or 1
    return [[w / total for w in e.weights] for e in batch]


def estimate_cost(examples: list[Example], epochs: int, train_usd_per_m: float) -> float:
    return sum(e.n_tokens for e in examples) * epochs * train_usd_per_m / 1_000_000
