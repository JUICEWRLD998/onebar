"""Question seeds in hiker register and the time phrases that fill them.

A question is generated from a situation, so the facts it needs are known. The seed text is the reliable label
source; a language model may paraphrase it (see paraphrase.py), but only a paraphrase that keeps every number and
the same intent labels is accepted.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from onebar.check.intents import classify, parse_target
from onebar.facts.engine import resolve_target


@dataclass(frozen=True)
class Seed:
    id: str
    text: str  # may contain {t}: a clock time written the way a hiker writes it, after a word like "by" or "before"

    @property
    def needs_time(self) -> bool:
        return "{t}" in self.text


SEEDS: tuple[Seed, ...] = tuple(
    Seed(f"s{i:02d}", text)
    for i, text in enumerate(
        [
            # storm
            "storm before {t}?",
            "any thunderstorms today?",
            "is there a lightning risk this afternoon?",
            "thunder coming? I'm above treeline",
            "when is the first storm?",
            # rain
            "will it rain before {t}?",
            "rain today?",
            "going to be wet up there?",
            "how likely is rain by {t}?",
            # wind
            "how windy is it going to get?",
            "gusts bad on the ridge?",
            "wind ok at {t}?",
            # daylight
            "when is sunset?",
            "do I need a headlamp?",
            "how much daylight is left?",
            "am I going to be in the dark before I get down?",
            # temperature
            "how cold will it get?",
            "do I need my warm jacket?",
            "what's the temp up here?",
            "how low will the temperature go?",
            # turnaround
            "when do I need to turn around?",
            "what time should I head down to make the car?",
            "can I make it back to the car in time?",
            "turn around time?",
            "should I turn around by {t}?",
            # go / no-go
            "is it safe to keep going?",
            "ok to summit?",
            "should I go up or bail?",
            "can I still do the ridge?",
            "worth it to continue?",
            "good to go until {t}?",
            # general
            "how's the weather?",
            "what's it doing up there?",
            "weather update?",
            # combinations
            "storm or rain before {t}?",
            "windy and cold at the top?",
            "ridge ok by {t} then car?",
            "storm before I'm back at the car?",
            "sunset time and any rain?",
            "wind, rain and temp for the next few hours?",
            "is it safe to stay out until {t}, or is a storm coming?",
            "how cold and when's sunset?",
            "gusts and storms before {t}?",
            "will I get back before dark and before the rain?",
        ]
    )
)


def time_phrases(target: datetime) -> list[str]:
    """Ways a hiker writes a clock time, for a target on the hour or half hour."""
    h24, m = target.hour, target.minute
    h12 = h24 % 12 or 12
    ampm = "am" if h24 < 12 else "pm"
    if m == 0:
        return [f"{h12}", f"{h12}{ampm}", f"{h12} {ampm}", f"{h24:02d}:00", f"{h24}:00"]
    return [f"{h12}:{m:02d}", f"{h12}:{m:02d}{ampm}", f"{h24:02d}:{m:02d}"]


def pick_target(at: datetime, rng: random.Random) -> datetime:
    """A half-hour mark 1.5 to 7 hours ahead on the same day, between 06:00 and 21:30."""
    for _ in range(20):
        raw = at + timedelta(minutes=rng.randrange(90, 421))
        t = raw.replace(minute=0, second=0, microsecond=0)
        if raw.minute >= 45:
            t += timedelta(hours=1)
        elif raw.minute >= 15:
            t = t.replace(minute=30)
        if t.date() == at.date() and 6 <= t.hour <= 21 and t > at:
            return t
    return at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)


def fill(seed: Seed, at: datetime, rng: random.Random) -> str:
    """The seed's question for this moment. A time phrase is kept only if it reads back as the intended time."""
    if not seed.needs_time:
        return seed.text
    target = pick_target(at, rng)
    phrases = time_phrases(target)
    rng.shuffle(phrases)
    for phrase in phrases:
        question = seed.text.format(t=phrase)
        raw = parse_target(question)
        if raw is not None and resolve_target(raw, at) == target:
            return question
    # No phrase round-trips (an hour that resolves to the other half of the day): use 24-hour.
    return seed.text.format(t=f"{target.hour:02d}:{target.minute:02d}")


def draw_seed(rng: random.Random) -> Seed:
    return rng.choice(SEEDS)


def label(question: str) -> list[str]:
    return classify(question)
