"""The web phone's backend: post a message, poll for the reply, open the trace of how it was made.

A web "sender" is an anonymous session id chosen by the browser. Replies are stored by message id (an unguessable
uuid), so whoever holds the id can read that one reply and nothing else.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from onebar.channels.hints import MAX_HINT_BYTES, HintStore
from onebar.channels.ratelimit import RateLimiter
from onebar.channels.traces import TraceStore
from onebar.commands import MAX_LEN
from onebar.temporal.models import Inbound
from onebar.temporal.starter import workflow_id

SESSION_RX = re.compile(r"[A-Za-z0-9_-]{8,64}")
ID_RX = re.compile(r"[0-9a-f]{32}")

Deliver = Callable[[str, Inbound], Awaitable[None]]


class WebSender:
    """Stores the reply to a web message so the browser can fetch it. Implements send(key, to, text) -> bool."""

    def __init__(self, directory: Path):
        self.dir = directory

    def _path(self, message_id: str) -> Path:
        return self.dir / (hashlib.sha256(message_id.encode()).hexdigest()[:32] + ".json")

    def send(self, key: str, to: str, text: str) -> bool:
        if not to.startswith("web:") or not key.startswith("reply:"):
            return False  # alerts go to a contact, which is never a browser session
        path = self._path(key[len("reply:"):])
        if path.exists():
            return False
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"text": text, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
                       encoding="utf-8")
        tmp.replace(path)
        return True

    def get(self, message_id: str) -> dict | None:
        path = self._path(message_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None


class Message(BaseModel):
    session: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1)
    hint: dict | None = None  # what the browser looked up itself; see channels/hints.py


def create_app(deliver: Deliver, web: WebSender, traces: TraceStore,
               per_session: RateLimiter | None = None, per_ip: RateLimiter | None = None,
               hints: HintStore | None = None) -> FastAPI:
    app = FastAPI(title="OneBar", docs_url=None, redoc_url=None, openapi_url=None)
    per_session = per_session or RateLimiter(max_events=10, window_s=600)
    per_ip = per_ip or RateLimiter(max_events=30, window_s=600)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.post("/api/message")
    async def post_message(body: Message, request: Request) -> dict:
        if not SESSION_RX.fullmatch(body.session):
            raise HTTPException(422, "bad session id")
        if len(body.text) > MAX_LEN:
            raise HTTPException(413, f"message over {MAX_LEN} characters")
        ip = request.client.host if request.client else "unknown"
        if not per_ip.allow(ip) or not per_session.allow(body.session):
            raise HTTPException(429, "too many messages; wait a few minutes")
        message_id = uuid.uuid4().hex
        sender = f"web:{body.session}"
        if hints is not None and body.hint is not None and len(json.dumps(body.hint)) <= MAX_HINT_BYTES:
            hints.save(workflow_id(sender), body.hint)  # a hint that fails its checks is dropped; the message still goes
        try:
            await deliver(sender, Inbound(id=message_id, text=body.text, channel="web",
                                                         ts=datetime.now(timezone.utc).isoformat()))
        except Exception:
            raise HTTPException(503, "could not reach the service; try again") from None
        return {"id": message_id}

    @app.get("/api/reply/{message_id}")
    async def get_reply(message_id: str) -> dict:
        if not ID_RX.fullmatch(message_id):
            raise HTTPException(404, "unknown message")
        got = web.get(message_id)
        if got is None:
            return {"status": "pending"}
        tid = traces.trace_id(message_id)
        return {"status": "done", "text": got["text"], "trace_id": tid if traces.load(tid) else None}

    @app.get("/api/trace/{trace_id}")
    async def get_trace(trace_id: str) -> dict:
        trace = traces.load(trace_id)
        if trace is None:
            raise HTTPException(404, "unknown trace")
        return trace

    return app
