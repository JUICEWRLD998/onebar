"""Fetch 20 real Open-Meteo forecasts once and freeze them under fixtures/forecasts/.

Each file is {"meta": {name, lat, lon, fetched_utc}, "forecast": <raw Open-Meteo response>}.
Run once; the committed files are the test inputs. Re-running overwrites them.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "forecasts"

PLACES = [
    ("jungfrau_ch", 46.55, 7.98),
    ("snowdon_uk", 53.07, -4.08),
    ("ben_nevis_uk", 56.80, -5.00),
    ("mont_blanc_fr", 45.83, 6.86),
    ("dolomites_it", 46.41, 11.84),
    ("tatra_pl", 49.18, 20.09),
    ("galdhopiggen_no", 61.64, 8.31),
    ("kebnekaise_se", 67.90, 18.52),
    ("teide_es", 28.27, -16.64),
    ("half_dome_us", 37.75, -119.53),
    ("rainier_us", 46.85, -121.76),
    ("longs_peak_us", 40.25, -105.62),
    ("presidential_us", 44.27, -71.30),
    ("banff_ca", 51.43, -116.18),
    ("torres_cl", -51.00, -73.00),
    ("aconcagua_ar", -32.65, -70.01),
    ("kilimanjaro_tz", -3.07, 37.35),
    ("everest_bc_np", 28.00, 86.85),
    ("fuji_jp", 35.36, 138.73),
    ("tongariro_nz", -39.13, 175.65),
]

HOURLY = (
    "temperature_2m,apparent_temperature,precipitation_probability,precipitation,"
    "weather_code,wind_speed_10m,wind_gusts_10m,cape"
)


def fetch(lat: float, lon: float) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&hourly={HOURLY}"
        "&daily=sunrise,sunset&timezone=auto&forecast_days=3"
    )
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (name, lat, lon) in enumerate(PLACES, 1):
        data = fetch(lat, lon)
        meta = {
            "name": name,
            "lat": lat,
            "lon": lon,
            "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        }
        path = OUT / f"{i:02d}_{name}.json"
        path.write_text(json.dumps({"meta": meta, "forecast": data}, indent=1), encoding="utf-8")
        print(path.name, data.get("elevation"), data.get("timezone"))
        time.sleep(1.5)


if __name__ == "__main__":
    main()
