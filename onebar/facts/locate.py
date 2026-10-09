"""Place name -> coordinates, with Open-Meteo's geocoding API. The HTTP getter is injected so tests stay offline."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

BASE = "https://geocoding-api.open-meteo.com/v1/search"


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float


def _http_get(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "onebar/0.1 (+https://github.com/JUICEWRLD998/onebar)"})
    for attempt in range(4):  # same transient 429/5xx handling as the forecast client
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise AssertionError("unreachable")


def geocode(name: str, get: Callable[[str], dict] = _http_get) -> Place | None:
    """The best match for a place name, or None when there is none. Network errors propagate."""
    name = name.strip()
    if not name:
        return None
    url = f"{BASE}?name={urllib.parse.quote(name)}&count=1&language=en&format=json"
    results = (get(url) or {}).get("results") or []
    if not results:
        return None
    r = results[0]
    if "latitude" not in r or "longitude" not in r:
        return None
    label = ", ".join(x for x in (r.get("name"), r.get("country")) if x)
    return Place(label or name, float(r["latitude"]), float(r["longitude"]))
