"""Run the worker: python -m onebar.temporal.worker [--no-model]

Reads TEMPORAL_ADDRESS (default localhost:7233) and TEMPORAL_NAMESPACE from .env. Replies and alerts go to
data/outbox.jsonl until Phase 6 adds real channels. With a model, the reply writer is ONEBAR_MODEL (spend is capped
by the ledger); with --no-model the code template answers.
"""
import argparse
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from temporalio.client import Client
from temporalio.worker import Worker

from onebar.channels import wiring
from onebar.channels.outbox import OutboxSender
from onebar.env import load_env
from onebar.model import keepalive
from onebar.model.client import ModelError, TinkerDraft
from onebar.temporal.activities import Activities, Deps
from onebar.temporal.models import TASK_QUEUE
from onebar.temporal.workflows import TripWorkflow


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-model", action="store_true")
    p.add_argument("--outbox", default="", help="fallback outbox file (default data/outbox.jsonl)")
    p.add_argument("--no-email", action="store_true", help="never send real email, even if IMAP_USER is set")
    args = p.parse_args()
    load_env()
    draft = None
    if not args.no_model:
        try:
            draft = TinkerDraft()
        except ModelError as exc:
            print(f"no model ({exc}); the template will answer", flush=True)
    st = wiring.stores()
    if args.outbox:  # a custom outbox path, used by the kill-and-restart demo
        st.outbox = OutboxSender(Path(args.outbox))
    if args.no_email:
        os.environ["IMAP_APP_PASSWORD"] = ""  # build_sender enables email only when both are set
    sender = wiring.build_sender(st)
    print("channels: email", "on" if sender.email else "off (local outbox)", "| web on", flush=True)
    baseline = None
    if draft is not None and os.environ.get("ONEBAR_COMPARE", "1") != "0":
        try:  # the untuned base model, run only to show the comparison on the trace page
            baseline = TinkerDraft(model="Qwen/Qwen3-8B")
        except ModelError:
            baseline = None
    acts = Activities(Deps(sender=sender, draft=draft, traces=st.traces, baseline_draft=baseline))
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
                                  namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"))
    keep_s = float(os.environ.get("ONEBAR_KEEPALIVE_S", 15))
    if draft is not None and keep_s > 0:
        asyncio.create_task(keepalive.ping_loop(draft, keep_s))
        print(f"model keepalive every {keep_s:g}s (ONEBAR_KEEPALIVE_S=0 turns it off)", flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        async with Worker(client, task_queue=TASK_QUEUE, workflows=[TripWorkflow], activities=acts.all(),
                          activity_executor=pool):
            print("worker running on task queue", TASK_QUEUE, "model:", "yes" if draft else "template only", flush=True)
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
