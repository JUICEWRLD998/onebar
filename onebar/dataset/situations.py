"""Situations: a place, a local moment and an optional trip, cut from a past forecast, then turned into dataset rows.

A row holds the question and the serialized facts, so training, eval and the checker never need the raw forecast.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta

from onebar.check.intents import classify
from onebar.dataset import questions as Q
from onebar.dataset.locations import Location
from onebar.dataset.serde import facts_to_json
from onebar.dataset.splits import split_of
from onebar.facts.engine import Trip, compute_facts

ASK_HOURS = range(5, 18)  # hikers ask between 05:00 and 17:59 local
TRIP_P = 0.5
STORM_BIAS = 0.5  # chance a situation is steered to an hour with a storm ahead, when the window has one


@dataclass(frozen=True)
class Situation:
    loc: Location
    at: datetime
    trip: Trip | None


def _days(forecast: dict) -> list[date]:
    """Days usable as an ask day: every day except the last, so the 12 hour look-ahead is always covered."""
    days = sorted({datetime.fromisoformat(t).date() for t in forecast["hourly"]["time"]})
    return days[:-1]


def sample_situations(
    loc: Location,
    forecast: dict,
    rng: random.Random,
    k: int = 3,
    storm_bias: float = STORM_BIAS,
    trip_p: float = TRIP_P,
) -> list[Situation]:
    pool_days = _days(forecast)
    out: list[Situation] = []
    for _ in range(min(k, len(pool_days))):
        rng.shuffle(pool_days)
        steered = rng.random() < storm_bias
        chosen: datetime | None = None
        if steered:  # look across the remaining days for an ask time with a storm ahead
            for day in pool_days:
                hours = list(ASK_HOURS)
                rng.shuffle(hours)
                for hour in hours:
                    at = datetime.combine(day, time(hour, rng.randrange(60)))
                    if "storm_first" in compute_facts(forecast, at):
                        chosen = at
                        break
                if chosen:
                    break
        if chosen is None:  # not steered, or no storm anywhere in the window: any hour of the next day in line
            chosen = datetime.combine(pool_days[0], time(rng.choice(list(ASK_HOURS)), rng.randrange(60)))
        pool_days.remove(chosen.date())
        trip = None
        if rng.random() < trip_p:
            # 2 to 9 hours out, as a round clock time: a hiker says "back by 17:15", never "17:54"
            back = chosen + timedelta(minutes=rng.randrange(128, 533))
            minutes = 15 * round((back.hour * 60 + back.minute) / 15)
            if back.date() == chosen.date() and minutes < 24 * 60:
                trip = Trip(return_by=time(minutes // 60, minutes % 60))
        out.append(Situation(loc, chosen, trip))
    return out


def row_id(sit: Situation) -> str:
    return f"{sit.loc.id}|{sit.at:%Y-%m-%dT%H:%M}"


def build_row(sit: Situation, forecast: dict, seed: Q.Seed, rng: random.Random) -> dict:
    question = Q.fill(seed, sit.at, rng)
    facts = compute_facts(forecast, sit.at, trip=sit.trip, question=question)
    return {
        "id": row_id(sit),
        "split": split_of(sit.loc.lat, sit.loc.lon),
        "loc": asdict(sit.loc),
        "at": sit.at.isoformat(timespec="minutes"),
        "trip": None
        if sit.trip is None
        else {"return_by": sit.trip.return_by.strftime("%H:%M"), "descent_min": sit.trip.descent_min},
        "seed": seed.id,
        "seed_question": question,
        "question": question,
        "paraphrased": False,
        "intents": classify(question),
        "facts": facts_to_json(facts),
    }
