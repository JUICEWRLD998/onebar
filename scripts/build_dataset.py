"""Build the Phase 3 dataset, one stage per subcommand. Every stage caches to data/cache and resumes after a stop.

  locations     Overpass -> data/locations.jsonl
  situations    historical forecasts + seed questions -> data/situations.jsonl
  paraphrase    large model rewrites ~60% of questions into hiker register -> data/questions.jsonl
  teacher-eval  pick the teacher: pass rate of each candidate model on a fixed sample
  teacher       4 candidates per train/val question, keep the best passing one -> data/train.jsonl, data/val.jsonl
  assemble      eval/test.jsonl (frozen test set) and data/stats.json

Needs TINKER_API_KEY for paraphrase, teacher-eval and teacher.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import threading
import time
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from onebar.check.checker import check
from onebar.dataset import forecasts, llm, locations, paraphrase, questions, situations, teacher
from onebar.dataset.serde import facts_from_json
from onebar.env import load_env

DATA = ROOT / "data"
CACHE = DATA / "cache"
SEED = 7
PARAPHRASE_SHARE = 60  # percent of questions sent to the paraphraser
TEACHER_MODEL = "Qwen/Qwen3.5-397B-A17B"


def read_jsonl(path: Path, lenient: bool = False) -> list[dict]:
    """lenient=True is for resume caches only: a line torn by an interrupted write is skipped and redrawn."""
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if not lenient:
                raise
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def log(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


# ---- stage 1 -------------------------------------------------------------------------------------------------

def cmd_locations(args) -> None:
    out: list[locations.Location] = []
    missing: list[str] = []
    for region in locations.REGIONS:
        raw_path = CACHE / "overpass" / f"{region.name}.json"
        if raw_path.is_file():
            elements = json.loads(raw_path.read_text(encoding="utf-8"))
        elif args.cached_only:
            log(f"{region.name:28s} not cached, skipped (--cached-only)")
            continue
        else:
            try:
                elements = locations.fetch_region(region)
            except RuntimeError as exc:
                missing.append(region.name)
                log(f"{region.name:28s} SKIPPED: {exc}")
                continue
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(elements, separators=(",", ":")), encoding="utf-8")
            time.sleep(2)
        parsed = locations.parse_elements(elements, region)
        picked = locations.sample(parsed, args.quota, seed=SEED)
        kinds = Counter(x.kind for x in picked)
        log(f"{region.name:28s} found {len(parsed):5d}  kept {len(picked):3d}  {dict(kinds)}")
        out.extend(picked)
    out = list({x.id: x for x in out}.values())  # overlapping region boxes can return the same OSM node
    locations.write_jsonl(out, DATA / "locations.jsonl")
    log(f"locations: {len(out)} -> data/locations.jsonl")
    if missing:
        log(f"INCOMPLETE: {len(missing)} regions failed ({', '.join(missing)}). Rerun this stage; finished regions are cached.")
        sys.exit(1)


# ---- stage 2 -------------------------------------------------------------------------------------------------

def cmd_situations(args) -> None:
    locs = locations.read_jsonl(DATA / "locations.jsonl")
    cache = CACHE / "forecasts"

    def load(loc):
        start = forecasts.pick_start(loc.id, SEED)
        time.sleep(0.25)  # stay well inside Open-Meteo's fair use per worker
        return forecasts.fetch_window(loc.id, loc.lat, loc.lon, start, cache)

    log(f"fetching {len(locs)} forecast windows with {args.workers} workers")
    fcs = llm.parallel_map(load, locs, workers=args.workers)
    rows, failed = [], 0
    for loc, fc in zip(locs, fcs):
        if isinstance(fc, Exception):
            failed += 1
            log(f"  skip {loc.id} {loc.name}: {fc}")
            continue
        rng = random.Random(f"{SEED}:{loc.id}:sit")
        for sit in situations.sample_situations(loc, fc, rng, k=args.per_location):
            rows.append(situations.build_row(sit, fc, questions.draw_seed(rng), rng))
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate row ids"
    write_jsonl(DATA / "situations.jsonl", rows)
    log(f"situations: {len(rows)} rows from {len(locs) - failed} locations ({failed} failed) -> data/situations.jsonl")
    stats_rows(rows)


def stats_rows(rows: list[dict]) -> None:
    n = len(rows)
    keys = [{f["key"] for f in r["facts"]} for r in rows]
    log("split:", dict(Counter(r["split"] for r in rows)))
    log(f"storm ahead: {sum('storm_first' in k for k in keys) / n:.1%}   rain ahead: {sum('rain_first' in k for k in keys) / n:.1%}"
        f"   trip: {sum(r['trip'] is not None for r in rows) / n:.1%}   dark: {sum('dark_now' in k for k in keys) / n:.1%}")
    log("intents:", dict(Counter(i for r in rows for i in r["intents"])))
    log("paraphrased:", sum(r["paraphrased"] for r in rows))


# ---- stage 3 -------------------------------------------------------------------------------------------------

def wants_paraphrase(row_id: str) -> bool:
    return int(hashlib.sha256(row_id.encode()).hexdigest()[:8], 16) % 100 < PARAPHRASE_SHARE


def cmd_paraphrase(args) -> None:
    rows = read_jsonl(DATA / "situations.jsonl")
    cache_path = CACHE / "paraphrase.jsonl"
    done = {r["id"]: r["candidate"] for r in read_jsonl(cache_path, lenient=True)}
    todo = [r for r in rows if wants_paraphrase(r["id"]) and r["id"] not in done]
    sampler = llm.Sampler(args.model)
    log(f"paraphrasing {len(todo)} questions ({len(done)} cached)")

    def work(row):
        text = sampler.sample(paraphrase.prompt(row["seed_question"]), n=1, temperature=0.9, max_tokens=60)[0]
        append_jsonl(cache_path, {"id": row["id"], "candidate": text})
        return text

    errs = [r for r in llm.parallel_map(work, todo, workers=args.workers) if isinstance(r, Exception)]
    if errs:
        log(f"{len(errs)} paraphrase calls failed (kept seed question); first: {errs[0]}")
    done = {r["id"]: r["candidate"] for r in read_jsonl(cache_path, lenient=True)}
    kept = 0
    for row in rows:
        cand = done.get(row["id"])
        text = paraphrase.accept(row["seed_question"], cand) if cand is not None else None
        if text and text.lower() != row["seed_question"].lower():
            row["question"], row["paraphrased"] = text, True
            kept += 1
    write_jsonl(DATA / "questions.jsonl", rows)
    asked = sum(wants_paraphrase(r["id"]) for r in rows)
    log(f"paraphrase: accepted {kept} of {asked} asked ({kept / max(asked, 1):.0%}) -> data/questions.jsonl")


# ---- stage 4 -------------------------------------------------------------------------------------------------

def teacher_request(model: str, facts, question: str):
    return teacher.messages(facts, question) if "gpt-oss" in model else teacher.prompt(facts, question)


def draw(sampler, model, row, n, temperature):
    facts = facts_from_json(row["facts"])
    return sampler.sample(teacher_request(model, facts, row["question"]), n=n, temperature=temperature, max_tokens=120)


def cmd_teacher_eval(args) -> None:
    rows = [r for r in read_jsonl(DATA / "questions.jsonl") if r["split"] == "train"]
    sample = random.Random(SEED).sample(rows, args.n)
    report = {}
    for model in args.models:
        sampler = llm.Sampler(model)
        t0 = time.time()
        results = llm.parallel_map(lambda r: draw(sampler, model, r, 4, 0.8), sample, workers=args.workers)
        picked = errors = first_pass = 0
        for row, cs in zip(sample, results):
            if isinstance(cs, Exception):
                errors += 1
                continue
            facts = facts_from_json(row["facts"])
            picked += teacher.pick(cs, facts, row["question"]) is not None
            first = teacher.clean(cs[0])
            first_pass += bool(teacher.natural(first) and check(first, facts, row["question"]).passed)
        report[model] = {
            "questions": len(sample), "errors": errors, "with_a_passing_candidate": picked,
            "first_candidate_passes": first_pass, "seconds": round(time.time() - t0, 1),
        }
        log(model, report[model])
    out = ROOT / "eval" / "results" / "teacher_choice.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    best = max(report, key=lambda m: (report[m]["with_a_passing_candidate"], -report[m]["seconds"]))
    log("best teacher by questions with a passing candidate:", best)


def cmd_teacher(args) -> None:
    rows = read_jsonl(DATA / "questions.jsonl")
    todo_rows = [r for r in rows if r["split"] in ("train", "val")]
    cache_path = CACHE / f"teacher_{args.model.replace('/', '_')}.jsonl"
    done = {r["id"]: r["candidates"] for r in read_jsonl(cache_path, lenient=True)}
    todo = [r for r in todo_rows if r["id"] not in done]
    if args.cached_only:
        todo = []
    sampler = llm.Sampler(args.model)
    log(f"teacher {args.model}: {len(todo)} to draw, {len(done)} cached")

    def work(row):
        cs = draw(sampler, args.model, row, args.candidates, 0.8)
        append_jsonl(cache_path, {"id": row["id"], "candidates": cs})
        return cs

    errs = [r for r in llm.parallel_map(work, todo, workers=args.workers) if isinstance(r, Exception)]
    if errs:
        log(f"{len(errs)} draws failed; rerun to retry them. first: {errs[0]}")
    done = {r["id"]: r["candidates"] for r in read_jsonl(cache_path, lenient=True)}

    kept: dict[str, list[dict]] = {"train": [], "val": []}
    dropped: Counter = Counter()
    for row in todo_rows:
        cs = done.get(row["id"])
        if cs is None:
            dropped["no_draw"] += 1
            continue
        facts = facts_from_json(row["facts"])
        ch = teacher.pick(cs, facts, row["question"])
        if ch is None:
            dropped["no_passing_candidate"] += 1
            continue
        kept[row["split"]].append({**row, "reply": ch.text, "septets": ch.result.septets,
                                   "teacher": {"model": args.model, "candidates": ch.n_candidates, "passed": ch.n_passed}})
    write_jsonl(DATA / "train.jsonl", kept["train"])
    write_jsonl(DATA / "val.jsonl", kept["val"])
    log(f"teacher: train {len(kept['train'])}, val {len(kept['val'])}, dropped {dict(dropped)}")


# ---- stage 5 -------------------------------------------------------------------------------------------------

def cmd_assemble(args) -> None:
    rows = read_jsonl(DATA / "questions.jsonl")
    test = [r for r in rows if r["split"] == "test"]
    write_jsonl(ROOT / "eval" / "test.jsonl", test)
    train, val = read_jsonl(DATA / "train.jsonl"), read_jsonl(DATA / "val.jsonl")
    share = lambda rs, pred: round(sum(pred(r) for r in rs) / max(len(rs), 1), 3)
    stats = {
        "built": date.today().isoformat(),
        "locations": len(read_jsonl(DATA / "locations.jsonl")),
        "situations": len(rows),
        "test_rows": len(test), "train_rows": len(train), "val_rows": len(val),
        "paraphrased_share": share(rows, lambda r: r["paraphrased"]),
        "reply_septets_mean": round(sum(r["septets"] for r in train) / max(len(train), 1), 1),
        "storm_ahead_share_train": share(train, lambda r: any(f["key"] == "storm_first" for f in r["facts"])),
        "teacher": train[0]["teacher"]["model"] if train else None,
    }
    (DATA / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    log(json.dumps(stats, indent=2))


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("locations")
    a.add_argument("--quota", type=int, default=36)
    a.add_argument("--cached-only", action="store_true", help="use only regions already downloaded")
    a.set_defaults(fn=cmd_locations)
    a = sub.add_parser("situations")
    a.add_argument("--workers", type=int, default=4)
    a.add_argument("--per-location", type=int, default=3)
    a.set_defaults(fn=cmd_situations)
    a = sub.add_parser("paraphrase")
    a.add_argument("--model", default=TEACHER_MODEL)
    a.add_argument("--workers", type=int, default=8)
    a.set_defaults(fn=cmd_paraphrase)
    a = sub.add_parser("teacher-eval")
    a.add_argument("--models", nargs="+", default=[TEACHER_MODEL, "openai/gpt-oss-120b"])
    a.add_argument("--n", type=int, default=50)
    a.add_argument("--workers", type=int, default=8)
    a.set_defaults(fn=cmd_teacher_eval)
    a = sub.add_parser("teacher")
    a.add_argument("--candidates", type=int, default=4)
    a.add_argument("--cached-only", action="store_true", help="assemble from drawn candidates; make no API calls")
    a.add_argument("--model", default=TEACHER_MODEL)
    a.add_argument("--workers", type=int, default=8)
    a.set_defaults(fn=cmd_teacher)
    a = sub.add_parser("assemble")
    a.set_defaults(fn=cmd_assemble)
    args = p.parse_args()
    load_env()
    args.fn(args)


if __name__ == "__main__":
    main()
