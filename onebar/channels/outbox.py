"""A file-backed sender: appends each message to data/outbox.jsonl, once per idempotency key.

This is the Phase 5 stand-in for real delivery. Phase 6 adds email and web senders with the same interface
(`send(key, to, text) -> bool`). The key store is the file itself, so a restarted worker still knows what it sent.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class OutboxSender:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _keys(self) -> set[str]:
        keys = set()
        for row in self.sent():
            keys.add(row["key"])
        return keys

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._keys()

    def record(self, key: str, to: str, text: str) -> None:
        """Write the line that makes `key` count as sent. Real senders call this after delivery succeeds."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            row = {"key": key, "to": to, "text": text, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def send(self, key: str, to: str, text: str) -> bool:
        """True when the message was written, False when this key was already sent."""
        with self._lock:
            if key in self._keys():
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            row = {"key": key, "to": to, "text": text, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            return True

    def sent(self) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # a line torn by a crash is not a sent message
            if isinstance(row, dict) and "key" in row:
                out.append(row)
        return out
