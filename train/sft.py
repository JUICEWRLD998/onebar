"""Phase 4a: supervised fine-tuning of Qwen3-8B (LoRA) on the teacher replies, on Tinker.

  python train/sft.py --dry-run            # tokens, cost estimate, no training
  python train/sft.py --max-steps 1        # one optimiser step, to see the API's real output
  python train/sft.py                      # full run

Safety: the estimate must fit --max-usd or the run refuses to start; each epoch's cost is written to the spend
ledger; validation sampling goes through the ledger's cap. The best epoch by validation first-try pass rate wins.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from onebar import budget, train_data
from onebar.dataset.llm import parallel_map
from onebar.dataset.serde import facts_from_json
from onebar.env import load_env
from onebar.model.client import TinkerDraft
from onebar.pipeline import answer_from_facts

BASE = "Qwen/Qwen3-8B"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def val_first_try(model: str, rows: list[dict]) -> float:
    draft = TinkerDraft(model=model)

    def one(row):
        facts = facts_from_json(row["facts"])
        r = answer_from_facts(row["question"], facts, draft)
        return bool(r.attempts[0].result and r.attempts[0].result.passed)

    out = parallel_map(one, rows, workers=6)
    return sum(1 for o in out if o is True) / len(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--rank", type=int, default=32)
    p.add_argument("--max-usd", type=float, default=1.6)
    p.add_argument("--val-n", type=int, default=150)
    p.add_argument("--max-steps", type=int)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    load_env()

    import tinker
    from tinker import types

    price = json.loads((ROOT / "eval" / "prices.json").read_text(encoding="utf-8"))["train"][BASE]
    svc = tinker.ServiceClient()
    tok = svc.create_sampling_client(base_model=BASE).get_tokenizer()

    def tokenize(s: str) -> list[int]:
        return tok.encode(s, add_special_tokens=False)

    train_rows, val_rows = read(ROOT / "data" / "train.jsonl"), read(ROOT / "data" / "val.jsonl")
    examples = train_data.build_examples(tokenize, train_rows)
    est = train_data.estimate_cost(examples, args.epochs, price)
    tokens = sum(e.n_tokens for e in examples)
    steps_per_epoch = -(-len(examples) // args.batch)
    print(f"{len(examples)} examples, {tokens} tokens/epoch, {steps_per_epoch} steps/epoch, "
          f"{args.epochs} epochs -> estimated training cost ${est:.3f} at ${price}/M tokens")
    if est > args.max_usd:
        sys.exit(f"estimate ${est:.3f} exceeds --max-usd {args.max_usd}; lower --epochs or raise the cap")
    if args.dry_run:
        return

    led = budget.default()
    tc = svc.create_lora_training_client(base_model=BASE, rank=args.rank, seed=7)
    rng = random.Random(7)
    val_sample = rng.sample(val_rows, min(args.val_n, len(val_rows)))
    total_steps = steps_per_epoch * args.epochs
    step, log, epochs_out = 0, [], []

    for epoch in range(1, args.epochs + 1):
        order = list(range(len(examples)))
        rng.shuffle(order)
        for b in range(0, len(order), args.batch):
            batch = [examples[i] for i in order[b : b + args.batch]]
            weights = train_data.normalise(batch)
            data = [
                types.Datum(
                    model_input=types.ModelInput.from_ints(e.input_ids),
                    loss_fn_inputs={"target_tokens": e.target_ids, "weights": w},
                )
                for e, w in zip(batch, weights)
            ]
            lr = args.lr * max(0.1, 1 - step / total_steps)  # linear decay to 10%
            fb = tc.forward_backward(data, "cross_entropy")
            op = tc.optim_step(types.AdamParams(learning_rate=lr))
            res = fb.result()
            op.result()
            if step == 0:
                print("first result fields:", [a for a in dir(res) if not a.startswith("_")][:20])
                print("metrics:", getattr(res, "metrics", None))
            metrics = getattr(res, "metrics", {}) or {}
            loss = next((v for k, v in metrics.items() if "loss" in k), None)
            log.append({"step": step, "lr": lr, "loss": loss})
            if step % 10 == 0:
                print(f"epoch {epoch} step {step}/{total_steps} lr {lr:.2e} loss {loss}", flush=True)
            step += 1
            if args.max_steps and step >= args.max_steps:
                spent = sum(e.n_tokens for e in batch) * price / 1e6
                led.charge_usd(f"train:{BASE}", spent)
                print(f"stopped at --max-steps; charged about ${spent:.5f}")
                return
        led.charge_usd(f"train:{BASE}", tokens * price / 1e6)
        saved = tc.save_weights_for_sampler(f"onebar-sft-e{epoch}").result()
        path = saved.path
        t0 = time.time()
        vp = val_first_try(path, val_sample)
        print(f"epoch {epoch}: sampler weights {path}\n  validation first-try pass {vp:.3f} on {len(val_sample)} "
              f"({time.time() - t0:.0f}s); ledger spend ${led.spent():.3f}", flush=True)
        epochs_out.append({"epoch": epoch, "sampler_path": path, "val_first_try_pass": vp})

    best = max(epochs_out, key=lambda e: e["val_first_try_pass"])
    out = {
        "base": BASE, "rank": args.rank, "lr": args.lr, "batch": args.batch, "epochs": args.epochs,
        "train_rows": len(examples), "tokens_per_epoch": tokens, "estimated_cost_usd": round(est, 4),
        "val_rows": len(val_sample), "epochs_out": epochs_out, "best": best, "loss_log": log,
    }
    (ROOT / "eval" / "results" / "sft_run.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("best:", best)


if __name__ == "__main__":
    main()
