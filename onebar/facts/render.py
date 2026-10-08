"""Canonical renderers. Every fact becomes one string here, and the checker matches only these."""
from __future__ import annotations

import math
from datetime import datetime


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def clock(dt: datetime) -> str:
    """24-hour clock, zero padded: 14:40."""
    return f"{dt.hour:02d}:{dt.minute:02d}"


def percent(x: float) -> str:
    return f"{round_half_up(x)}%"


def speed(kmh: float) -> str:
    return f"{round_half_up(kmh)}km/h"


def temp(c: float) -> str:
    n = round_half_up(c)
    return f"{n}C"


def metres(m: float) -> str:
    return f"{round_half_up(m)}m"


def duration(minutes: float) -> str:
    """Whole minutes as 45m, 2h or 2h10m."""
    total = round_half_up(minutes)
    if total < 0:
        raise ValueError("negative duration")
    h, m = divmod(total, 60)
    if h == 0:
        return f"{m}m"
    if m == 0:
        return f"{h}h"
    return f"{h}h{m}m"
