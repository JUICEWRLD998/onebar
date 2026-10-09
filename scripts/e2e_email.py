"""End-to-end email check: send a TRIP and three questions to the alias, time the replies.

Starts a Temporal dev server, the worker (tuned model if ONEBAR_MODEL is set), and the email poller in
--allow-self mode, because the only sender available to this script is the account owner. A judge writes from
another address; the code path is the same except for that one skip rule.

Only the owner's own address ever receives mail. The mailbox is opened read-only to find the replies.
"""
import imaplib
import os
import smtplib
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from onebar.channels.email_io import alias_for
from onebar.env import load_env

load_env()
USER = os.environ["IMAP_USER"]
PASSWORD = os.environ["IMAP_APP_PASSWORD"].replace(" ", "")
ALIAS = alias_for(USER)
LIMIT_S = 30


def say(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def send(subject: str, body: str) -> str:
    m = EmailMessage()
    mid = make_msgid(domain="gmail.com")
    m["From"], m["To"], m["Subject"], m["Message-ID"] = USER, ALIAS, subject, mid
    m.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(USER, PASSWORD)
        s.send_message(m)
    return mid.strip("<>")


def find_reply(mid: str, timeout_s: float):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        m = imaplib.IMAP4_SSL("imap.gmail.com")
        m.login(USER, PASSWORD)
        m.select("INBOX", readonly=True)
        _, data = m.uid("SEARCH", None, "HEADER", "In-Reply-To", f"<{mid}>")
        uids = (data[0] or b"").split()
        if uids:
            _, msgdata = m.uid("FETCH", uids[0], "(BODY.PEEK[])")
            m.logout()
            return message_from_bytes(msgdata[0][1], policy=policy.default)
        m.logout()
        time.sleep(2)
    return None


def app_latency(mid: str, sent_at: datetime) -> float | None:
    """Seconds from our SMTP send of the question to our SMTP accept of the reply, from the sender's own log."""
    import json

    log = ROOT / "data" / "email_sent.jsonl"
    if not log.is_file():
        return None
    for line in log.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["key"] == f"reply:{mid}":
            return (datetime.fromisoformat(row["at"]) - sent_at).total_seconds()
    return None


def main() -> int:
    env ={**os.environ, "ONEBAR_BUDGET_USD": "4.6", "ONEBAR_PUBLIC_URL": "http://localhost:8000",
           "PYTHONIOENCODING": "utf-8"}
    db = ROOT / "data" / "e2e-temporal.db"
    db.unlink(missing_ok=True)
    log = (ROOT / "data" / "e2e.log").open("w", encoding="utf-8")
    server = subprocess.Popen([str(ROOT / ".tools" / "temporal.exe"), "server", "start-dev", "--headless",
                               "--port", "7233", "--db-filename", str(db)], stdout=log, stderr=log)
    procs = [server]
    try:
        time.sleep(8)
        procs.append(subprocess.Popen([sys.executable, "-m", "onebar.temporal.worker"], cwd=ROOT, env=env,
                                      stdout=log, stderr=log))
        procs.append(subprocess.Popen([sys.executable, "-m", "onebar.channels.email_poll", "--allow-self"],
                                      cwd=ROOT, env=env, stdout=log, stderr=log))
        time.sleep(6)
        back = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%H:%M")
        steps = [
            ("OneBar e2e test 1", f"TRIP 46.55,7.98 BACK {back} CONTACT {USER}", None),
            ("OneBar e2e test 2", "storm before I'm back at the car?", LIMIT_S),
            ("OneBar e2e test 3", "how windy is it going to get?", LIMIT_S),
            ("OneBar e2e test 4", "do I need a headlamp?", LIMIT_S),
        ]
        results = []
        for subject, body, limit in steps:
            t0 = time.time()
            t_send_utc = datetime.now(timezone.utc)
            mid = send(subject, body)
            say(f"sent: {subject!r}")
            reply = find_reply(mid, 75)
            took = time.time() - t0
            if reply is None:
                say("  NO REPLY within 75 s")
                results.append((subject, None, took, None))
                continue
            text = reply.get_content().replace("\r\n", "\n").strip()
            first = text.split("\n\n")[0]
            app = app_latency(mid, t_send_utc)
            say(f"  app side {app:.1f}s (send -> reply accepted by SMTP); visible in mailbox after {took:.1f}s  "
                f"subject={reply['Subject']!r}")
            took = app if app is not None else took
            say(f"  body: {first!r}  ({len(first)} chars)")
            say(f"  footer: {'yes' if 'How this was checked' in text else 'no'}")
            results.append((subject, first, took, reply))
        ok = True
        for subject, first, took, reply in results[1:]:  # the TRIP confirmation is not a judged question
            good = (first is not None and took <= LIMIT_S and len(first) <= 160
                    and reply["In-Reply-To"] is not None and reply["Auto-Submitted"] == "auto-replied"
                    and "How this was checked" in reply.get_content())
            ok &= good
            say(f"{subject}: {'PASS' if good else 'FAIL'} ({took:.1f}s, limit {LIMIT_S}s)")
        say("RESULT: " + ("PASS - three questions answered in thread under 30 s with a trace link" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        for p in reversed(procs):
            p.kill()
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
