import asyncio

from onebar.model import keepalive as K
from onebar.model.client import ModelError


def run(coro):
    return asyncio.run(coro)


def test_pings_repeat_until_stopped():
    calls = []

    async def go():
        stop = asyncio.Event()
        task = asyncio.create_task(K.ping_loop(lambda p: calls.append(p) or "ok", 0.02, stop))
        await asyncio.sleep(0.15)
        stop.set()
        return await task

    ok = run(go())
    assert ok == len(calls) >= 3
    assert all(c == K.PING_PROMPT for c in calls)


def test_errors_do_not_stop_the_loop():
    n = {"i": 0}

    def flaky(prompt):
        n["i"] += 1
        if n["i"] % 2:
            raise ModelError("cap reached")
        return "ok"

    async def go():
        stop = asyncio.Event()
        task = asyncio.create_task(K.ping_loop(flaky, 0.02, stop))
        await asyncio.sleep(0.15)
        stop.set()
        return await task

    ok = run(go())
    assert n["i"] >= 4 and 0 < ok < n["i"]


def test_the_ping_is_tiny():
    assert len(K.PING_PROMPT) < 120 and K.PING_PROMPT.endswith("<think>\n\n</think>\n\n")
