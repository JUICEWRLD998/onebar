"""Eval metrics: pure functions from pipeline replies to the numbers in eval/TABLE.md.

Definitions (the table repeats them):
- first-try pass: the first draft passed the checker. For the template system the template is the only draft.
- served by model: the reply that went out came from the model (first try or the one retry), not the template.
- invented-number rate: share of first drafts with at least one number that is in no fact and not in the question.
- contradiction rate: share of first drafts that deny a storm/rain in the facts or announce one they rule out.
- required-fact coverage: mean over questions of (required fact groups the first draft stated / groups demanded).
- septets: GSM-7 length of the reply that went out.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from onebar.check.intents import required_groups
from onebar.facts.model import FactSet
from onebar.pipeline import TEMPLATE, Reply


@dataclass(frozen=True)
class RowScore:
    id: str
    path: str
    reply: str
    septets: int
    first_passed: bool
    first_reasons: tuple[str, ...]
    first_text: str
    model_error: bool
    groups_demanded: int
    groups_missing: int
    latency_s: float


def score_row(row_id: str, reply: Reply, facts: FactSet) -> RowScore:
    first = reply.attempts[0]
    reasons = first.result.reasons if first.result else ()
    demanded = [g for g in required_groups(list(reply.result.intents)) if any(k in facts for k in g)]
    missing = sum(1 for r in reasons if r.startswith("missing_fact:"))
    return RowScore(
        id=row_id,
        path=reply.path,
        reply=reply.text,
        septets=reply.result.septets,
        first_passed=bool(first.result and first.result.passed),
        first_reasons=tuple(reasons),
        first_text=first.text,
        model_error=first.error is not None,
        groups_demanded=len(demanded),
        groups_missing=min(missing, len(demanded)),
        latency_s=reply.latency_s,
    )


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile; 0 for an empty list."""
    if not values:
        return 0.0
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def _rate(scores: list[RowScore], pred) -> float:
    return sum(1 for s in scores if pred(s)) / len(scores) if scores else 0.0


def aggregate(scores: list[RowScore], latencies: list[float] | None = None) -> dict:
    """`latencies` come from a separate sequential run; the full run is concurrent, so its timings are inflated."""
    judged = [s for s in scores if not s.model_error]  # a dead endpoint says nothing about draft quality
    coverage = [1 - s.groups_missing / s.groups_demanded for s in judged if s.groups_demanded]
    return {
        "n": len(scores),
        "first_try_pass": _rate(scores, lambda s: s.first_passed),
        "served_by_model": _rate(scores, lambda s: s.path != TEMPLATE),
        "template_fallback": _rate(scores, lambda s: s.path == TEMPLATE),
        "model_errors": sum(s.model_error for s in scores),
        "invented_number_rate": _rate(judged, lambda s: any(r.startswith("invented_number") for r in s.first_reasons)),
        "contradiction_rate": _rate(judged, lambda s: any(r.startswith("contradiction") for r in s.first_reasons)),
        "too_long_rate": _rate(judged, lambda s: any(r.startswith("too_long") for r in s.first_reasons)),
        "required_fact_coverage": sum(coverage) / len(coverage) if coverage else 1.0,
        "septets_mean": sum(s.septets for s in scores) / len(scores) if scores else 0.0,
        "septets_p95": percentile([s.septets for s in scores], 95),
        "latency_p50_s": percentile(latencies or [], 50),
        "latency_p95_s": percentile(latencies or [], 95),
        "latency_n": len(latencies or []),
    }


def cost_per_answer(prompt_tokens: int, completion_tokens: int, answers: int, price: dict | None) -> float | None:
    """USD per answer at the published per-million-token prices; None when no price is known; 0 with no model."""
    if price is None:
        return None
    if answers <= 0:
        return 0.0
    usd = (prompt_tokens * price["prefill"] + completion_tokens * price["sample"]) / 1_000_000
    return usd / answers
