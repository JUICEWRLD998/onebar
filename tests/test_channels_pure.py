from datetime import datetime
from email.message import EmailMessage

import pytest

from onebar import pipeline
from onebar.channels import mailparse as M
from onebar.channels.ratelimit import RateLimiter
from onebar.channels.traces import TraceStore, make_trace
from onebar.facts.engine import compute_facts
from conftest import set_hour, synth

OWN = "owner@gmail.com"


def mail(body="storm before 3?", frm="Sam <sam@example.org>", subject="Hi", msg_id="<abc@mx>", **hdr) -> bytes:
    m = EmailMessage()
    if msg_id:
        m["Message-ID"] = msg_id
    m["From"], m["To"], m["Subject"] = frm, "owner+onebar@gmail.com", subject
    for k, v in hdr.items():
        m[k.replace("_", "-")] = v
    m.set_content(body)
    return m.as_bytes()


def test_plain_question_is_parsed():
    e = M.parse_email(mail(), OWN)
    assert (e.msg_id, e.sender, e.text) == ("abc@mx", "sam@example.org", "storm before 3?")


def test_quoted_history_and_signature_are_stripped():
    body = "wind at the top?\n\nThanks\n-- \nSam\nsent from nowhere\n\nOn Tue, 9 Oct 2026, OneBar wrote:\n> old reply"
    assert M.parse_email(mail(body), OWN).text == "wind at the top? Thanks"


@pytest.mark.parametrize("tail", [
    "On Tue, Oct 9, 2026 at 10:20 AM OneBar <owner+onebar@gmail.com>\nwrote:\n> hi",
    "-----Original Message-----\nFrom: OneBar\nSent: Tuesday",
    "Sent from my iPhone\n\nsomething after",
    "> quoted line only\n> another",
])
def test_other_clients_boilerplate_is_cut(tail):
    assert M.parse_email(mail("rain today?\n" + tail), OWN).text == "rain today?"


def test_html_only_mail_is_reduced_to_text():
    m = EmailMessage()
    m["Message-ID"], m["From"], m["Subject"] = "<h@mx>", "a@b.co", "x"
    m.set_content("<p>how <b>cold</b> will it get?</p><br>-- <br>sig", subtype="html")
    assert M.parse_email(m.as_bytes(), OWN).text.startswith("how cold will it get?")


def test_empty_body_falls_back_to_the_subject_without_re_prefixes():
    assert M.parse_email(mail("", subject="Re: Fwd: sunset time?"), OWN).text == "sunset time?"


def test_long_text_is_cut_to_the_message_limit():
    assert len(M.parse_email(mail("x" * 2000), OWN).text) == 500


@pytest.mark.parametrize("kw, reason", [
    (dict(msg_id=None), "no_message_id"),
    (dict(frm="noreply@shop.com"), "automated"),
    (dict(frm="MAILER-DAEMON@mx.google.com"), "automated"),
    (dict(frm="Postmaster <postmaster@x.org>"), "automated"),
    (dict(Auto_Submitted="auto-replied"), "automated"),
    (dict(Precedence="bulk"), "automated"),
    (dict(List_Id="<news.example.org>"), "automated"),
    (dict(List_Unsubscribe="<mailto:u@x.org>"), "automated"),
    (dict(X_OneBar="reply"), "automated"),  # our own replies can never loop
    (dict(frm="owner@gmail.com"), "own_address"),
    (dict(frm="OWNER@GMAIL.COM"), "own_address"),
    (dict(body="", subject=""), "empty"),
])
def test_mail_that_must_not_get_a_reply_is_ignored_with_a_reason(kw, reason):
    with pytest.raises(M.Ignored) as ei:
        M.parse_email(mail(**kw), OWN)
    assert ei.value.reason == reason


def test_the_owner_may_test_with_allow_self():
    assert M.parse_email(mail(frm="owner@gmail.com"), OWN, allow_self=True).sender == "owner@gmail.com"


def test_auto_submitted_no_is_a_normal_mail():
    assert M.parse_email(mail(Auto_Submitted="no"), OWN).text == "storm before 3?"


def test_a_person_named_like_a_bot_word_is_not_over_matched():
    assert M.parse_email(mail(frm="bouncer.sam@example.org"), OWN).sender == "bouncer.sam@example.org"


# ---- rate limit ----------------------------------------------------------------------------------------------

def test_rate_limiter_allows_up_to_the_cap_then_refuses_then_recovers():
    t = [0.0]
    rl = RateLimiter(max_events=3, window_s=60, clock=lambda: t[0])
    assert [rl.allow("a") for _ in range(4)] == [True, True, True, False]
    assert rl.allow("b") is True  # keys are independent
    t[0] = 59.0
    assert rl.allow("a") is False
    t[0] = 61.0
    assert rl.allow("a") is True


# ---- traces --------------------------------------------------------------------------------------------------

def reply(fc=None):
    q = "storm before 3?"
    facts = compute_facts(fc or synth(), datetime(2026, 10, 8, 10, 20), question=q)
    return q, pipeline.answer_from_facts(q, facts, None)


def test_trace_roundtrip_and_no_sender_data(tmp_path):
    q, r = reply()
    store = TraceStore(tmp_path)
    tid = store.save("msg-1", make_trace(q, r))
    got = store.load(tid)
    assert got["reply"] == r.text and got["path"] == "template" and got["question"] == q
    assert got["attempts"][-1]["source"] == "template"
    assert "sam@example.org" not in (tmp_path / f"{tid}.json").read_text(encoding="utf-8")


def test_trace_ids_are_stable_and_safe(tmp_path):
    store = TraceStore(tmp_path)
    assert store.trace_id("m") == store.trace_id("m") != store.trace_id("n") and len(store.trace_id("m")) == 32
    for bad in ["../../etc/passwd", "a" * 31, "g" * 33, "", "x/../y", "A" * 32 + "!"]:
        assert store.load(bad) is None
    assert store.load("a" * 32) is None  # well-formed but unknown


def test_numbers_in_a_trace_carry_their_source_fact_and_hour():
    q, r = reply(set_hour(synth(), "2026-10-08T14:00", weather_code=95))
    tr = make_trace(q, r)
    storm = [n for n in tr["numbers"] if n["text"] == "14:00"]
    assert storm and storm[0]["ok"] and ["storm_first", "2026-10-08T14:00"] in storm[0]["sources"]
