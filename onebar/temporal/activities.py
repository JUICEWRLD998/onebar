"""Activities: every call that touches the outside world. Dependencies are injected so tests run offline.

Retry policy lives in the workflow. Here, errors worth retrying (network, forecast service) are raised as they are;
errors that retrying cannot fix are raised as non-retryable ApplicationError.
"""
from __future__ import annotations

import os
import threading
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Callable

from temporalio import activity
from temporalio.exceptions import ApplicationError

from onebar import pipeline, trips
from onebar.channels.traces import hours_slice, make_baseline, make_trace
from onebar.model.prompt import render as render_prompt
from onebar.facts.engine import Trip
from onebar.facts.locate import Place, geocode
from onebar.facts.open_meteo import ForecastError, fetch_forecast
from onebar.model.client import Draft
from onebar.temporal.models import (
    AnswerReq, AnswerResult, PlaceReq, PlaceResult, ResolveReq, ResolveResult, SendReq,
)

DEFAULT_GRACE_MIN = 30


@dataclass
class Deps:
    sender: object  # anything with send(key, to, text) -> bool
    draft: Draft | None = None  # None means the template answers
    get_forecast: Callable[[str], dict] | None = None  # None uses the real Open-Meteo getter
    get_geocode: Callable[[str], dict] | None = None
    traces: object | None = None  # a TraceStore: where the trace of each answer is saved
    baseline_draft: Draft | None = None  # the base model, only to show how it fares on the same question
    grace_min: int = field(default_factory=lambda: int(os.environ.get("ONEBAR_GRACE_MIN", DEFAULT_GRACE_MIN)))
    cache_ttl_s: float = 600.0  # 0 turns the forecast cache off
    _cache: dict = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


def _forecast(deps: Deps, lat: float, lon: float) -> dict:
    """The forecast for a place, reused for deps.cache_ttl_s seconds so follow-up questions skip the network call."""
    key = (round(lat, 2), round(lon, 2))
    now = _time.monotonic()  # `time` in this module is datetime.time
    with deps._lock:
        hit = deps._cache.get(key)
        if hit and now - hit[0] < deps.cache_ttl_s:
            return hit[1]
    kw = {"get": deps.get_forecast} if deps.get_forecast else {}
    try:
        data = fetch_forecast(lat, lon, **kw)
    except ForecastError:
        raise  # transient as far as we can tell: let the retry policy decide
    except ValueError as exc:
        raise ApplicationError(str(exc), non_retryable=True) from exc
    with deps._lock:
        deps._cache[key] = (now, data)
    return data


class Activities:
    def __init__(self, deps: Deps):
        self.deps = deps

    @activity.defn
    def resolve_trip(self, req: ResolveReq) -> ResolveResult:
        now = datetime.fromisoformat(req.now_iso)
        if req.coords:
            place = Place(f"{req.coords[0]:.3f},{req.coords[1]:.3f}", req.coords[0], req.coords[1])
        else:
            kw = {"get": self.deps.get_geocode} if self.deps.get_geocode else {}
            found = geocode(req.place, **kw)
            if found is None:
                return ResolveResult(ok=False, error="Could not find that place. Use lat,lon, like 46.55,7.98.")
            place = found
        offset = int(_forecast(self.deps, place.lat, place.lon)["utc_offset_seconds"])
        back = time.fromisoformat(req.back)
        deadline = trips.deadline_utc(now, offset, back)
        alert = deadline + timedelta(minutes=self.deps.grace_min)
        return ResolveResult(
            ok=True, place=place.name, lat=place.lat, lon=place.lon, offset_s=offset,
            deadline_iso=deadline.isoformat(), alert_iso=alert.isoformat(),
            back_local=trips.local_clock(deadline, offset), alert_local=trips.local_clock(alert, offset),
        )

    @activity.defn
    def resolve_place(self, req: PlaceReq) -> PlaceResult:
        """PLACE <name or lat,lon>: coordinates and the place's UTC offset, with no trip and no deadline."""
        if req.coords:
            place = Place(f"{req.coords[0]:.3f},{req.coords[1]:.3f}", req.coords[0], req.coords[1])
        else:
            kw = {"get": self.deps.get_geocode} if self.deps.get_geocode else {}
            found = geocode(req.place, **kw)
            if found is None:
                return PlaceResult(ok=False, error="Could not find that place. Use PLACE lat,lon, like 46.55,7.98.")
            place = found
        offset = int(_forecast(self.deps, place.lat, place.lon)["utc_offset_seconds"])
        return PlaceResult(ok=True, place=place.name, lat=place.lat, lon=place.lon, offset_s=offset)

    @activity.defn
    def answer_question(self, req: AnswerReq) -> AnswerResult:
        """Facts and draft in one activity, so the 70 KB forecast never enters the workflow history."""
        forecast = _forecast(self.deps, req.lat, req.lon)
        now = datetime.fromisoformat(req.now_iso).astimezone(timezone.utc)
        at = (now + timedelta(seconds=req.offset_s)).replace(tzinfo=None, second=0, microsecond=0)
        trip = Trip(return_by=time.fromisoformat(req.return_local)) if req.return_local else None
        try:
            reply = pipeline.answer(req.question, at, forecast, self.deps.draft, trip=trip)
        except ValueError as exc:  # the forecast does not cover this moment; retrying will not change that
            raise ApplicationError(str(exc), non_retryable=True) from exc
        if self.deps.traces is not None and req.msg_id:
            baseline = None
            if self.deps.baseline_draft is not None:  # the base model's draft, shown beside ours and never sent
                try:
                    text = self.deps.baseline_draft(render_prompt(reply.facts, req.question))
                    baseline = make_baseline(text, reply.facts, req.question)
                except Exception:
                    baseline = None  # a missing comparison must never cost the hiker their reply
            self.deps.traces.save(
                req.msg_id,
                make_trace(req.question, reply, hours_slice(forecast, at), baseline, place=(req.lat, req.lon)),
            )
        return AnswerResult(text=reply.text, path=reply.path, septets=reply.result.septets)

    @activity.defn
    def send(self, req: SendReq) -> bool:
        """Idempotent on req.key: a redelivered or retried call returns False and sends nothing."""
        return bool(self.deps.sender.send(req.key, req.to, req.text))

    def all(self) -> list:
        return [self.resolve_trip, self.resolve_place, self.answer_question, self.send]
