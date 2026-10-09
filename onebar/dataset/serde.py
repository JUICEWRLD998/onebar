"""FactSet <-> JSON. Datetimes are tagged so a roundtrip restores the exact Python type; the template depends on it."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from onebar.facts.model import Fact, FactSet


def _enc(v: Any) -> Any:
    if isinstance(v, datetime):
        return {"dt": v.isoformat()}
    return v  # bool, int, float, None and str are JSON-native and keep their type


def _dec(v: Any) -> Any:
    if isinstance(v, dict) and set(v) == {"dt"}:
        return datetime.fromisoformat(v["dt"])
    return v


def facts_to_json(facts: FactSet) -> list[dict]:
    return [{"key": f.key, "token": f.token, "value": _enc(f.value), "hour": f.hour} for f in facts]


def facts_from_json(rows: list[dict]) -> FactSet:
    return FactSet(Fact(r["key"], r["token"], _dec(r["value"]), r["hour"]) for r in rows)
