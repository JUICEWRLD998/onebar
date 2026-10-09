"""Polarity check: a reply must not deny a storm or rain the facts contain, nor announce one they rule out.

This is a deliberately small rule set, not language understanding:
- A reply is cut into clauses (sentence ends, commas, "and", "but").
- A clause is negated when it holds a negation word (no, not, none, without, never, unlikely, n't).
  "no-go" is not a negation.
- Facts hold an event (`storm_first`) and a clause denies it with no time qualifier: contradiction.
  A qualifier (before, until, by, now, later, or a clock time) makes the denial a claim about a
  window, which this check does not judge, so it passes.
- Facts rule the event out (`storm_none`) and a clause mentions it without negation: contradiction.
Topics with neither fact are never judged, because the data is missing and the reply cannot be blamed.
"""
from __future__ import annotations

import re

from onebar.facts.model import FactSet

_I = re.IGNORECASE

# topic -> (mention pattern, event fact key, ruled-out fact key)
TOPICS: dict[str, tuple[re.Pattern[str], str, str]] = {
    "storm": (re.compile(r"\b(?:thunder\w*|storm\w*|lightning)\b", _I), "storm_first", "storm_none"),
    "rain": (re.compile(r"\b(?:rain\w*|shower\w*|drizzl\w*|precip\w*)\b", _I), "rain_first", "rain_none"),
}

_CLAUSE = re.compile(r"[.!?;\n,]+|\b(?:and|but)\b", _I)
_NEGATION = re.compile(r"\bno\b(?!-)|\bnot\b|\bnone\b|\bwithout\b|\bnever\b|\bunlikely\b|n't\b|(?<![\d.])0%", _I)
_QUALIFIER = re.compile(r"\b(?:before|until|till|by|now|later|yet|soon|through)\b|\d{1,2}:\d{2}", _I)


def contradictions(reply: str, facts: FactSet) -> tuple[str, ...]:
    """Topic names (in TOPICS order) on which the reply contradicts the facts."""
    clauses = [c for c in _CLAUSE.split(reply) if c and c.strip()]
    found: list[str] = []
    for topic, (mention, event_key, none_key) in TOPICS.items():
        has_event, ruled_out = event_key in facts, none_key in facts
        if not (has_event or ruled_out):
            continue
        for clause in clauses:
            if not mention.search(clause):
                continue
            negated = _NEGATION.search(clause) is not None
            if has_event and negated and not _QUALIFIER.search(clause):
                found.append(topic)
                break
            if ruled_out and not negated:
                found.append(topic)
                break
    return tuple(found)
