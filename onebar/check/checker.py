"""The adjudicator: pure function from (reply, facts, question) to pass/fail plus a trace.

Reason codes (the retry prompt and the UI read these):
  empty                    reply is blank
  too_long:<n>             more than 160 septets
  charset:<chars>          characters outside GSM-7
  invented_number:<text>   a number that is in no fact and not in the question
  missing_fact:<k1|k2>     the question needs one of these facts and the reply states none
  contradiction:<topic>    the reply denies a storm or rain the facts contain, or announces one they rule out
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from onebar.check.gsm7 import LIMIT, analyze
from onebar.check.intents import classify, required_groups
from onebar.check.numbers import NumberTrace, extract, invented, trace_numbers
from onebar.check.polarity import contradictions
from onebar.facts.model import FactSet


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    reasons: tuple[str, ...]
    septets: int
    intents: tuple[str, ...]
    numbers: tuple[NumberTrace, ...]


def _states(reply: str, token: str) -> bool:
    """True when the reply states this fact token."""
    if re.search(r"\d", token):
        return any(hit.text == token for hit in extract(reply))
    return re.search(r"\b" + re.escape(token), reply, re.IGNORECASE) is not None


def check(reply: str, facts: FactSet, question: str) -> CheckResult:
    intents = tuple(classify(question))
    if not reply.strip():
        return CheckResult(False, ("empty",), 0, intents, ())

    reasons: list[str] = []
    gsm = analyze(reply)
    if gsm.bad_chars:
        reasons.append("charset:" + "".join(gsm.bad_chars))
    if gsm.septets > LIMIT:
        reasons.append(f"too_long:{gsm.septets}")

    traces = trace_numbers(reply, facts, question)
    reasons.extend(f"invented_number:{text}" for text in invented(traces))

    reasons.extend(f"contradiction:{topic}" for topic in contradictions(reply, facts))

    for group in required_groups(list(intents)):
        present = [k for k in group if k in facts]
        if not present:
            continue  # the data is missing, so the reply cannot be blamed
        if not any(_states(reply, facts.token(k)) for k in present):
            reasons.append("missing_fact:" + "|".join(present))

    return CheckResult(not reasons, tuple(reasons), gsm.septets, intents, tuple(traces))
