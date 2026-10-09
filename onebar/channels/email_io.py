"""The email channel: a read-only IMAP poller for one alias, and an SMTP sender that replies in thread.

Safety for a real person's inbox:
- The poller opens the mailbox read-only and fetches with BODY.PEEK, so it never changes a flag or moves a mail.
- It only looks at mail addressed to the alias (owner+onebar@gmail.com), from the last few days.
- Automated mail, lists, bounces, our own replies and the owner's own address are skipped (see mailparse).
- Each mail is handled once: by IMAP uid and by Message-ID, remembered on disk.
- A sender is limited to a handful of messages per window.
"""
from __future__ import annotations

import imaplib
import json
import re
import smtplib
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Callable

from onebar.channels import mailparse
from onebar.channels.outbox import OutboxSender
from onebar.channels.ratelimit import RateLimiter
from onebar.channels.traces import TraceStore
from onebar.temporal.models import Inbound

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
EMAIL_RX = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MAX_PER_CYCLE = 20
LOOKBACK_DAYS = 3
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def alias_for(user: str) -> str:
    """owner@gmail.com -> owner+onebar@gmail.com (Gmail delivers it to the owner's inbox)."""
    local, _, domain = user.partition("@")
    return f"{local.split('+')[0]}+onebar@{domain}"


def imap_date(d: datetime) -> str:
    """IMAP wants 09-Oct-2026 with an English month, whatever the machine's locale is."""
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


class _Atomic:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _write(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.path)


class SeenSet(_Atomic):
    def _read(self) -> set[str]:
        try:
            return set(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return set()

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._read()

    def add(self, key: str) -> None:
        with self._lock:
            s = self._read()
            s.add(key)
            self._write(json.dumps(sorted(s)))


class ThreadStore(_Atomic):
    """message id -> original subject, so a reply can go out in the same thread."""

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def get(self, msg_id: str) -> str | None:
        with self._lock:
            return self._read().get(msg_id)

    def set(self, msg_id: str, subject: str) -> None:
        with self._lock:
            d = self._read()
            d[msg_id] = subject
            self._write(json.dumps(d))


# ---- sending -------------------------------------------------------------------------------------------------

class EmailSender:
    """send(key, to, text) -> bool. A key is recorded only after SMTP accepts the mail, so a crash can repeat a
    message but never lose one: for an overdue alert, that is the right way round."""

    def __init__(self, user: str, password: str, log: OutboxSender, threads: ThreadStore,
                 traces: TraceStore | None = None, public_url: str | None = None,
                 smtp_factory: Callable[[], smtplib.SMTP] | None = None):
        self.user, self.password = user, password.replace(" ", "")
        self.log, self.threads, self.traces = log, threads, traces
        self.public_url = public_url.rstrip("/") if public_url else None
        self._smtp = smtp_factory or (lambda: smtplib.SMTP_SSL(SMTP_HOST, 465, timeout=30))

    def send(self, key: str, to: str, text: str) -> bool:
        if not EMAIL_RX.fullmatch(to) or self.log.has(key):
            return False
        msg = self._compose(key, to, text)
        with self._smtp() as smtp:
            smtp.login(self.user, self.password)
            smtp.send_message(msg)
        self.log.record(key, to, text)
        return True

    def _compose(self, key: str, to: str, text: str) -> EmailMessage:
        msg = EmailMessage()
        msg["From"], msg["To"] = f"OneBar <{self.user}>", to
        msg["Date"], msg["Message-ID"] = formatdate(localtime=False), make_msgid(domain=self.user.split("@")[-1])
        msg["Auto-Submitted"] = "auto-replied"  # receivers' autoresponders, and our own poller, must not answer this
        msg[mailparse.MARKER] = "alert" if key.startswith("alert:") else "reply"
        body = text
        if key.startswith("reply:"):
            mid = key[len("reply:"):]
            subject = self.threads.get(mid) or "your question"
            msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
            msg["In-Reply-To"] = msg["References"] = f"<{mid}>"
            if self.public_url and self.traces and self.traces.load(self.traces.trace_id(mid)):
                body += f"\n\nHow this was checked: {self.public_url}/trace/{self.traces.trace_id(mid)}"
        else:
            msg["Subject"] = "OneBar: a trip has not been checked out"
        msg.set_content(body)
        return msg


# ---- receiving -----------------------------------------------------------------------------------------------

class GmailImap:
    """Read-only view of one mailbox. Use as a context manager."""

    def __init__(self, user: str, password: str, host: str = IMAP_HOST, factory=imaplib.IMAP4_SSL):
        self.user, self.password, self.host, self._factory = user, password.replace(" ", ""), host, factory
        self.validity = "0"

    m = None

    @property
    def connected(self) -> bool:
        return self.m is not None

    def connect(self) -> None:
        self.m = self._factory(self.host)
        self.m.login(self.user, self.password)
        self.m.select("INBOX", readonly=True)  # read-only: nothing here can change the owner's mailbox
        _, data = self.m.response("UIDVALIDITY")
        self.validity = (data[0] or b"0").decode() if data else "0"

    def refresh(self) -> None:
        """Keep a long-lived connection current: NOOP makes the server report mail that arrived since the last pass."""
        self.m.noop()

    def close(self) -> None:
        m, self.m = self.m, None
        try:
            if m is not None:
                m.logout()
        except Exception:
            pass

    def __enter__(self) -> "GmailImap":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def search(self, alias: str, since: datetime) -> list[str]:
        _, data = self.m.uid("SEARCH", None, "TO", f'"{alias}"', "SINCE", imap_date(since))
        return [u.decode() for u in (data[0] or b"").split()]

    def fetch(self, uid: str) -> bytes:
        _, data = self.m.uid("FETCH", uid, "(BODY.PEEK[])")
        return data[0][1]


def poll_once(imap, *, alias: str, own: str, seen: SeenSet, threads: ThreadStore, limiter: RateLimiter,
              handoff: Callable[[str, Inbound], None], allow_self: bool = False,
              now: datetime | None = None) -> Counter:
    """One pass. `handoff(sender, inbound)` raises on failure; that mail is then retried on the next pass."""
    now = now or datetime.now(timezone.utc)
    counts: Counter = Counter()
    handled = 0
    for uid in imap.search(alias, now - timedelta(days=LOOKBACK_DAYS)):
        ukey = f"uid:{imap.validity}:{uid}"
        if seen.has(ukey):
            continue
        if handled >= MAX_PER_CYCLE:
            counts["deferred"] += 1
            continue
        handled += 1
        try:
            mail = mailparse.parse_email(imap.fetch(uid), own, allow_self)
        except mailparse.Ignored as e:
            counts[f"ignored:{e.reason}"] += 1
            seen.add(ukey)
            continue
        if seen.has(mail.msg_id):
            counts["duplicate"] += 1
            seen.add(ukey)
            continue
        if not limiter.allow(mail.sender):
            counts["rate_limited"] += 1
            seen.add(ukey)
            continue
        threads.set(mail.msg_id, mail.subject)
        handoff(mail.sender, Inbound(id=mail.msg_id, text=mail.text, channel="email", ts=now.isoformat()))
        seen.add(mail.msg_id)
        seen.add(ukey)
        counts["delivered"] += 1
    return counts
