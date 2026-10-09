"""One place that decides where every channel keeps its files and how the real sender is assembled."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from onebar.channels.email_io import EmailSender, SeenSet, ThreadStore
from onebar.channels.outbox import OutboxSender
from onebar.channels.router import RouterSender
from onebar.channels.traces import TraceStore
from onebar.channels.web_api import WebSender
from onebar.env import ROOT


@dataclass
class Stores:
    traces: TraceStore
    web: WebSender
    threads: ThreadStore
    seen: SeenSet
    email_log: OutboxSender
    outbox: OutboxSender


def stores(data_dir: Path | None = None) -> Stores:
    d = data_dir or ROOT / "data"
    return Stores(
        traces=TraceStore(d / "traces"),
        web=WebSender(d / "web_replies"),
        threads=ThreadStore(d / "email_threads.json"),
        seen=SeenSet(d / "email_seen.json"),
        email_log=OutboxSender(d / "email_sent.jsonl"),
        outbox=OutboxSender(d / "outbox.jsonl"),
    )


def build_sender(st: Stores) -> RouterSender:
    """Email is enabled only when IMAP_USER and IMAP_APP_PASSWORD are set; otherwise mail goes to the local outbox."""
    email = None
    user, password = os.environ.get("IMAP_USER", ""), os.environ.get("IMAP_APP_PASSWORD", "")
    if user and password:
        email = EmailSender(user, password, st.email_log, st.threads, traces=st.traces,
                            public_url=os.environ.get("ONEBAR_PUBLIC_URL") or None)
    return RouterSender(email=email, web=st.web, fallback=st.outbox)
