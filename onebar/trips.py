"""Trip arithmetic and the overdue-alert text. Pure functions: no clock, no I/O."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

NEED_PLACE = "No place yet. Text TRIP <place> BACK 17:00 CONTACT <email> first, then ask."
FORECAST_DOWN = "Forecast unavailable right now. Try again in a few minutes."


def deadline_utc(now_utc: datetime, offset_s: int, back: time) -> datetime:
    """The next moment the place's own clock reads `back`, as an aware UTC datetime.

    A `back` time already reached today (or equal to now) means tomorrow.
    """
    now_utc = now_utc.astimezone(timezone.utc)
    local_now = (now_utc + timedelta(seconds=offset_s)).replace(tzinfo=None)
    local = datetime.combine(local_now.date(), back)
    if local <= local_now:
        local += timedelta(days=1)
    return (local - timedelta(seconds=offset_s)).replace(tzinfo=timezone.utc)


def local_clock(utc: datetime, offset_s: int) -> str:
    return (utc.astimezone(timezone.utc) + timedelta(seconds=offset_s)).strftime("%H:%M")


def trip_saved_text(back_local: str, alert_local: str) -> str:
    return f"Trip saved. Text OUT when you are safe. If I hear nothing by {alert_local} your contact is told. Back {back_local}."


def alert_text(sender: str, place: str, lat: float, lon: float, back_local: str, last_msg_local: str | None) -> str:
    last = f"Last message from them at {last_msg_local} local time." if last_msg_local else "No message from them since the trip began."
    coords = f"{lat:.3f}, {lon:.3f}"
    area = coords if place.replace(",", "").replace(".", "").replace("-", "").isdigit() else f"{place} ({coords})"
    return (
        f"OneBar: {sender} planned to be back at {back_local} and has not checked out. "
        f"Trip area: {area}. {last} "
        "OneBar is not a rescue service. If you are worried, call the local emergency number."
    )
