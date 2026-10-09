"""Keep the tuned adapter warm.

Measured on Tinker: a LoRA adapter answers in about 1 s while in use, 3 s after 20 s idle and 6.6 s after 45 s idle.
A minimal completion every few seconds keeps replies near 1 s. Each ping is a few dozen tokens, billed through the
spend ledger like any other call; a spent budget or a network error just ends that ping.
"""
from __future__ import annotations

import asyncio

from onebar.model.prompt import chatml

PING_PROMPT = chatml([{"role": "user", "content": "Say ok."}])


async def ping_loop(draft, interval_s: float, stop: asyncio.Event | None = None) -> int:
    """Ping `draft` every `interval_s` seconds until `stop` is set. Returns the number of successful pings."""
    ok = 0
    stop = stop or asyncio.Event()
    while not stop.is_set():
        try:
            await asyncio.to_thread(draft, PING_PROMPT)
            ok += 1
        except Exception:
            pass  # a failed ping must never take the worker down
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            pass
    return ok
