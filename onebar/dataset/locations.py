"""Real trailheads, summits and alpine huts from OpenStreetMap (Overpass), spread over mountain regions worldwide."""
from __future__ import annotations

import json
import random
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "onebar-hackathon/0.1 (dataset build)"


@dataclass(frozen=True)
class Region:
    name: str
    climate: str
    bbox: tuple[float, float, float, float]  # south, west, north, east


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    kind: str  # peak | trailhead | hut
    lat: float
    lon: float
    region: str
    ele: float | None = None


REGIONS: tuple[Region, ...] = (
    Region("alps_valais", "alpine", (46.0, 7.0, 46.7, 8.4)),
    Region("alps_bernese", "alpine", (46.4, 7.6, 46.9, 8.6)),
    Region("alps_mont_blanc", "alpine", (45.5, 6.6, 46.1, 7.2)),
    Region("alps_tyrol", "alpine", (46.7, 10.2, 47.4, 12.2)),
    Region("alps_dolomites", "alpine", (46.2, 11.4, 46.8, 12.4)),
    Region("alps_julian", "alpine", (46.2, 13.4, 46.6, 14.2)),
    Region("pyrenees", "alpine", (42.5, -0.8, 42.9, 1.2)),
    Region("tatra", "continental", (49.1, 19.6, 49.35, 20.4)),
    Region("carpathians_romania", "continental", (45.4, 24.4, 45.7, 25.2)),
    Region("norway_jotunheimen", "subarctic", (61.3, 7.5, 61.9, 8.9)),
    Region("sweden_kebnekaise", "subarctic", (67.7, 17.8, 68.1, 18.9)),
    Region("scotland_highlands", "maritime", (56.6, -5.4, 57.2, -3.6)),
    Region("wales_snowdonia", "maritime", (52.8, -4.2, 53.2, -3.7)),
    Region("england_lake_district", "maritime", (54.3, -3.3, 54.7, -2.9)),
    Region("iceland_south", "subarctic", (63.6, -20.0, 64.3, -17.5)),
    Region("spain_picos", "maritime", (43.0, -5.2, 43.35, -4.6)),
    Region("tenerife", "subtropical", (28.0, -16.9, 28.6, -16.3)),
    Region("morocco_atlas", "arid", (31.0, -8.0, 31.35, -7.6)),
    Region("tanzania_kilimanjaro", "tropical", (-3.4, 37.0, -2.9, 37.7)),
    Region("south_africa_drakensberg", "subtropical", (-29.4, 29.0, -28.6, 29.8)),
    Region("nepal_everest", "alpine", (27.6, 86.4, 28.1, 87.1)),
    Region("nepal_annapurna", "alpine", (28.3, 83.6, 28.9, 84.4)),
    Region("india_ladakh", "arid", (33.9, 77.0, 34.4, 77.9)),
    Region("kyrgyz_tien_shan", "continental", (42.0, 74.0, 42.9, 78.0)),
    Region("japan_alps", "continental", (35.9, 137.4, 36.5, 138.0)),
    Region("japan_hokkaido", "continental", (43.3, 142.6, 43.8, 143.3)),
    Region("taiwan_central", "subtropical", (23.3, 120.7, 24.5, 121.5)),
    Region("nz_southern_alps", "maritime", (-44.2, 169.4, -43.3, 170.5)),
    Region("nz_tongariro", "maritime", (-39.4, 175.4, -39.0, 175.8)),
    Region("tasmania", "maritime", (-42.2, 145.8, -41.5, 146.6)),
    Region("australia_alps", "temperate", (-36.7, 147.2, -36.2, 148.6)),
    Region("patagonia_torres", "maritime", (-51.3, -73.6, -50.7, -72.6)),
    Region("patagonia_fitz_roy", "maritime", (-49.5, -73.2, -49.0, -72.7)),
    Region("andes_aconcagua", "arid", (-33.1, -70.4, -32.4, -69.6)),
    Region("peru_cordillera_blanca", "alpine", (-9.7, -77.7, -8.8, -77.2)),
    Region("colombia_cocuy", "tropical", (6.2, -72.5, 6.7, -72.1)),
    Region("usa_colorado_rockies", "continental", (39.5, -106.6, 40.5, -105.4)),
    Region("usa_sierra_nevada", "alpine", (36.3, -118.8, 37.9, -118.2)),
    Region("usa_cascades_wa", "maritime", (46.6, -121.9, 48.8, -120.8)),
    Region("usa_white_mountains", "continental", (44.0, -71.6, 44.5, -71.0)),
    Region("usa_smokies", "temperate", (35.4, -83.7, 35.8, -83.0)),
    Region("canada_banff", "alpine", (51.0, -116.6, 51.9, -115.4)),
    Region("canada_coast_mountains", "maritime", (49.6, -123.4, 50.3, -122.7)),
    Region("alaska_chugach", "subarctic", (60.9, -150.5, 61.6, -148.5)),
    Region("hawaii_big_island", "tropical", (19.4, -155.9, 19.9, -155.3)),
)


def build_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    box = f"({s},{w},{n},{e})"
    return (
        "[out:json][timeout:90];("
        f'node["natural"="peak"]["name"]{box};'
        f'node["highway"="trailhead"]["name"]{box};'
        f'node["tourism"="alpine_hut"]["name"]{box};'
        ");out;"
    )


def _kind(tags: dict) -> str | None:
    if tags.get("natural") == "peak":
        return "peak"
    if tags.get("tourism") == "alpine_hut":
        return "hut"
    if tags.get("highway") == "trailhead":
        return "trailhead"
    return None


def parse_elements(elements: list[dict], region: Region) -> list[Location]:
    out: list[Location] = []
    seen: set[tuple[str, float, float]] = set()
    for e in elements:
        if e.get("type") != "node" or "lat" not in e:
            continue
        tags = e.get("tags") or {}
        name, kind = (tags.get("name") or "").strip(), _kind(tags)
        if not name or kind is None:
            continue
        key = (name.lower(), round(e["lat"], 2), round(e["lon"], 2))
        if key in seen:
            continue
        seen.add(key)
        try:
            ele = float(str(tags["ele"]).split(";")[0].replace("m", "").strip()) if "ele" in tags else None
        except ValueError:
            ele = None
        out.append(Location(f"osm:n{e['id']}", name, kind, e["lat"], e["lon"], region.name, ele))
    return out


def sample(locations: list[Location], n: int, seed: int) -> list[Location]:
    """Up to n locations, seeded. Huts and trailheads are drawn in turn with peaks so peaks cannot crowd them out."""
    if len(locations) <= n:
        return list(locations)
    rng = random.Random(seed)
    pools = {k: [x for x in locations if x.kind == k] for k in ("hut", "trailhead", "peak")}
    for pool in pools.values():
        rng.shuffle(pool)
    out: list[Location] = []
    while len(out) < n and any(pools.values()):
        for k in ("hut", "trailhead", "peak", "peak"):  # peaks get two turns in four
            if pools[k] and len(out) < n:
                out.append(pools[k].pop())
    return sorted(out, key=lambda x: x.id)


def fetch_region(
    region: Region,
    post: Callable[[str], dict] | None = None,
    retries: int = 6,
) -> list[dict]:
    def default_post(q: str) -> dict:
        req = urllib.request.Request(
            OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)

    post = post or default_post
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return post(build_query(region.bbox))["elements"]
        except Exception as exc:  # Overpass answers 429/504 under load; back off and retry
            last = exc
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Overpass failed for {region.name}: {last}")


def write_jsonl(locations: list[Location], path: Path) -> None:
    path.write_text("".join(json.dumps(asdict(x), ensure_ascii=False) + "\n" for x in locations), encoding="utf-8")


def read_jsonl(path: Path) -> list[Location]:
    return [Location(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
