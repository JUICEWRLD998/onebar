"""Forecast + local time + optional trip -> FactSet. Every derived fact is computed here, in code.

Times are local naive datetimes: Open-Meteo is called with timezone=auto, so the forecast, the
sunrise/sunset arrays and `at` all share the place's own clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from onebar.check.intents import RawTime, parse_target
from onebar.facts import render
from onebar.facts.model import Fact, FactSet

STORM_CODES = range(95, 100)  # WMO thunderstorm codes 95, 96, 99 (97/98 unused by Open-Meteo)
STORM_CAPE = 1000.0  # J/kg
STORM_POP = 60  # percent, needed together with CAPE
RAIN_MM = 0.2  # mm in the hour
RAIN_POP = 50  # percent


@dataclass(frozen=True)
class Trip:
    return_by: time
    descent_min: int = 90  # assumed minutes from the turn-around point back to the car
    route_name: str | None = None


def resolve_target(raw: RawTime, at: datetime) -> datetime:
    """Pick the next moment at or after `at` that matches a clock time written in a question."""
    if raw.meridiem == "am":
        hours = [raw.hour % 12]
    elif raw.meridiem == "pm":
        hours = [raw.hour % 12 + 12]
    elif 1 <= raw.hour <= 11:
        hours = [raw.hour, raw.hour + 12]
    else:
        hours = [raw.hour]
    candidates = sorted(
        at.replace(hour=h, minute=raw.minute, second=0, microsecond=0) for h in hours
    )
    for c in candidates:
        if c >= at:
            return c
    return candidates[0] + timedelta(days=1)


def _parse_times(values: list[Any] | None) -> list[datetime]:
    return sorted(datetime.fromisoformat(v) for v in (values or []) if v)


def compute_facts(
    forecast: dict,
    at: datetime,
    trip: Trip | None = None,
    question: str = "",
    horizon_h: int = 12,
) -> FactSet:
    hourly = forecast["hourly"]
    iso_times: list[str] = hourly["time"]
    times = [datetime.fromisoformat(t) for t in iso_times]
    floor = at.replace(minute=0, second=0, microsecond=0)
    try:
        start = times.index(floor)
    except ValueError:
        raise ValueError(f"forecast does not cover {at.isoformat()}") from None
    end = min(start + horizon_h, len(times))
    window = range(start, end)

    def series(name: str) -> list | None:
        return hourly.get(name)

    def value(name: str, i: int):
        s = series(name)
        return None if s is None else s[i]

    def hour_fact(key: str, token: str, i: int, raw: Any) -> Fact:
        return Fact(key, token, raw, iso_times[i])

    facts: list[Fact] = [Fact("now", render.clock(at), at)]

    temp_now = value("temperature_2m", start)
    if temp_now is not None:
        facts.append(hour_fact("temp_now", render.temp(temp_now), start, temp_now))

    def extreme(name: str, pick_max: bool) -> tuple[int, float] | None:
        best: tuple[int, float] | None = None
        for i in window:
            v = value(name, i)
            if v is None:
                continue
            if best is None or (v > best[1] if pick_max else v < best[1]):
                best = (i, v)
        return best

    coldest = extreme("apparent_temperature", pick_max=False)
    if coldest:
        facts.append(hour_fact("feels_min", render.temp(coldest[1]), coldest[0], coldest[1]))

    gust = extreme("wind_gusts_10m", pick_max=True)
    if gust:
        i, v = gust
        facts.append(hour_fact("gust_max", render.speed(v), i, v))
        facts.append(hour_fact("gust_max_at", render.clock(times[i]), i, times[i]))

    pop = extreme("precipitation_probability", pick_max=True)
    if pop:
        facts.append(hour_fact("pop_max", render.percent(pop[1]), pop[0], pop[1]))

    # Storm: weather code 95-99, or high CAPE together with a high precipitation probability.
    have_storm_data = series("weather_code") is not None or (
        series("cape") is not None and series("precipitation_probability") is not None
    )
    if have_storm_data:
        first = None
        for i in window:
            code, cape, p = value("weather_code", i), value("cape", i), value("precipitation_probability", i)
            by_code = code is not None and code in STORM_CODES
            by_cape = cape is not None and p is not None and cape >= STORM_CAPE and p >= STORM_POP
            if by_code or by_cape:
                first = i
                break
        if first is None:
            facts.append(Fact("storm_none", "no storm"))
        else:
            facts.append(hour_fact("storm_first", render.clock(times[first]), first, times[first]))

    if series("precipitation") is not None and series("precipitation_probability") is not None:
        first = None
        for i in window:
            mm, p = value("precipitation", i), value("precipitation_probability", i)
            if mm is not None and p is not None and mm >= RAIN_MM and p >= RAIN_POP:
                first = i
                break
        if first is None:
            facts.append(Fact("rain_none", "no rain"))
        else:
            facts.append(hour_fact("rain_first", render.clock(times[first]), first, times[first]))

    facts.extend(_sun_facts(forecast.get("daily") or {}, at))

    elevation = forecast.get("elevation")
    if elevation is not None:
        facts.append(Fact("elevation", render.metres(elevation), elevation))

    if trip is not None:
        car = datetime.combine(at.date(), trip.return_by)
        if car < at:
            car += timedelta(days=1)
        facts.append(Fact("car_by", render.clock(car), car))
        turn = car - timedelta(minutes=trip.descent_min)
        if turn >= at:
            facts.append(Fact("turn_by", render.clock(turn), turn))
        else:
            facts.append(Fact("turn_now", "turn now", turn))

    raw = parse_target(question)
    if raw is not None:
        target = resolve_target(raw, at)
        facts.append(Fact("target", render.clock(target), target))

    return FactSet(facts)


def _sun_facts(daily: dict, at: datetime) -> list[Fact]:
    sunrises = _parse_times(daily.get("sunrise"))
    sunsets = _parse_times(daily.get("sunset"))
    today_rise = next((t for t in sunrises if t.date() == at.date()), None)
    today_set = next((t for t in sunsets if t.date() == at.date()), None)
    dark = None
    if today_rise and today_set:
        dark = at < today_rise or at >= today_set
    next_set = next((t for t in sunsets if t > at), None)
    next_rise = next((t for t in sunrises if t > at), None)

    out: list[Fact] = []
    if next_set:
        out.append(Fact("sunset", render.clock(next_set), next_set, next_set.strftime("%Y-%m-%dT%H:%M")))
    if next_rise:
        out.append(Fact("sunrise", render.clock(next_rise), next_rise, next_rise.strftime("%Y-%m-%dT%H:%M")))
    if dark is True:
        out.append(Fact("dark_now", "dark", True))
    elif dark is False and next_set:
        left = (next_set - at).total_seconds() / 60
        out.append(Fact("daylight_left", render.duration(left), left))
    return out
