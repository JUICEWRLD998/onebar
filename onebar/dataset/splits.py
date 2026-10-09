"""Train / validation / test assignment by geographic cell, never by row.

Every location in the same 0.5 degree cell lands in the same split, so two summits a few
kilometres apart (same weather on the same day) cannot straddle train and test.
The split is a hash of the cell, so it is stable across runs and independent of sampling order.
"""
from __future__ import annotations

import hashlib
import math
from typing import Iterable, TypeVar

CELL_DEG = 0.5
SALT = "onebar-v1"
SPLITS = ("train", "val", "test")


def cell(lat: float, lon: float) -> tuple[int, int]:
    return (math.floor(lat / CELL_DEG), math.floor(lon / CELL_DEG))


def split_of(lat: float, lon: float) -> str:
    i, j = cell(lat, lon)
    h = int.from_bytes(hashlib.sha256(f"{SALT}:{i}:{j}".encode()).digest()[:8], "big") % 100
    return "train" if h < 80 else "val" if h < 90 else "test"


T = TypeVar("T")


def assign(locations: Iterable[T]) -> dict[str, list[T]]:
    out: dict[str, list[T]] = {s: [] for s in SPLITS}
    for loc in locations:
        out[split_of(loc.lat, loc.lon)].append(loc)  # type: ignore[attr-defined]
    return out
