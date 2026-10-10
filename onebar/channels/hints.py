"""What a visitor's browser looked up for its own session: the place it geocoded and the forecast it fetched.

Open-Meteo counts its free quota per IP, and a shared cloud host's outbound IP is often over that quota before this
service makes a single call. The visitor's own browser is not, so the web page fetches the same Open-Meteo URLs the
server would and sends them along with the message. The API checks the shape, keeps only the fields the facts engine
reads, and files it under that session's workflow id. The worker uses it for that session only and never puts it in
the shared forecast cache, so a visitor can only ever affect the facts in their own replies.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Callable

from onebar.facts.locate import Place
from onebar.facts.open_meteo import clean_forecast

MAX_HINT_BYTES = 256_000
DEFAULT_TTL_S = 1800.0


def _is_coord(lat: object, lon: object) -> bool:
    ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lat, lon))
    return ok and -90 <= lat <= 90 and -180 <= lon <= 180  # type: ignore[operator]


def _words(s: str) -> str:
    return " ".join(s.lower().split())


def _clean_text(v: object) -> str:
    if not isinstance(v, str) or not 0 < len(v.strip()) <= 200 or any(ord(c) < 32 for c in v):
        raise ValueError("bad text")
    return v.strip()


def _clean_place(raw: object) -> dict:
    if not isinstance(raw, dict) or not _is_coord(raw.get("lat"), raw.get("lon")):
        raise ValueError("bad place")
    return {"query": _clean_text(raw.get("query")), "name": _clean_text(raw.get("name")),
            "lat": float(raw["lat"]), "lon": float(raw["lon"])}


def _clean_forecast_hint(raw: object) -> dict:
    if not isinstance(raw, dict) or not _is_coord(raw.get("lat"), raw.get("lon")):
        raise ValueError("bad forecast hint")
    lat, lon = float(raw["lat"]), float(raw["lon"])
    return {"lat": lat, "lon": lon, "data": clean_forecast(raw.get("data"), lat, lon)}


class HintStore:
    def __init__(self, directory: Path, ttl_s: float = DEFAULT_TTL_S, clock: Callable[[], float] = time.time):
        self.dir = Path(directory)
        self.ttl_s = ttl_s
        self.clock = clock

    def _path(self, key: str) -> Path:
        return self.dir / (hashlib.sha256(key.encode()).hexdigest()[:32] + ".json")

    def _read(self, key: str) -> dict:
        try:
            return json.loads(self._path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _fresh(self, part: object) -> dict | None:
        if isinstance(part, dict) and self.clock() - part.get("at", 0) <= self.ttl_s:
            return part
        return None

    def save(self, key: str, raw: object) -> bool:
        """Keep the parts of `raw` that pass the checks. Returns whether anything was kept."""
        if not isinstance(raw, dict):
            return False
        now = self.clock()
        kept = {}
        for name, clean in (("place", _clean_place), ("forecast", _clean_forecast_hint)):
            if name in raw:
                try:
                    kept[name] = {**clean(raw[name]), "at": now}
                except ValueError:
                    pass
        if not kept:
            return False
        merged = {**self._read(key), **kept}
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path(key).with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(merged), encoding="utf-8")
        os.replace(tmp, self._path(key))
        return True

    def place(self, key: str, query: str) -> Place | None:
        p = self._fresh(self._read(key).get("place"))
        if p is None or _words(p["query"]) != _words(query):
            return None
        return Place(p["name"], p["lat"], p["lon"])

    def forecast(self, key: str, lat: float, lon: float) -> dict | None:
        f = self._fresh(self._read(key).get("forecast"))
        if f is None or (round(f["lat"], 2), round(f["lon"], 2)) != (round(lat, 2), round(lon, 2)):
            return None
        return f["data"]
