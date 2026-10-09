"""TripWorkflow on Temporal's time-skipping test server. The server binary is downloaded on first use."""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from onebar.channels.outbox import OutboxSender
from onebar.channels.traces import TraceStore
from onebar.check.gsm7 import LIMIT, analyze
from onebar.facts.open_meteo import ForecastError
from onebar.temporal.activities import Activities, Deps
from onebar.temporal.models import TASK_QUEUE, Inbound
from onebar.temporal.starter import deliver, workflow_id
from onebar.temporal.workflows import TripWorkflow
from conftest import synth

temporalio_testing = pytest.importorskip("temporalio.testing")
from temporalio.worker import Worker  # noqa: E402

SENDER = "Sam@Example.org"
CONTACT = "friend@example.org"
GEOCODE = {"results": [{"name": "Zermatt", "latitude": 46.02, "longitude": 7.75, "country": "Switzerland"}]}


def forecast(now: datetime, offset_s: int = 0) -> dict:
    fc = synth(start=(now - timedelta(days=1)).strftime("%Y-%m-%d"), days=5)
    fc["utc_offset_seconds"] = offset_s
    return fc


def inbound(text: str, mid: str | None = None, ts: datetime | None = None) -> Inbound:
    ts = ts or datetime.now(timezone.utc)
    return Inbound(id=mid or uuid.uuid4().hex, text=text, channel="test", ts=ts.isoformat())


class Harness:
    def __init__(self, tmp_path: Path, **deps):
        self.now = datetime.now(timezone.utc)
        self.box = OutboxSender(tmp_path / "outbox.jsonl")
        self.offset_s = deps.pop("offset_s", 0)
        self.traces = TraceStore(tmp_path / "traces")
        self.deps = Deps(sender=deps.pop("sender", self.box),
                         get_forecast=deps.pop("get_forecast", lambda url: forecast(self.now, self.offset_s)),
                         get_geocode=deps.pop("get_geocode", lambda url: GEOCODE), grace_min=30,
                         traces=self.traces, **deps)

    def local_hour(self) -> str:
        return (self.now + timedelta(seconds=self.offset_s)).strftime("%H")

    def trace(self, msg_id: str) -> dict:
        return self.traces.load(self.traces.trace_id(msg_id))

    def back_text(self, hours: float) -> str:
        return (self.now + timedelta(hours=hours)).strftime("%H:%M")

    def rows(self, prefix: str) -> list[dict]:
        return [r for r in self.box.sent() if r["key"].startswith(prefix)]


def run_with(h: Harness, scenario):
    """Start a time-skipping server and a worker, run `scenario(env, h)`, tear everything down."""

    async def go():
        try:
            env = await temporalio_testing.WorkflowEnvironment.start_time_skipping()
        except Exception as exc:  # no network to fetch the test server binary
            pytest.skip(f"time-skipping test server unavailable: {exc}")
        async with env:
            with ThreadPoolExecutor(4) as pool:
                async with Worker(env.client, task_queue=TASK_QUEUE, workflows=[TripWorkflow],
                                  activities=Activities(h.deps).all(), activity_executor=pool):
                    return await scenario(env, h)

    return asyncio.run(go())


async def status(env, sender=SENDER):
    return await env.client.get_workflow_handle(workflow_id(sender)).query(TripWorkflow.status)


def trip_msg(h, hours=2, mid="trip1", contact=CONTACT):
    return inbound(f"TRIP 46.55,7.98 BACK {h.back_text(hours)} CONTACT {contact}", mid, h.now)


# ---- the three required behaviours -----------------------------------------------------------------------------

def test_overdue_trip_sends_exactly_one_alert(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, trip_msg(h))
        await env.sleep(timedelta(hours=1))
        assert (await status(env))["trip"]["alerted"] is False  # still before return + grace
        await env.sleep(timedelta(hours=2))  # now past return (2h) + grace (30m)
        assert (await status(env))["trip"]["alerted"] is True
        await env.sleep(timedelta(days=3))  # nothing else may fire

    run_with(h, scenario)
    alerts = h.rows("alert:")
    assert len(alerts) == 1 and alerts[0]["to"] == CONTACT
    assert "not a rescue service" in alerts[0]["text"] and "46.550, 7.980" in alerts[0]["text"]
    assert len(h.rows("reply:")) == 1  # the trip-saved reply, nothing else


def test_out_before_the_deadline_cancels_the_alert(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, trip_msg(h))
        await env.sleep(timedelta(hours=1))
        await deliver(env.client, SENDER, inbound("OUT", "out1", h.now + timedelta(hours=1)))
        await env.sleep(timedelta(days=2))
        assert (await status(env))["trip"] is None

    run_with(h, scenario)
    assert h.rows("alert:") == []
    assert [r["text"] for r in h.rows("reply:out1")] == ["Checked out. Trip ended. Glad you are safe."]


def test_the_same_message_id_signalled_twice_gets_one_reply(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, trip_msg(h))
        q = inbound("storm before 3?", "q1", h.now)
        await deliver(env.client, SENDER, q)
        await deliver(env.client, SENDER, q)  # redelivery
        await deliver(env.client, SENDER, trip_msg(h))  # even the trip message redelivered
        await env.sleep(timedelta(minutes=5))
        assert (await status(env))["processed"] == 2

    run_with(h, scenario)
    assert len(h.rows("reply:q1")) == 1
    assert len(h.rows("reply:trip1")) == 1


# ---- the rest of the behaviour ---------------------------------------------------------------------------------

def test_a_question_is_answered_from_the_forecast_and_fits_one_sms(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, trip_msg(h))
        await deliver(env.client, SENDER, inbound("how windy is it going to get?", "q1", h.now))
        await env.sleep(timedelta(minutes=5))

    run_with(h, scenario)
    text = h.rows("reply:q1")[0]["text"]
    a = analyze(text)
    assert "km/h" in text and not a.bad_chars and a.septets <= LIMIT, text


def test_question_without_a_trip_asks_for_one(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, inbound("storm?", "q1", h.now))
        await env.sleep(timedelta(minutes=5))

    run_with(h, scenario)
    assert h.rows("reply:q1")[0]["text"].startswith("No place yet")


def test_place_name_is_geocoded(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, inbound(f"TRIP Zermatt BACK {h.back_text(3)} CONTACT {CONTACT}", "t1", h.now))
        await env.sleep(timedelta(minutes=1))
        assert (await status(env))["trip"]["place"] == "Zermatt, Switzerland"

    run_with(h, scenario)


def test_unknown_place_is_refused_and_no_trip_is_stored(tmp_path):
    h = Harness(tmp_path, get_geocode=lambda url: {})

    async def scenario(env, h):
        await deliver(env.client, SENDER, inbound(f"TRIP Nowhereville BACK {h.back_text(3)} CONTACT {CONTACT}", "t2", h.now))
        await env.sleep(timedelta(minutes=1))
        assert (await status(env))["trip"] is None

    run_with(h, scenario)
    assert "Could not find that place" in h.rows("reply:t2")[0]["text"]


def test_malformed_trip_and_help_get_replies(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, inbound("TRIP Matterhorn", "bad1", h.now))
        await deliver(env.client, SENDER, inbound("help", "help1", h.now))
        await env.sleep(timedelta(minutes=1))

    run_with(h, scenario)
    assert h.rows("reply:bad1")[0]["text"].startswith("Use: TRIP")
    assert h.rows("reply:help1")[0]["text"].startswith("OneBar:")


def test_forget_ends_the_workflow_and_wipes_state(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, trip_msg(h))
        await deliver(env.client, SENDER, inbound("FORGET", "f1", h.now))
        result = await env.client.get_workflow_handle(workflow_id(SENDER)).result()
        assert result == "forgotten"
        # a new message starts a fresh workflow with no trip
        await deliver(env.client, SENDER, inbound("storm?", "q9", h.now))
        await env.sleep(timedelta(minutes=1))
        assert (await status(env))["trip"] is None

    run_with(h, scenario)
    assert h.rows("reply:f1")[0]["text"].startswith("Done.")
    assert h.rows("reply:q9")[0]["text"].startswith("No place yet")
    assert h.rows("alert:") == []  # the forgotten trip never alerts


def test_forecast_outage_gives_a_clear_reply_after_retries(tmp_path):
    state = {"down": False}

    def get(url):
        if state["down"]:
            raise ForecastError("down")
        return forecast(h.now)

    h = Harness(tmp_path, get_forecast=get, cache_ttl_s=0)  # cache off, so the outage is really seen

    async def scenario(env, h):
        await deliver(env.client, SENDER, trip_msg(h))
        await env.sleep(timedelta(minutes=1))
        state["down"] = True
        await deliver(env.client, SENDER, inbound("storm?", "q1", h.now))
        await env.sleep(timedelta(minutes=10))

    run_with(h, scenario)
    assert h.rows("reply:q1")[0]["text"].startswith("Forecast unavailable")


def test_a_flaky_sender_is_retried_and_the_alert_still_lands_once(tmp_path):
    class Flaky(OutboxSender):
        def __init__(self, path):
            super().__init__(path)
            self.fail = 3

        def send(self, key, to, text):
            if key.startswith("alert:") and self.fail > 0:
                self.fail -= 1
                raise OSError("smtp down")
            return super().send(key, to, text)

    box = Flaky(tmp_path / "outbox.jsonl")
    h = Harness(tmp_path, sender=box)
    h.box = box

    async def scenario(env, h):
        await deliver(env.client, SENDER, trip_msg(h))
        await env.sleep(timedelta(hours=4))
        assert (await status(env))["trip"]["alerted"] is True

    run_with(h, scenario)
    assert box.fail == 0 and len(h.rows("alert:")) == 1


def test_continue_as_new_keeps_the_trip_and_the_dedupe_set(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, trip_msg(h), can_after=3)
        for i in range(5):
            await deliver(env.client, SENDER, inbound("help", f"h{i}", h.now), can_after=3)
        await env.sleep(timedelta(minutes=5))
        await deliver(env.client, SENDER, inbound("help", "h0", h.now), can_after=3)  # old id, after a rollover
        await env.sleep(timedelta(minutes=5))
        assert (await status(env))["trip"] is not None
        await env.sleep(timedelta(hours=4))
        assert (await status(env))["trip"]["alerted"] is True  # the timer survived the rollover

    run_with(h, scenario)
    assert len(h.rows("reply:h")) == 5
    assert len(h.rows("alert:")) == 1


# ---- PLACE, local time without a trip, and the richer trace -------------------------------------------------------

def test_a_question_after_place_uses_that_places_local_time(tmp_path):
    h = Harness(tmp_path, offset_s=7200)

    async def scenario(env, h):
        await deliver(env.client, SENDER, inbound("PLACE 46.5, 7.9", "p1", h.now))
        await deliver(env.client, SENDER, inbound("how windy is it going to get?", "q1", h.now))
        await env.sleep(timedelta(minutes=5))
        st = await status(env)
        assert st["pos"] == [46.5, 7.9] and st["offset_s"] == 7200 and st["trip"] is None

    run_with(h, scenario)
    assert h.rows("reply:p1")[0]["text"].startswith("Place set: 46.500,7.900")
    hours = h.trace("q1")["hours"]
    assert len(hours) == 12 and hours[0]["t"][11:13] == h.local_hour()  # the hiker's clock, not UTC
    assert h.trace("q1")["place"] == {"lat": 46.5, "lon": 7.9}  # so the trace page can draw the terrain


def test_place_by_name_and_unknown_place(tmp_path):
    h = Harness(tmp_path)

    async def scenario(env, h):
        await deliver(env.client, SENDER, inbound("PLACE Zermatt", "p1", h.now))
        await env.sleep(timedelta(minutes=1))
        assert (await status(env))["pos"] == [46.02, 7.75]

    run_with(h, scenario)
    assert "Zermatt, Switzerland" in h.rows("reply:p1")[0]["text"]

    h2 = Harness(tmp_path / "b", get_geocode=lambda url: {})
    (tmp_path / "b").mkdir()

    async def scenario2(env, h):
        await deliver(env.client, SENDER, inbound("PLACE Nowhereville", "p2", h.now))
        await env.sleep(timedelta(minutes=1))
        assert (await status(env))["pos"] is None

    run_with(h2, scenario2)
    assert "Could not find that place" in h2.rows("reply:p2")[0]["text"]


def test_the_offset_survives_out_so_later_questions_keep_the_right_clock(tmp_path):
    h = Harness(tmp_path, offset_s=-7 * 3600)

    async def scenario(env, h):
        await deliver(env.client, SENDER, trip_msg(h))
        await deliver(env.client, SENDER, inbound("OUT", "o1", h.now))
        await deliver(env.client, SENDER, inbound("how windy is it going to get?", "q1", h.now))
        await env.sleep(timedelta(minutes=5))

    run_with(h, scenario)
    assert h.trace("q1")["hours"][0]["t"][11:13] == h.local_hour()


def test_trace_carries_the_baseline_draft_checked_by_the_same_checker(tmp_path):
    h = Harness(tmp_path, baseline_draft=lambda prompt: "Gusts 999km/h at 03:33, bring a jacket.")

    async def scenario(env, h):
        await deliver(env.client, SENDER, inbound("PLACE 46.5, 7.9", "p1", h.now))
        await deliver(env.client, SENDER, inbound("how windy is it going to get?", "q1", h.now))
        await env.sleep(timedelta(minutes=5))

    run_with(h, scenario)
    base = h.trace("q1")["baseline"]
    assert base["passed"] is False
    assert any(r.startswith("invented_number") for r in base["reasons"])
    assert [n["ok"] for n in base["numbers"]] == [False, False]


def test_a_failing_baseline_never_costs_the_hiker_their_reply(tmp_path):
    def boom(prompt):
        raise RuntimeError("baseline model down")

    h = Harness(tmp_path, baseline_draft=boom)

    async def scenario(env, h):
        await deliver(env.client, SENDER, inbound("PLACE 46.5, 7.9", "p1", h.now))
        await deliver(env.client, SENDER, inbound("how windy is it going to get?", "q1", h.now))
        await env.sleep(timedelta(minutes=5))

    run_with(h, scenario)
    assert "km/h" in h.rows("reply:q1")[0]["text"] and h.trace("q1")["baseline"] is None
