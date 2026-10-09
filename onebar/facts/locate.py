"""Place name -> coordinates, with Open-Meteo's geocoding API. The HTTP getter is injected so tests stay offline."""
from __future__ import annotations

import json
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
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


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
