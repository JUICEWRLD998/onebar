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

from onebar.channels.outbox import OutboxSender
from onebar.env import ROOT, load_env
from onebar.model.client import ModelError, TinkerDraft
from onebar.temporal.activities import Activities, Deps
from onebar.temporal.models import TASK_QUEUE
from onebar.temporal.workflows import TripWorkflow


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-model", action="store_true")
    p.add_argument("--outbox", default=str(ROOT / "data" / "outbox.jsonl"))
    args = p.parse_args()
    load_env()
    draft = None
    if not args.no_model:
        try:
            draft = TinkerDraft()
        except ModelError as exc:
            print(f"no model ({exc}); the template will answer", flush=True)
    acts = Activities(Deps(sender=OutboxSender(Path(args.outbox)), draft=draft))
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
                                  namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        async with Worker(client, task_queue=TASK_QUEUE, workflows=[TripWorkflow], activities=acts.all(),
                          activity_executor=pool):
            print("worker running on task queue", TASK_QUEUE, "model:", "yes" if draft else "template only", flush=True)
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
