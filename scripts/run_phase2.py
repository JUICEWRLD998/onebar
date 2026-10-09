"""Phase 2 exit run: the hand-written questions through the live base model, on frozen real forecasts.

Each question is paired with a frozen forecast at 10:20 local. `storm_at` marks questions whose forecast has
a synthetic thunderstorm hour written into it (the frozen real forecasts hold none); those rows are labelled.
Writes eval/results/phase2_base.json and prints the summary. Needs TINKER_API_KEY.
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from onebar.env import load_env
from onebar.facts.engine import Trip
from onebar.model.client import TinkerDraft
from onebar.pipeline import answer

load_env()
fixtures = {}
for path in sorted((ROOT / "fixtures" / "forecasts").glob("*.json")):
    blob = json.loads(path.read_text(encoding="utf-8"))
    fixtures[blob["meta"]["name"]] = blob["forecast"]

draft = TinkerDraft()
rows = []
for line in (ROOT / "eval" / "phase2_questions.jsonl").read_text(encoding="utf-8").splitlines():
    q = json.loads(line)
    forecast = json.loads(json.dumps(fixtures[q["place"]]))
    day = forecast["hourly"]["time"][0][:10]
    at = datetime.fromisoformat(day + "T10:20")
    if "storm_at" in q:
        i = forecast["hourly"]["time"].index(f"{day}T{q['storm_at']}")
        forecast["hourly"]["weather_code"][i] = 95
    trip = Trip(time.fromisoformat(q["return_by"])) if "return_by" in q else None
    r = answer(q["question"], at, forecast, draft, trip=trip)
    rows.append({
        "id": q["id"], "question": q["question"], "synthetic_storm": "storm_at" in q,
        "path": r.path, "reply": r.text, "septets": r.result.septets, "latency_s": round(r.latency_s, 2),
        "attempts": [{"source": a.source, "text": a.text, "passed": bool(a.result and a.result.passed),
                      "reasons": list(a.result.reasons) if a.result else [], "error": a.error,
                      "latency_s": round(a.latency_s, 2)} for a in r.attempts],
    })
    print(q["id"], r.path, repr(r.text), file=sys.stderr)

n = len(rows)
first_try = sum(r["path"] == "model" for r in rows)
retry = sum(r["path"] == "model-retry" for r in rows)
fallback = sum(r["path"] == "template" for r in rows)
lat = sorted(r["latency_s"] for r in rows)
summary = {
    "model": draft.model, "n": n, "first_try_pass": first_try, "pass_after_retry": first_try + retry,
    "template_fallback": fallback, "latency_p50_s": round(statistics.median(lat), 2), "latency_max_s": lat[-1],
    "model_errors": sum(1 for r in rows for a in r["attempts"] if a["error"]),
}
out = ROOT / "eval" / "results" / "phase2_base.json"
out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
