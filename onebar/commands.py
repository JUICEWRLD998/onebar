"""Plain-text commands from the hiker. Pure parsing, case-insensitive, no I/O.

  TRIP <place or lat,lon> BACK <HH:MM> CONTACT <email or phone>   register a trip
  OUT                                                              checked in safe, cancels the alert
  FORGET                                                           delete everything stored about the sender
  HELP                                                             list the commands
  PLACE <place or lat,lon>                                         set where you are, no trip needed
  anything else                                                    a weather question
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time

MAX_LEN = 500  # longer inbound text is refused, not parsed

HELP_TEXT = "OneBar: TRIP <place> BACK 17:00 CONTACT <email>. OUT when safe. FORGET deletes your data. Or ask a weather question."
USAGE_TRIP = "Use: TRIP <place or lat,lon> BACK 17:00 CONTACT <email or phone>"


@dataclass(frozen=True)
class TripCmd:
    place: str
    coords: tuple[float, float] | None  # set when the place was written as lat,lon
    back: time
    contact: str


@dataclass(frozen=True)
class OutCmd:
    pass


@dataclass(frozen=True)
class ForgetCmd:
    pass


@dataclass(frozen=True)
class HelpCmd:
    pass


@dataclass(frozen=True)
class PlaceCmd:
    """PLACE <name or lat,lon>: where the hiker is, with no trip and no contact."""
    place: str
    coords: tuple[float, float] | None


@dataclass(frozen=True)
class QuestionCmd:
    text: str


@dataclass(frozen=True)
class BadCmd:
    reason: str  # short, safe to send back to the hiker


Command = TripCmd | OutCmd | ForgetCmd | HelpCmd | PlaceCmd | QuestionCmd | BadCmd

_I = re.IGNORECASE
_TRIP = re.compile(r"trip\s+(?P<place>.+?)\s+back\s+(?P<back>\S+)\s+contact\s+(?P<contact>.+)", _I | re.DOTALL)
_PLACE = re.compile(r"place\s+(?P<place>.{1,80})", _I)
_COORDS = re.compile(r"(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE = re.compile(r"\+?\d[\d \-]{6,18}\d")
_WORD = {"out": OutCmd, "forget": ForgetCmd, "help": HelpCmd}


def parse_clock(text: str) -> time | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return time(h, mi) if h <= 23 and mi <= 59 else None


def parse(text: str, allow_phone: bool = True) -> Command:
    """`allow_phone=False` refuses phone numbers as the contact, for deployments with no SMS channel."""
    text = (text or "").strip()
    if not text:
        return BadCmd("Empty message. Text HELP for the commands.")
    if len(text) > MAX_LEN:
        return BadCmd("Message too long. Keep it under 500 characters.")
    word = re.fullmatch(r"([A-Za-z]+)[\s.!]*", text)
    if word and word.group(1).lower() in _WORD:
        return _WORD[word.group(1).lower()]()
    if re.match(r"trip\b", text, _I):
        return _parse_trip(text, allow_phone)
    place = _PLACE.fullmatch(text)
    if place and "?" not in text:  # "place ..." with a question mark is a question
        return _parse_place(place.group("place").strip())
    return QuestionCmd(text)


def _parse_place(place: str) -> Command:
    c = _COORDS.fullmatch(place)
    if not c:
        return PlaceCmd(place=place, coords=None)
    lat, lon = float(c.group(1)), float(c.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return BadCmd("Coordinates are out of range. Use: PLACE <place or lat,lon>")
    return PlaceCmd(place=place, coords=(lat, lon))


def _parse_trip(text: str, allow_phone: bool = True) -> Command:
    m = _TRIP.fullmatch(text)
    if not m:
        return BadCmd(USAGE_TRIP)
    back = parse_clock(m.group("back"))
    if back is None:
        return BadCmd("Time must be 24-hour HH:MM, like 17:00. " + USAGE_TRIP)
    contact = m.group("contact").strip()
    if not allow_phone:
        if not _EMAIL.fullmatch(contact):
            return BadCmd("CONTACT must be an email address. " + USAGE_TRIP.replace(" or phone", ""))
    elif not (_EMAIL.fullmatch(contact) or _PHONE.fullmatch(contact)):
        return BadCmd("CONTACT must be an email or a phone number. " + USAGE_TRIP)
    place = m.group("place").strip()
    coords = None
    c = _COORDS.fullmatch(place)
    if c:
        lat, lon = float(c.group(1)), float(c.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return BadCmd("Coordinates are out of range. " + USAGE_TRIP)
        coords = (lat, lon)
    return TripCmd(place=place, coords=coords, back=back, contact=contact)
