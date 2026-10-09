"""Poll the alias every 10 seconds and hand new mail to Temporal.

  python -m onebar.channels.email_poll            # run until stopped
  python -m onebar.channels.email_poll --once     # one pass, for a check
  python -m onebar.channels.email_poll --allow-self   # the owner testing from their own address

Logs only counts and message ids, never addresses or message text.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from temporalio.client import Client

from onebar.channels import email_io, wiring
from onebar.channels.ratelimit import RateLimiter
from onebar.env import load_env
from onebar.temporal.starter import deliver

INTERVAL_S = float(os.environ.get("ONEBAR_POLL_S", 5))  # a pass on a live connection costs under a second


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--allow-self", action="store_true")
    args = p.parse_args()
    load_env()
    user, password = os.environ.get("IMAP_USER", ""), os.environ.get("IMAP_APP_PASSWORD", "")
    if not user or not password:
        print("IMAP_USER and IMAP_APP_PASSWORD must be set in .env", file=sys.stderr)
        return 1
    alias = email_io.alias_for(user)
    st = wiring.stores()
    limiter = RateLimiter(max_events=10, window_s=600)
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
                                  namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"))
    loop = asyncio.get_running_loop()

    def handoff(sender, inbound):
        asyncio.run_coroutine_threadsafe(deliver(client, sender, inbound), loop).result(60)

    imap = email_io.GmailImap(user, password)  # one long-lived connection: a fresh TLS connect costs about 4 s

    def cycle():
        try:
            if imap.connected:
                imap.refresh()
            else:
                imap.connect()
            return email_io.poll_once(imap, alias=alias, own=user, seen=st.seen, threads=st.threads,
                                      limiter=limiter, handoff=handoff, allow_self=args.allow_self)
        except Exception:
            imap.close()  # reconnect on the next pass
            raise

    log(f"polling mail sent to the alias every {INTERVAL_S}s (read-only); allow_self={args.allow_self}")
    while True:
        try:
            counts = await asyncio.to_thread(cycle)
            if counts:
                log(f"pass: {dict(counts)}")
        except Exception as exc:  # network blips and IMAP hiccups must not kill the poller
            tb = exc.__traceback__
            while tb and tb.tb_next:
                tb = tb.tb_next
            where = f"{Path(tb.tb_frame.f_code.co_filename).name}:{tb.tb_lineno}" if tb else "?"
            log(f"pass failed: {type(exc).__name__} at {where}")  # type and place only: messages can hold addresses
        if args.once:
            return 0
        await asyncio.sleep(INTERVAL_S)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
