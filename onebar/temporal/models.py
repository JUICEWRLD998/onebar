"""Payloads that cross the Temporal boundary. Plain dataclasses of JSON types; datetimes travel as ISO strings.

No `from __future__ import annotations` here: Temporal's converter reads the real field types to rebuild them.
"""
from dataclasses import dataclass, field
from typing import List, Optional

TASK_QUEUE = "onebar"


@dataclass
class Inbound:
    id: str  # idempotency key: the channel's message id (email Message-ID, web message uuid)
    text: str
    channel: str
    ts: str  # ISO 8601 UTC, when the channel received it


@dataclass
class TripState:
    place: str
    lat: float
    lon: float
    contact: str
    back_local: str  # HH:MM on the place's clock
    offset_s: int  # the place's UTC offset when the trip was registered
    deadline_iso: str  # return time, UTC
    alert_iso: str  # deadline plus grace, UTC
    trip_id: str
    alerted: bool = False


@dataclass
class WorkflowState:
    sender: str
    trip: Optional[TripState] = None
    seen: List[str] = field(default_factory=list)  # message ids already accepted, newest last
    last_pos: Optional[List[float]] = None  # [lat, lon] of the last trip or PLACE
    last_offset_s: int = 0  # that place's UTC offset, so a question without a trip still gets the right local time
    last_msg_iso: Optional[str] = None
    processed: int = 0  # messages handled since the last continue-as-new
    can_after: int = 100  # continue-as-new after this many messages, to keep history small
    idle_s: int = 7 * 24 * 3600  # a quiet workflow with no active trip ends after this long
    allow_phone: bool = False  # phone contacts need an SMS channel, which this deployment does not have


@dataclass
class ResolveReq:
    place: str
    coords: Optional[List[float]]
    back: str  # HH:MM
    now_iso: str


@dataclass
class ResolveResult:
    ok: bool
    error: str = ""
    place: str = ""
    lat: float = 0.0
    lon: float = 0.0
    offset_s: int = 0
    deadline_iso: str = ""
    alert_iso: str = ""
    back_local: str = ""
    alert_local: str = ""


@dataclass
class PlaceReq:
    place: str
    coords: Optional[List[float]]


@dataclass
class PlaceResult:
    ok: bool
    error: str = ""
    place: str = ""
    lat: float = 0.0
    lon: float = 0.0
    offset_s: int = 0


@dataclass
class AnswerReq:
    question: str
    lat: float
    lon: float
    now_iso: str
    offset_s: int
    return_local: Optional[str] = None
    msg_id: str = ""  # the inbound message id; the trace of the answer is stored under it


@dataclass
class AnswerResult:
    text: str
    path: str  # model | model-retry | template
    septets: int


@dataclass
class SendReq:
    key: str
    to: str
    text: str
