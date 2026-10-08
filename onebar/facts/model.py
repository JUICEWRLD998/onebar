"""Fact containers. A fact is a canonical string (token) plus the raw value and its source hour."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Iterator


@dataclass(frozen=True)
class Fact:
    key: str
    token: str  # the only form the model sees and the checker matches, e.g. "14:40", "55km/h"
    value: Any = None  # raw value (datetime, int, float) for code decisions, never shown to the model
    hour: str | None = None  # ISO forecast hour this fact came from, for the trace


class FactSet:
    def __init__(self, facts: Iterable[Fact] = ()):
        self._facts: dict[str, Fact] = {}
        for fact in facts:
            if fact.key in self._facts:
                raise ValueError(f"duplicate fact key: {fact.key}")
            self._facts[fact.key] = fact

    def __contains__(self, key: object) -> bool:
        return key in self._facts

    def __iter__(self) -> Iterator[Fact]:
        return iter(self._facts.values())

    def __len__(self) -> int:
        return len(self._facts)

    def get(self, key: str) -> Fact | None:
        return self._facts.get(key)

    def token(self, key: str) -> str | None:
        fact = self._facts.get(key)
        return fact.token if fact else None

    def keys(self) -> list[str]:
        return list(self._facts)

    def with_fact(self, fact: Fact) -> "FactSet":
        return FactSet([*self, fact])

    def without(self, *keys: str) -> "FactSet":
        return FactSet(f for f in self if f.key not in keys)
