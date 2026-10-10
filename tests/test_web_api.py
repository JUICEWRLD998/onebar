import pytest
from fastapi.testclient import TestClient

import json

from onebar.channels.hints import HintStore
from onebar.channels.ratelimit import RateLimiter
from onebar.channels.router import RouterSender
from onebar.channels.traces import TraceStore
from onebar.channels.web_api import WebSender, create_app
from onebar.temporal.starter import workflow_id

from conftest import FIXTURE_DIR

SESSION = "sess-abcdef12"


class Rig:
    def __init__(self, tmp_path, fail=False, per_session=None, per_ip=None):
        self.web = WebSender(tmp_path / "web")
        self.traces = TraceStore(tmp_path / "tr")
        self.hints = HintStore(tmp_path / "hints")
        self.delivered = []
        self.fail = fail

        async def deliver(sender, msg):
            if self.fail:
                raise ConnectionError("temporal down")
            self.delivered.append((sender, msg))

        self.client = TestClient(create_app(deliver, self.web, self.traces, per_session, per_ip, hints=self.hints))


def test_post_message_delivers_to_a_web_sender_and_returns_an_id(tmp_path):
    r = Rig(tmp_path)
    res = r.client.post("/api/message", json={"session": SESSION, "text": "storm before 3?"})
    assert res.status_code == 200
    mid = res.json()["id"]
    assert len(mid) == 32
    sender, msg = r.delivered[0]
    assert sender == f"web:{SESSION}" and msg.id == mid and msg.text == "storm before 3?" and msg.channel == "web"


def test_reply_is_pending_then_done_with_a_trace_link(tmp_path):
    r = Rig(tmp_path)
    mid = r.client.post("/api/message", json={"session": SESSION, "text": "hi"}).json()["id"]
    assert r.client.get(f"/api/reply/{mid}").json() == {"status": "pending"}
    assert RouterSender(web=r.web).send(f"reply:{mid}", f"web:{SESSION}", "No storm.") is True
    assert r.client.get(f"/api/reply/{mid}").json() == {"status": "done", "text": "No storm.", "trace_id": None}
    tid = r.traces.save(mid, {"reply": "No storm.", "question": "hi", "numbers": []})
    assert r.client.get(f"/api/reply/{mid}").json()["trace_id"] == tid
    assert r.client.get(f"/api/trace/{tid}").json()["reply"] == "No storm."


def test_a_reply_is_written_once(tmp_path):
    r = Rig(tmp_path)
    assert r.web.send("reply:" + "a" * 32, "web:s", "first") is True
    assert r.web.send("reply:" + "a" * 32, "web:s", "second") is False
    assert r.web.get("a" * 32)["text"] == "first"


def test_alerts_and_non_web_destinations_never_reach_the_browser_store(tmp_path):
    r = Rig(tmp_path)
    assert r.web.send("alert:t1", "web:s", "x") is False
    assert r.web.send("reply:m1", "a@b.co", "x") is False


@pytest.mark.parametrize("body, code", [
    ({"session": "short", "text": "hi"}, 422),
    ({"session": "has space in it!", "text": "hi"}, 422),
    ({"session": SESSION, "text": ""}, 422),
    ({"session": SESSION}, 422),
    ({"session": SESSION, "text": "x" * 501}, 413),
])
def test_bad_input_is_refused(tmp_path, body, code):
    r = Rig(tmp_path)
    assert r.client.post("/api/message", json=body).status_code == code
    assert r.delivered == []


def test_exactly_the_maximum_length_is_accepted(tmp_path):
    r = Rig(tmp_path)
    assert r.client.post("/api/message", json={"session": SESSION, "text": "x" * 500}).status_code == 200


def test_rate_limits_by_session_and_by_ip(tmp_path):
    r = Rig(tmp_path, per_session=RateLimiter(2, 600), per_ip=RateLimiter(100, 600))
    codes = [r.client.post("/api/message", json={"session": SESSION, "text": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert r.client.post("/api/message", json={"session": "another-session", "text": "hi"}).status_code == 200
    r2 = Rig(tmp_path / "b", per_session=RateLimiter(100, 600), per_ip=RateLimiter(1, 600))
    assert [r2.client.post("/api/message", json={"session": f"sess-{i}xxxxxxx", "text": "hi"}).status_code
            for i in range(2)] == [200, 429]


def test_service_down_is_a_clear_503_with_no_internal_detail(tmp_path):
    r = Rig(tmp_path, fail=True)
    res = r.client.post("/api/message", json={"session": SESSION, "text": "hi"})
    assert res.status_code == 503 and "temporal" not in res.text.lower()


@pytest.mark.parametrize("path", ["/api/reply/not-an-id", "/api/reply/" + "g" * 32, "/api/trace/..%2f..%2fsecret",
                                  "/api/trace/" + "a" * 32, "/api/trace/short"])
def test_unknown_or_malformed_ids_are_404(tmp_path, path):
    assert Rig(tmp_path).client.get(path).status_code == 404


def test_the_trace_never_exposes_the_session_or_address(tmp_path):
    r = Rig(tmp_path)
    mid = r.client.post("/api/message", json={"session": SESSION, "text": "hi"}).json()["id"]
    tid = r.traces.save(mid, {"reply": "x", "question": "hi", "numbers": []})
    assert SESSION not in r.client.get(f"/api/trace/{tid}").text
    assert SESSION not in r.client.get(f"/api/reply/{mid}").text


REAL = json.loads((FIXTURE_DIR.parent / "open_meteo_46.55_7.98.json").read_text())


def test_a_browser_hint_is_filed_under_the_sessions_workflow(tmp_path):
    r = Rig(tmp_path)
    hint = {"forecast": {"lat": 46.55, "lon": 7.98, "data": REAL}}
    res = r.client.post("/api/message", json={"session": SESSION, "text": "storm?", "hint": hint})
    assert res.status_code == 200 and len(r.delivered) == 1
    assert r.hints.forecast(workflow_id(f"web:{SESSION}"), 46.55, 7.98) is not None
    assert r.hints.forecast(workflow_id("web:sess-zzzzzzzz"), 46.55, 7.98) is None


def test_a_bad_or_oversized_hint_is_dropped_but_the_message_still_goes(tmp_path):
    r = Rig(tmp_path)
    for hint in ({"forecast": {"lat": 46.55, "lon": 7.98, "data": {"hourly": "x"}}},
                 {"place": {"query": "a", "name": "b" * 300_000, "lat": 1, "lon": 1}}):
        res = r.client.post("/api/message", json={"session": SESSION, "text": "storm?", "hint": hint})
        assert res.status_code == 200
    assert len(r.delivered) == 2
    assert not (tmp_path / "hints").exists()


def test_health_and_no_openapi_docs(tmp_path):
    c = Rig(tmp_path).client
    assert c.get("/api/health").json() == {"ok": True}
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


def test_router_picks_the_channel_by_destination():
    class Rec:
        def __init__(self):
            self.calls = []

        def send(self, k, t, x):
            self.calls.append((k, t))
            return True

    email, web, fb = Rec(), Rec(), Rec()
    r = RouterSender(email=email, web=web, fallback=fb)
    r.send("reply:1", "web:abc", "t")
    r.send("alert:1", "friend@example.org", "t")
    r.send("alert:2", "+4477", "t")
    assert (web.calls, email.calls, fb.calls) == ([("reply:1", "web:abc")], [("alert:1", "friend@example.org")], [("alert:2", "+4477")])
    assert RouterSender().send("k", "a@b.co", "t") is False
    assert RouterSender(web=None).send("k", "web:x", "t") is False
