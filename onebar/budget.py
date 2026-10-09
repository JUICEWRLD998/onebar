"""Spend ledger with a hard cap. Every Tinker sampling call is charged here before its result is used.

The credit is a fixed hackathon grant, so the cap is enforced in code, not by care. Costs are estimates from the
published per-million-token prices with every prompt token billed at the uncached rate (an upper bound). The
total persists in data/spend.json across runs, so a restarted script cannot forget what was spent.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "eval" / "prices.json"
LEDGER = ROOT / "data" / "spend.json"
DEFAULT_CAP_USD = 3.2  # sampling for data and eval; about $1.5 is held back for training so the whole grant stays under $5


class BudgetExceeded(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: Path = LEDGER, cap_usd: float | None = None, prices: dict | None = None):
        self.path = path
        self.cap = float(os.environ.get("ONEBAR_BUDGET_USD", DEFAULT_CAP_USD)) if cap_usd is None else cap_usd
        self._prices = prices
        self._lock = threading.Lock()

    def prices(self) -> dict:
        if self._prices is None:
            self._prices = json.loads(PRICES.read_text(encoding="utf-8"))["models"]
        return self._prices

    def _read(self) -> dict:
        if self.path.is_file():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {"usd": 0.0, "calls": 0, "by_model": {}}

    def spent(self) -> float:
        return self._read()["usd"]

    def cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        price = self.prices().get(model)
        if price is None:
            raise BudgetExceeded(f"no price known for {model}; add it to eval/prices.json before using it")
        return (prompt_tokens * price["prefill"] + completion_tokens * price["sample"]) / 1_000_000

    def check(self, model: str, est_prompt_tokens: int = 1500, est_completion_tokens: int = 150) -> None:
        """Refuse before the call if even one more typical call would pass the cap."""
        with self._lock:
            if self._read()["usd"] + self.cost(model, est_prompt_tokens, est_completion_tokens) > self.cap:
                raise BudgetExceeded(f"spend cap ${self.cap:.2f} reached (spent ${self._read()['usd']:.4f})")

    def charge(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        usd = self.cost(model, prompt_tokens, completion_tokens)
        with self._lock:
            data = self._read()
            data["usd"] = round(data["usd"] + usd, 6)
            data["calls"] += 1
            m = data["by_model"].setdefault(model, {"usd": 0.0, "calls": 0})
            m["usd"] = round(m["usd"] + usd, 6)
            m["calls"] += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return usd


_default: Ledger | None = None


def default() -> Ledger:
    global _default
    if _default is None:
        _default = Ledger(Path(os.environ.get("ONEBAR_LEDGER", LEDGER)))
    return _default
