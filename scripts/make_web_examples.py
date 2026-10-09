"""Build the web UI's recorded examples from real test-set rows.

Each example is a real question from eval/test.jsonl, the tuned model's real reply and the base model's real first
draft from eval/results, checked by the real checker, with the real hourly forecast the facts were cut from.
The output has the same shape as the live /api/trace response, so the UI renders both the same way.

  python scripts/make_web_examples.py        -> web/src/data/examples.json
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from onebar.channels.traces import hours_slice, make_baseline
from onebar.check.checker import check
from onebar.dataset import forecasts
from onebar.dataset.serde import facts_from_json

# (row id, short name). Chosen to cover a clear "yes", a storm already under way, and a turn-around time.
PICKS = [
    ("osm:n6927207747|2026-08-19T13:46", "ridge"),
    ("osm:n294758495|2026-08-06T14:11", "storm"),
    ("osm:n1373128447|2026-09-08T17:43", "turnback"),
]


def main() -> None:
    test = {r["id"]: r for r in map(json.loads, (ROOT / "eval" / "test.jsonl").read_text(encoding="utf-8").splitlines())}
    tuned = {r["id"]: r for r in json.loads((ROOT / "eval" / "results" / "tuned.json").read_text(encoding="utf-8"))["rows"]}
    base = {r["id"]: r for r in json.loads((ROOT / "eval" / "results" / "base.json").read_text(encoding="utf-8"))["rows"]}
    out = []
    for row_id, name in PICKS:
        row = test[row_id]
        facts = facts_from_json(row["facts"])
        q = row["question"]
        reply = tuned[row_id]["reply"]
        res = check(reply, facts, q)
        assert res.passed, (row_id, res.reasons)
        loc = row["loc"]
        start = forecasts.pick_start(loc["id"], 7)
        cache = ROOT / "data" / "cache" / "forecasts" / f"{loc['id'].replace(':', '_')}_{start}.json"
        fc = json.loads(cache.read_text(encoding="utf-8"))
        at = datetime.fromisoformat(row["at"])
        hours = hours_slice(fc, at)
        assert len(hours) == 12, (row_id, len(hours))
        elevation = next((f["token"] for f in row["facts"] if f["key"] == "elevation"), None)
        out.append({
            "id": f"example-{name}",
            "recorded": True,
            "question": q,
            "place": {"name": loc["name"], "lat": loc["lat"], "lon": loc["lon"], "elevation": elevation},
            "at": row["at"],
            "trip": row["trip"],
            "reply": reply,
            "path": tuned[row_id]["path"],
            "septets": res.septets,
            "intents": list(res.intents),
            "numbers": [{"text": n.text, "ok": n.ok, "sources": [[k, h] for k, h in n.sources]} for n in res.numbers],
            "attempts": [{"source": "model", "text": reply, "passed": True, "reasons": [], "error": None}],
            "hours": hours,
            "baseline": make_baseline(base[row_id]["first_text"], facts, q),
            "created": date.today().isoformat(),
        })
    dest = ROOT / "web" / "src" / "data" / "examples.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for e in out:
        print(e["id"], "|", e["question"], "|", e["reply"], "|", e["septets"], "septets |",
              [(n["text"], n["sources"]) for n in e["numbers"]], "| base ok:", e["baseline"]["passed"], e["baseline"]["reasons"])


if __name__ == "__main__":
    main()
