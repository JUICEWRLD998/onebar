"""Every number in a reply must trace to a fact token or to a number the hiker wrote.

A "number" is a span of digits plus the unit glued to it: 14:40, 55km/h, 80%, -3C, 2h10m.
It is compared as one string, so 55mph, 55 km/h or a lost minus sign all count as invented.
The same extractor reads the fact tokens, so a token and its use in a reply cannot drift apart.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from onebar.facts.model import FactSet

# sign (only when not glued to a word), then body, then the unit glued to it.
_NUMBER = re.compile(
    r"(?:(?<!\w)(?P<sign>-))?"
    r"(?P<body>\d+h\d+m|\d+(?::\d+)?(?:\.\d+)?)"
    r"(?P<unit>[A-Za-z]+(?:/[A-Za-z]+)?|%)?"
)

Source = tuple[str, str | None]  # (fact key or "question", forecast hour ISO)


@dataclass(frozen=True)
class NumberHit:
    text: str
    start: int
    end: int
    body: str
    unit: str


@dataclass(frozen=True)
class NumberTrace:
    text: str
    start: int
    end: int
    ok: bool
    sources: tuple[Source, ...]


def extract(text: str) -> list[NumberHit]:
    hits = []
    for m in _NUMBER.finditer(text):
        hits.append(
            NumberHit(
                text=m.group(0),
                start=m.start(),
                end=m.end(),
                body=m.group("body"),
                unit=m.group("unit") or "",
            )
        )
    return hits


def _clock_forms(hour: int, minute: int) -> set[str]:
    return {f"{hour:02d}:{minute:02d}", f"{hour}:{minute:02d}"}


def _question_allowed(question: str) -> set[str]:
    """Strings the hiker's own numbers allow: as written, plus the 24-hour form of a clock time."""
    allowed: set[str] = set()
    for hit in extract(question):
        allowed.add(hit.text.lstrip("-"))
        meridiem = hit.unit.lower() if hit.unit.lower() in ("am", "pm") else None
        if hit.unit and meridiem is None:
            continue  # 3000m, 55km/h: allowed as written only
        if ":" in hit.body:
            h_s, m_s = hit.body.split(":", 1)
            if not (h_s.isdigit() and m_s.isdigit()):
                continue
            hour, minute = int(h_s), int(m_s)
            if hour > 23 or minute > 59:
                continue
        elif hit.body.isdigit() and int(hit.body) <= 23:
            hour, minute = int(hit.body), 0
        else:
            continue
        if meridiem:
            if not 1 <= hour <= 12:
                continue
            hour = hour % 12 + (12 if meridiem == "pm" else 0)
            allowed |= _clock_forms(hour, minute)
        else:
            allowed |= _clock_forms(hour, minute)
            if 1 <= hour < 12:
                allowed |= _clock_forms(hour + 12, minute)
    return allowed


def trace_numbers(reply: str, facts: FactSet, question: str) -> list[NumberTrace]:
    by_token: dict[str, list[Source]] = {}
    for fact in facts:
        for hit in extract(fact.token):
            sources = by_token.setdefault(hit.text, [])
            if (fact.key, fact.hour) not in sources:
                sources.append((fact.key, fact.hour))
    from_question = _question_allowed(question)

    traces = []
    for hit in extract(reply):
        sources = list(by_token.get(hit.text, []))
        if hit.text in from_question:
            sources.append(("question", None))
        traces.append(
            NumberTrace(
                text=hit.text,
                start=hit.start,
                end=hit.end,
                ok=bool(sources),
                sources=tuple(sources),
            )
        )
    return traces


def invented(traces: list[NumberTrace]) -> list[str]:
    return [t.text for t in traces if not t.ok]
