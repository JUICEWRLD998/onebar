from datetime import datetime, timezone
from email.message import EmailMessage

import pytest

from onebar.channels import email_io as E
from onebar.channels import mailparse
from onebar.channels.outbox import OutboxSender
from onebar.channels.ratelimit import RateLimiter
from onebar.channels.traces import TraceStore
from onebar.temporal.models import Inbound

OWN = "owner@gmail.com"
ALIAS = "owner+onebar@gmail.com"
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def raw(msg_id="m1", frm="sam@example.org", body="storm before 3?", subject="Question", **hdr) -> bytes:
    m = EmailMessage()
    m["Message-ID"], m["From"], m["To"], m["Subject"] = f"<{msg_id}>", frm, ALIAS, subject
    for k, v in hdr.items():
        m[k.replace("_", "-")] = v
    m.set_content(body)
    return m.as_bytes()


class FakeImap:
    validity = "77"

    def __init__(self, mails: dict[str, bytes]):
        self.mails, self.searched, self.fetched = mails, [], []

    def search(self, alias, since):
        self.searched.append((alias, since))
        return list(self.mails)

    def fetch(self, uid):
        self.fetched.append(uid)
        return self.mails[uid]


class Env:
    def __init__(self, tmp_path, max_events=10):
        self.seen = E.SeenSet(tmp_path / "seen.json")
        self.threads = E.ThreadStore(tmp_path / "threads.json")
        self.limiter = RateLimiter(max_events=max_events, window_s=600, clock=lambda: 0.0)
        self.delivered: list[tuple[str, Inbound]] = []

    def poll(self, imap, **kw):
        return E.poll_once(imap, alias=ALIAS, own=OWN, seen=self.seen, threads=self.threads, limiter=self.limiter,
                           handoff=lambda s, m: self.delivered.append((s, m)), now=NOW, **kw)


def test_a_normal_mail_is_delivered_once_and_remembered(tmp_path):
    env, imap = Env(tmp_path), FakeImap({"1": raw()})
    assert env.poll(imap)["delivered"] == 1
    sender, msg = env.delivered[0]
    assert sender == "sam@example.org" and msg.id == "m1" and msg.text == "storm before 3?" and msg.channel == "email"
    assert env.threads.get("m1") == "Question"
    assert env.poll(imap)["delivered"] == 0 and len(env.delivered) == 1
    assert imap.fetched == ["1"]  # the second pass did not even download it again


def test_search_is_limited_to_the_alias_and_recent_days(tmp_path):
    env, imap = Env(tmp_path), FakeImap({})
    env.poll(imap)
    alias, since = imap.searched[0]
    assert alias == ALIAS and (NOW - since).days == E.LOOKBACK_DAYS


@pytest.mark.parametrize("kw, key", [
    (dict(frm="noreply@x.com"), "ignored:automated"),
    (dict(Auto_Submitted="auto-replied"), "ignored:automated"),
    (dict(frm=OWN), "ignored:own_address"),
    (dict(body="", subject=""), "ignored:empty"),
])
def test_mail_that_must_stay_unanswered_is_counted_and_never_delivered(tmp_path, kw, key):
    env = Env(tmp_path)
    counts = env.poll(FakeImap({"1": raw(**kw)}))
    assert counts[key] == 1 and env.delivered == []
    assert env.poll(FakeImap({"1": raw(**kw)}))[key] == 0  # remembered, not reprocessed


def test_the_owner_can_test_with_allow_self(tmp_path):
    env = Env(tmp_path)
    assert env.poll(FakeImap({"1": raw(frm=OWN)}), allow_self=True)["delivered"] == 1


def test_same_message_id_under_another_uid_is_a_duplicate(tmp_path):
    env = Env(tmp_path)
    env.poll(FakeImap({"1": raw()}))
    counts = env.poll(FakeImap({"2": raw()}))
    assert counts["duplicate"] == 1 and len(env.delivered) == 1


def test_a_chatty_sender_is_rate_limited_in_silence(tmp_path):
    env = Env(tmp_path, max_events=2)
    mails = {str(i): raw(msg_id=f"m{i}") for i in range(5)}
    counts = env.poll(FakeImap(mails))
    assert counts["delivered"] == 2 and counts["rate_limited"] == 3


def test_a_failed_handoff_leaves_the_mail_to_be_retried(tmp_path):
    env, imap = Env(tmp_path), FakeImap({"1": raw()})
    state = {"fail": True}

    def handoff(s, m):
        if state["fail"]:
            raise ConnectionError("temporal down")
        env.delivered.append((s, m))

    kw = dict(alias=ALIAS, own=OWN, seen=env.seen, threads=env.threads, limiter=env.limiter, handoff=handoff, now=NOW)
    with pytest.raises(ConnectionError):
        E.poll_once(imap, **kw)
    state["fail"] = False
    assert E.poll_once(imap, **kw)["delivered"] == 1 and len(env.delivered) == 1


def test_a_cycle_handles_at_most_the_cap_and_the_rest_waits(tmp_path):
    env = Env(tmp_path, max_events=100)
    mails = {str(i): raw(msg_id=f"m{i}", frm=f"p{i}@example.org") for i in range(E.MAX_PER_CYCLE + 5)}
    counts = env.poll(FakeImap(mails))
    assert counts["delivered"] == E.MAX_PER_CYCLE and counts["deferred"] == 5
    assert env.poll(FakeImap(mails))["delivered"] == 5


def test_alias_and_imap_date_helpers():
    assert E.alias_for("Owner@gmail.com") == "Owner+onebar@gmail.com"
    assert E.alias_for("a+tag@gmail.com") == "a+onebar@gmail.com"
    assert E.imap_date(datetime(2026, 3, 5)) == "05-Mar-2026" and E.imap_date(datetime(2026, 12, 31)) == "31-Dec-2026"


# ---- GmailImap: read-only by construction ----------------------------------------------------------------------

class FakeM:
    def __init__(self, host):
        self.calls = []

    def login(self, u, p):
        self.calls.append(("login", u, p))

    def select(self, box, readonly=False):
        self.calls.append(("select", box, readonly))

    def response(self, name):
        return name, [b"4242"]

    def uid(self, *args):
        self.calls.append(("uid",) + args)
        if args[0] == "SEARCH":
            return "OK", [b"5 6"]
        return "OK", [(b"hdr", b"RAW"), b")"]

    def logout(self):
        self.calls.append(("logout",))

    def noop(self):
        self.calls.append(("noop",))


def test_gmail_imap_opens_read_only_and_peeks():
    made = []

    def factory(host):
        made.append(FakeM(host))
        return made[0]

    with E.GmailImap("o@gmail.com", "abcd efgh", factory=factory) as imap:
        assert imap.validity == "4242"
        assert imap.search(ALIAS, NOW) == ["5", "6"]
        assert imap.fetch("5") == b"RAW"
    calls = made[0].calls
    assert ("login", "o@gmail.com", "abcdefgh") in calls  # app password spaces removed
    assert ("select", "INBOX", True) in calls
    search = next(c for c in calls if c[:2] == ("uid", "SEARCH"))
    assert search[3:] == ("TO", f'"{ALIAS}"', "SINCE", "09-Oct-2026")
    fetch = next(c for c in calls if c[:2] == ("uid", "FETCH"))
    assert fetch[3] == "(BODY.PEEK[])"  # never plain BODY[], which would set \Seen
    assert calls[-1] == ("logout",)
    assert not any(c[0] in ("store", "copy", "expunge") for c in calls)


def test_a_long_lived_connection_refreshes_with_noop_and_reconnects_after_close():
    made = []

    def factory(host):
        made.append(FakeM(host))
        return made[-1]

    imap = E.GmailImap("o@gmail.com", "pw", factory=factory)
    assert not imap.connected
    imap.connect()
    imap.refresh()
    imap.refresh()
    assert imap.connected and len(made) == 1 and made[0].calls.count(("noop",)) == 2
    imap.close()
    imap.close()  # closing twice is harmless
    assert not imap.connected and made[0].calls.count(("logout",)) == 1
    imap.connect()
    assert len(made) == 2  # a fresh connection after close


def test_close_survives_a_dead_connection():
    class Dead(FakeM):
        def logout(self):
            raise OSError("already gone")

    imap = E.GmailImap("o@gmail.com", "pw", factory=lambda h: Dead(h))
    imap.connect()
    imap.close()
    assert not imap.connected


# ---- EmailSender ---------------------------------------------------------------------------------------------

class FakeSmtp:
    def __init__(self, sent, fail=False):
        self.sent, self.fail, self.logged_in = sent, fail, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, u, p):
        self.logged_in = (u, p)

    def send_message(self, msg):
        if self.fail:
            raise OSError("smtp down")
        self.sent.append(msg)


def sender(tmp_path, fail=False, traces=None, url="https://onebar.example"):
    sent: list = []
    s = E.EmailSender("o@gmail.com", "abcd efgh", OutboxSender(tmp_path / "sent.jsonl"),
                      E.ThreadStore(tmp_path / "th.json"), traces=traces, public_url=url,
                      smtp_factory=lambda: FakeSmtp(sent, fail))
    return s, sent


def test_reply_goes_out_in_thread_with_loop_proof_headers(tmp_path):
    s, sent = sender(tmp_path)
    s.threads.set("m1", "Question")
    assert s.send("reply:m1", "sam@example.org", "No storm. Gusts 40km/h.") is True
    m = sent[0]
    assert (m["To"], m["Subject"], m["In-Reply-To"], m["References"]) == ("sam@example.org", "Re: Question", "<m1>", "<m1>")
    assert m["Auto-Submitted"] == "auto-replied" and m[mailparse.MARKER] == "reply"
    assert m.get_content().strip() == "No storm. Gusts 40km/h."  # no trace yet, so no footer
    # our own reply can never be picked up by our own poller
    with pytest.raises(mailparse.Ignored):
        mailparse.parse_email(m.as_bytes(), OWN)


def test_footer_links_the_trace_only_when_the_trace_exists(tmp_path):
    traces = TraceStore(tmp_path / "tr")
    s, sent = sender(tmp_path, traces=traces)
    tid = traces.save("m1", {"reply": "x"})
    s.send("reply:m1", "sam@example.org", "Reply text.")
    body = sent[0].get_content()
    assert body.startswith("Reply text.") and body.rstrip().endswith(f"https://onebar.example/trace/{tid}")
    assert "sam@example.org" not in body
    s.threads.set("m2", "Re: already")
    s.send("reply:m2", "sam@example.org", "No trace for this one.")
    assert "How this was checked" not in sent[1].get_content()
    assert sent[1]["Subject"] == "Re: already"  # no double Re:


def test_alert_is_a_fresh_message_not_a_reply(tmp_path):
    s, sent = sender(tmp_path)
    s.send("alert:trip1", "friend@example.org", "OneBar: someone has not checked out.")
    m = sent[0]
    assert m["In-Reply-To"] is None and m[mailparse.MARKER] == "alert" and "not been checked out" in m["Subject"]


def test_a_key_is_sent_once_even_across_instances(tmp_path):
    s, sent = sender(tmp_path)
    assert s.send("reply:m1", "a@b.co", "t") is True
    assert s.send("reply:m1", "a@b.co", "t") is False
    s2, sent2 = sender(tmp_path)
    assert s2.send("reply:m1", "a@b.co", "t") is False and sent2 == []


def test_smtp_failure_raises_for_the_retry_and_records_nothing(tmp_path):
    s, _ = sender(tmp_path, fail=True)
    with pytest.raises(OSError):
        s.send("alert:t", "a@b.co", "t")
    assert not s.log.has("alert:t")  # the retry will really send it


def test_non_email_destinations_are_refused_not_sent(tmp_path):
    s, sent = sender(tmp_path)
    assert s.send("alert:t", "+447700900123", "t") is False and sent == []
