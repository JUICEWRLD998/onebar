"""question + forecast -> one checked reply. Pure apart from the injected `draft` callable and the clock.

Flow: facts -> model draft -> check -> (one retry with the failure reasons) -> template.
The template is code and passes the checker by construction, so a reply always goes out.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from onebar.check.checker import CheckResult, check
from onebar.facts.engine import Trip, compute_facts
from onebar.facts.model import FactSet
from onebar.model import prompt as prompts
from onebar.model.client import Draft, ModelError
from onebar.template import build as build_template

MODEL = "model"
MODEL_RETRY = "model-retry"
TEMPLATE = "template"


@dataclass(frozen=True)
class Attempt:
    source: str  # "model", "model-retry" or "template"
    text: str
    result: CheckResult | None  # None when the model gave no text
    error: str | None = None
    latency_s: float = 0.0


@dataclass(frozen=True)
class Reply:
    text: str
    path: str  # which attempt produced the text
    result: CheckResult  # the checker's verdict and number trace for `text`
    attempts: tuple[Attempt, ...]
    latency_s: float
    facts: FactSet = field(repr=False, default_factory=FactSet)


def answer_from_facts(
    question: str,
    facts: FactSet,
    draft: Draft | None,
    clock: Callable[[], float] = time.perf_counter,
) -> Reply:
    """`draft=None` means no model: the template answers."""
    t0 = clock()
    attempts: list[Attempt] = []

    def try_model(source: str, previous: str | None, reasons: tuple[str, ...]) -> Attempt:
        started = clock()
        try:
            text = draft(prompts.render(facts, question, previous, reasons))
        except ModelError as exc:
            return Attempt(source, "", None, str(exc), clock() - started)
        return Attempt(source, text, check(text, facts, question), None, clock() - started)

    if draft is not None:
        first = try_model(MODEL, None, ())
        attempts.append(first)
        if first.result and first.result.passed:
            return Reply(first.text, MODEL, first.result, tuple(attempts), clock() - t0, facts)
        if first.result is not None:  # a model error skips the retry: do not spend another timeout
            retry = try_model(MODEL_RETRY, first.text, first.result.reasons)
            attempts.append(retry)
            if retry.result and retry.result.passed:
                return Reply(retry.text, MODEL_RETRY, retry.result, tuple(attempts), clock() - t0, facts)

    started = clock()
    text = build_template(facts, question)
    result = check(text, facts, question)
    attempts.append(Attempt(TEMPLATE, text, result, None, clock() - started))
    return Reply(text, TEMPLATE, result, tuple(attempts), clock() - t0, facts)


def answer(
    question: str,
    at: datetime,
    forecast: dict,
    draft: Draft | None,
    trip: Trip | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> Reply:
    facts = compute_facts(forecast, at, trip=trip, question=question)
    return answer_from_facts(question, facts, draft, clock)
