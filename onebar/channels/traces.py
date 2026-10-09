"""Trace of how one reply was produced: which fact each number came from, what the checker said, which path answered.

Stored by message id, shown on the trace page. It never holds the sender's address: the trace page is public to
anyone who knows the id.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def make_trace(question: str, reply) -> dict:
    """`reply` is a pipeline.Reply."""
    r = reply.result
    return {
        "question": question,
        "reply": reply.text,
        "path": reply.path,
        "septets": r.septets,
        "intents": list(r.intents),
        "numbers": [
            {"text": n.text, "ok": n.ok, "sources": [[k, h] for k, h in n.sources]} for n in r.numbers
        ],
        "attempts": [
            {
                "source": a.source,
                "text": a.text,
                "passed": bool(a.result and a.result.passed),
                "reasons": list(a.result.reasons) if a.result else [],
                "error": a.error,
            }
            for a in reply.attempts
        ],
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class TraceStore:
    def __init__(self, directory: Path):
        self.dir = directory

    def _path(self, message_id: str) -> Path:
        return self.dir / (hashlib.sha256(message_id.encode()).hexdigest()[:32] + ".json")

    def trace_id(self, message_id: str) -> str:
        return self._path(message_id).stem

    def save(self, message_id: str, trace: dict) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(message_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # atomic: a reader never sees half a trace
        return path.stem

    def load(self, trace_id: str) -> dict | None:
        if not trace_id.isalnum() or len(trace_id) != 32:
            return None  # not one of ours: never build a path from user input
        path = self.dir / f"{trace_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
