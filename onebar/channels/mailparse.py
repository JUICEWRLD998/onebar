"""Inbound email -> the hiker's question, or a reason to ignore the mail. Pure: bytes in, data out.

The inbox is a real person's, so the rules lean toward silence: automated mail, mailing lists, bounces, our own
replies and anything without a stable Message-ID are never answered.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from html.parser import HTMLParser

from onebar.commands import MAX_LEN

MARKER = "X-OneBar"
_BOT = re.compile(r"(?:^|[._+-])(?:no-?reply|do-?not-?reply|mailer-daemon|postmaster|bounces?|notifications?)(?:$|[._+-])", re.I)
_QUOTE_START = [
    re.compile(r"^On .{0,200}wrote:\s*$", re.I),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.I),
    re.compile(r"^-{2,}\s*Forwarded message\s*-{2,}", re.I),
    re.compile(r"^From:\s.+", re.I),
    re.compile(r"^-- ?$"),
    re.compile(r"^Sent from my ", re.I),
    re.compile(r"^Get Outlook for ", re.I),
]


@dataclass(frozen=True)
class InboundEmail:
    msg_id: str
    sender: str  # lower-case address
    subject: str
    text: str  # the new text only, at most MAX_LEN characters


class Ignored(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _Strip(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out: list[str] = []

    def handle_data(self, data):
        self.out.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li", "tr"):
            self.out.append("\n")


def _html_to_text(html: str) -> str:
    p = _Strip()
    p.feed(html)
    return "".join(p.out)


def clean_body(text: str) -> str:
    """Only what the sender just wrote: quoted history, signatures and client boilerplate removed."""
    kept: list[str] = []
    lines = text.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        joined = (s + " " + lines[i + 1].strip()).strip() if i + 1 < len(lines) else s
        if any(rx.match(s) for rx in _QUOTE_START) or (s.startswith("On ") and _QUOTE_START[0].match(joined)):
            break
        if s.startswith(">"):
            continue
        kept.append(s)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def _automated(msg: EmailMessage) -> bool:
    auto = (msg.get("Auto-Submitted") or "no").strip().lower()
    if auto != "no":
        return True
    if (msg.get("Precedence") or "").strip().lower() in {"bulk", "list", "junk", "auto_reply"}:
        return True
    if msg.get("List-Id") or msg.get("List-Unsubscribe") or msg.get(MARKER):
        return True
    if msg.get_content_type() == "multipart/report":
        return True
    return False


def parse_email(raw: bytes, own_address: str, allow_self: bool = False) -> InboundEmail:
    """Raises Ignored(reason) for mail that must not get a reply."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    msg_id = (msg.get("Message-ID") or "").strip().strip("<>").strip()
    if not msg_id:
        raise Ignored("no_message_id")
    sender = parseaddr(str(msg.get("From") or ""))[1].lower()
    if not sender or "@" not in sender:
        raise Ignored("no_sender")
    if _automated(msg) or _BOT.search(sender.split("@")[0]):
        raise Ignored("automated")
    if sender == own_address.lower() and not allow_self:
        raise Ignored("own_address")
    subject = re.sub(r"^(?:\s*(?:re|fwd?)\s*:\s*)+", "", str(msg.get("Subject") or ""), flags=re.I).strip()
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if body_part is not None:
        content = body_part.get_content()
        body = clean_body(_html_to_text(content) if body_part.get_content_type() == "text/html" else content)
    text = (body or subject)[:MAX_LEN]
    if not text:
        raise Ignored("empty")
    return InboundEmail(msg_id=msg_id, sender=sender, subject=subject, text=text)
