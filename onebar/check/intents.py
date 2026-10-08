"""Question -> intent labels (keyword rules) -> groups of fact keys a good reply must cover.

A group is satisfied when the reply contains the token of at least one fact of that group that
exists in the FactSet. A group with no existing fact cannot be demanded, so it is skipped by the
checker (the data is missing, not the reply).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_I = re.IGNORECASE

# Order here is the order intents are reported in.
_RULES: dict[str, re.Pattern[str]] = {
    "storm": re.compile(r"\b(?:storm(?:s|y)?|thunder\w*|lightning|t-?storms?)\b", _I),
    "rain": re.compile(
        r"\b(?:rain\w*|shower\w*|drizzl\w*|snow\w*|wet|precip\w*|downpour\w*|sleet|hail)\b", _I
    ),
    "wind": re.compile(r"\b(?:wind\w*|gust\w*|breez\w*)\b", _I),
    "daylight": re.compile(r"\b(?:sunset|sunrise|dark|daylight|dusk|dawn|headlamp)\b", _I),
    "temperature": re.compile(
        r"\b(?:cold\w*|temp|temps|temperature|freez\w*|warm\w*|hot|chill\w*|degrees|jacket|feels?)\b",
        _I,
    ),
    "turnaround": re.compile(
        r"\b(?:turn(?:ing|around)?|back by|return\w*|descen\w+|car|head(?:ing)? down|get down)\b",
        _I,
    ),
    "go_nogo": re.compile(
        r"\b(?:ok|okay|safe\w*|go|should i|can i|good to|fine|worth it|risky)\b", _I
    ),
}

_STORM = ("storm_first", "storm_none")

REQUIRED: dict[str, list[tuple[str, ...]]] = {
    "storm": [_STORM],
    "rain": [("rain_first", "rain_none", "pop_max")],
    "wind": [("gust_max",)],
    "daylight": [("sunset", "dark_now")],
    "temperature": [("feels_min", "temp_now")],
    "turnaround": [("turn_by", "car_by", "target", "turn_now", "sunset"), _STORM],
    "go_nogo": [_STORM, ("gust_max",)],
    "general": [_STORM],
}


def classify(question: str) -> list[str]:
    found = [name for name, rx in _RULES.items() if rx.search(question)]
    return found or ["general"]


def required_groups(intents: list[str]) -> list[tuple[str, ...]]:
    groups: list[tuple[str, ...]] = []
    for intent in intents:
        for group in REQUIRED[intent]:
            if group not in groups:
                groups.append(group)
    return groups


@dataclass(frozen=True)
class RawTime:
    hour: int
    minute: int
    meridiem: str | None  # "am", "pm" or None


_TARGET = re.compile(
    r"\b(?:by|before|until|till|at|back)\s+(?:(?:by|at)\s+)?"
    r"(\d{1,2})(?::(\d{2}))?(?![\d:%])\s*(am|pm|a\.m\.|p\.m\.)?",
    _I,
)


def parse_target(question: str) -> RawTime | None:
    """First valid clock time the question names ("by 3", "back at 15:30", "5pm"), unresolved."""
    for m in _TARGET.finditer(question):
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        meridiem = m.group(3).lower().replace(".", "") if m.group(3) else None
        if minute > 59:
            continue
        if meridiem:
            if not 1 <= hour <= 12:
                continue
        elif hour > 23:
            continue
        return RawTime(hour, minute, meridiem)
    return None
