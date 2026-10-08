"""Deterministic reply built from facts alone: the answer that goes out when the model cannot be trusted.

Each intent contributes a segment with a long and a short wording. build() tries the longest text,
shortens from the end, drops optional extras, then drops trailing segments, and returns the first
candidate the checker accepts. Only fact tokens appear as numbers.
"""
from __future__ import annotations

from dataclasses import dataclass

from onebar.check.checker import check
from onebar.check.intents import classify
from onebar.facts.model import Fact, FactSet

FALLBACK = "Limited data. Use caution."
GUST_CAUTION_KMH = 60  # at or above this a go/no-go answer is "Caution"


@dataclass(frozen=True)
class Seg:
    name: str
    variants: tuple[str, ...]  # longest first, shortest last
    optional: bool = False


def _ref(f: FactSet) -> Fact | None:
    """The time the hiker cares about: the one in the question, else the trip's car time."""
    return f.get("target") or f.get("car_by")


def _storm(f: FactSet) -> tuple[str, ...] | None:
    sf = f.get("storm_first")
    if sf is not None:
        ref = _ref(f)
        short = f"Storm from {sf.token}."
        if ref is None:
            return (short,)
        word = "before" if sf.value <= ref.value else "after"
        return (f"Storm from {sf.token}, {word} {ref.token}.", short)
    if "storm_none" in f:
        return ("No storm expected.", "No storm.")
    return None


def _rain(f: FactSet) -> tuple[str, ...] | None:
    pop = f.get("pop_max")
    rf = f.get("rain_first")
    if rf is not None:
        short = f"Rain from {rf.token}."
        if pop is None:
            return (short,)
        return (f"Rain from {rf.token}, chance up to {pop.token}.", short)
    if "rain_none" in f:
        return ("No rain expected.", "No rain.")
    if pop is not None:
        return (f"Rain chance up to {pop.token}.",)
    return None


def _wind(f: FactSet) -> tuple[str, ...] | None:
    g, at = f.get("gust_max"), f.get("gust_max_at")
    if g is None:
        return None
    short = f"Gusts to {g.token}."
    if at is None:
        return (short,)
    return (f"Gusts to {g.token} around {at.token}.", short)


def _daylight(f: FactSet) -> tuple[str, ...] | None:
    if "dark_now" in f:
        sr = f.get("sunrise")
        if sr is not None:
            return (f"Dark now, sunrise {sr.token}.", "Dark now.")
        return ("Dark now.",)
    ss = f.get("sunset")
    if ss is None:
        return None
    left = f.get("daylight_left")
    short = f"Sunset {ss.token}."
    if left is None:
        return (short,)
    return (f"Sunset {ss.token}, {left.token} of light left.", short)


def _temperature(f: FactSet) -> tuple[str, ...] | None:
    now, low = f.get("temp_now"), f.get("feels_min")
    if now and low:
        return (f"{now.token} now, feels down to {low.token}.", f"{now.token} now.")
    if now:
        return (f"{now.token} now.",)
    if low:
        return (f"Feels down to {low.token}.",)
    return None


def _turnaround(f: FactSet) -> tuple[str, ...] | None:
    tb, cb = f.get("turn_by"), f.get("car_by")
    if tb is not None:
        return (f"Turn by {tb.token} to reach car by {cb.token}.", f"Turn by {tb.token}.")
    if "turn_now" in f:
        return (f"Turn now, car by {cb.token}.", "Turn now.")
    if cb is not None:
        return (f"Car by {cb.token}.",)
    tg = f.get("target")
    if tg is not None:
        return (f"Plan around {tg.token}.",)
    ss = f.get("sunset")
    if ss is not None:
        return (f"Sunset {ss.token}.",)
    return None


def _verdict(f: FactSet) -> tuple[str, ...] | None:
    g = f.get("gust_max")
    gust = f" Gusts {g.token}." if g is not None else ""
    sf = f.get("storm_first")
    if sf is None and "storm_none" not in f:
        return (f"Gusts {g.token}.",) if g is not None else None  # no storm data: no verdict
    ref = _ref(f)
    if sf is not None and ref is not None and sf.value <= ref.value:
        word = "No-go."
    elif sf is not None or (g is not None and g.value >= GUST_CAUTION_KMH):
        word = "Caution."
    else:
        word = "Looks OK."
    return (word + gust,)


def _segments(f: FactSet, intents: list[str]) -> list[Seg]:
    segs: list[Seg] = []

    def add(name: str, variants: tuple[str, ...] | None, optional: bool = False) -> None:
        if variants:
            segs.append(Seg(name, variants, optional))

    verdict = None
    if "go_nogo" in intents:
        verdict = _verdict(f)
        add("verdict", verdict)
    if set(intents) & {"storm", "turnaround", "go_nogo", "general"}:
        add("storm", _storm(f))
    if "rain" in intents:
        add("rain", _rain(f))
    if "wind" in intents and verdict is None:
        add("wind", _wind(f))
    if "daylight" in intents:
        add("daylight", _daylight(f))
    if "temperature" in intents:
        add("temperature", _temperature(f))
    if "turnaround" in intents:
        add("turnaround", _turnaround(f))
    if intents == ["general"]:
        add("wind", _wind(f), optional=True)
        add("daylight", _daylight(f), optional=True)
    return segs


def _candidates(segs: list[Seg]):
    required = [s for s in segs if not s.optional]
    for keep in (segs, required):
        if not keep:
            continue
        n = len(keep)
        for shortened in range(n + 1):  # shorten from the end first
            yield " ".join(
                s.variants[-1] if i >= n - shortened else s.variants[0]
                for i, s in enumerate(keep)
            )
    for cut in range(1, len(required)):  # last resort: drop trailing segments
        yield " ".join(s.variants[-1] for s in required[:-cut])


def build(facts: FactSet, question: str) -> str:
    intents = classify(question)
    for text in _candidates(_segments(facts, intents)):
        if check(text, facts, question).passed:
            return text
    return FALLBACK
