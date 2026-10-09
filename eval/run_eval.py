"""Run one system over the frozen test set and write eval/results/<system>.json.

  python eval/run_eval.py --system template
  python eval/run_eval.py --system base            # Qwen/Qwen3-8B
  python eval/run_eval.py --system large           # Qwen/Qwen3.6-35B-A3B, same short prompt as base
  python eval/run_eval.py --system tuned           # ONEBAR_MODEL (tinker://.../sampler_weights/...)

Accuracy metrics come from one concurrent pass over every row. Latency comes from a second, sequential pass over the
first --latency-n rows, because concurrent timings include queueing on this machine.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from onebar import evaluation
from onebar.dataset.llm import parallel_map
from onebar.dataset.serde import facts_from_json
from onebar.env import load_env
from onebar.model.client import TinkerDraft
from onebar.pipeline import answer_from_facts

MODELS = {"base": "Qwen/Qwen3-8B", "large": "Qwen/Qwen3.6-35B-A3B"}


def load_rows(limit: int | None) -> list[dict]:
    path = ROOT / "eval" / "test.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--system", required=True, choices=["template", "base", "large", "tuned"])
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--latency-n", type=int, default=40)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    load_env()

    draft = None
    model = None
    if args.system != "template":
        model = MODELS.get(args.system) or os.environ.get("ONEBAR_MODEL")
        if not model:
            sys.exit("tuned system needs ONEBAR_MODEL set to the tinker://.../sampler_weights/... path")
        draft = TinkerDraft(model=model)

    rows = load_rows(args.limit)
    facts = {r["id"]: facts_from_json(r["facts"]) for r in rows}

    def one(row):
        return answer_from_facts(row["question"], facts[row["id"]], draft)

    t0 = time.time()
    replies = parallel_map(one, rows, workers=args.workers)
    crashed = [r for r in replies if isinstance(r, Exception)]
    if crashed:
        sys.exit(f"{len(crashed)} rows crashed the pipeline (a bug, not a model error): {crashed[0]!r}")
    scores = [evaluation.score_row(row["id"], rep, facts[row["id"]]) for row, rep in zip(rows, replies)]
    wall = time.time() - t0

    # Token totals are read before the latency pass, which calls the model again and must not inflate the cost.
    usage = {"prompt": 0, "completion": 0, "calls": 0}
    if draft is not None:
        usage = {"prompt": draft.prompt_tokens, "completion": draft.completion_tokens, "calls": draft.calls}

    latencies = [answer_from_facts(r["question"], facts[r["id"]], draft).latency_s for r in rows[: args.latency_n]]

    prices = json.loads((ROOT / "eval" / "prices.json").read_text(encoding="utf-8"))["models"]
    if model is None:
        price = {"prefill": 0.0, "sample": 0.0}
    elif model.startswith("tinker://"):
        price = prices.get("Qwen/Qwen3-8B")  # a LoRA adapter of the base model samples at the base price
    else:
        price = prices.get(model)
    metrics = evaluation.aggregate(scores, latencies)
    metrics["cost_per_answer_usd"] = evaluation.cost_per_answer(usage["prompt"], usage["completion"], len(rows), price)
    metrics["model_calls_per_answer"] = usage["calls"] / len(rows) if rows else 0.0
    metrics["tokens_per_answer"] = (usage["prompt"] + usage["completion"]) / len(rows) if rows else 0.0

    out = {
        "system": args.system,
        "model": model or "none (code template)",
        "test_rows": len(rows),
        "wall_seconds_concurrent": round(wall, 1),
        "metrics": metrics,
        "rows": [
            {"id": s.id, "path": s.path, "reply": s.reply, "septets": s.septets, "first_text": s.first_text,
             "first_reasons": list(s.first_reasons)}
            for s in scores
        ],
    }
    dest = ROOT / "eval" / "results" / f"{args.system}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, default=float) + "\n", encoding="utf-8")
    print(json.dumps({"system": args.system, "model": out["model"], **metrics}, indent=2, default=float))


if __name__ == "__main__":
    main()
