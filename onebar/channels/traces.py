"""Trace of how one reply was produced: which fact each number came from, what the checker said, which path answered.

Stored by message id, shown on the trace page. It never holds the sender's address: the trace page is public to
anyone who knows the id.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def hours_slice(forecast: dict, at: datetime, n: int = 12) -> list[dict]:
    """The next n forecast hours from `at` (a naive local datetime), for the trace page's hourly strip."""
    from onebar.facts.engine import RAIN_MM, RAIN_POP, STORM_CAPE, STORM_CODES, STORM_POP

    h = forecast["hourly"]
    times = h["time"]
    floor = at.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    if floor not in times:
        return []
    start = times.index(floor)

    def val(name, i):
        s = h.get(name)
        return None if s is None else s[i]

    out = []
    for i in range(start, min(start + n, len(times))):
        code, cape, pop, mm = val("weather_code", i), val("cape", i), val("precipitation_probability", i), val("precipitation", i)
        storm = (code is not None and code in STORM_CODES) or (
            cape is not None and pop is not None and cape >= STORM_CAPE and pop >= STORM_POP)
        rain = mm is not None and pop is not None and mm >= RAIN_MM and pop >= RAIN_POP
        out.append({"t": times[i], "temp": val("temperature_2m", i), "gust": val("wind_gusts_10m", i),
                    "pop": pop, "storm": bool(storm), "rain": bool(rain)})
    return out


def make_baseline(text: str, facts, question: str) -> dict:
    """How a draft (the base model's, shown for comparison and never sent) fares against the same checker."""
    from onebar.check.checker import check

    res = check(text, facts, question)
    return {
        "text": text, "passed": res.passed, "reasons": list(res.reasons), "septets": res.septets,
        "numbers": [{"text": n.text, "ok": n.ok, "sources": [[k, h] for k, h in n.sources]} for n in res.numbers],
    }


def make_trace(question: str, reply, hours: list[dict] | None = None, baseline: dict | None = None,
               place: tuple[float, float] | None = None) -> dict:
    """`reply` is a pipeline.Reply. `place` is the (lat, lon) the forecast was read at, for the trace page's map."""
    r = reply.result
    return {
        "hours": hours or [],
        "baseline": baseline,
        "place": None if place is None else {"lat": place[0], "lon": place[1]},
        "question": question,
        "reply": reply.text,
        "path": reply.path,
        "septets": r.septets,
        "intents": list(r.intents),
        "numbers": [
            {"text": n.text, "ok": n.ok, "sources": [[k, h] for k, h in n.sources]} for n in r.numbers
        ],
        "attempts": [
            {
                "source": a.source,
                "text": a.text,
                "passed": bool(a.result and a.result.passed),
                "reasons": list(a.result.reasons) if a.result else [],
                "error": a.error,
            }
            for a in reply.attempts
        ],
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class TraceStore:
    def __init__(self, directory: Path):
        self.dir = directory

    def _path(self, message_id: str) -> Path:
        return self.dir / (hashlib.sha256(message_id.encode()).hexdigest()[:32] + ".json")

    def trace_id(self, message_id: str) -> str:
        return self._path(message_id).stem

    def save(self, message_id: str, trace: dict) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(message_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # atomic: a reader never sees half a trace
        return path.stem

    def load(self, trace_id: str) -> dict | None:
        if not trace_id.isalnum() or len(trace_id) != 32:
            return None  # not one of ours: never build a path from user input
        path = self.dir / f"{trace_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
