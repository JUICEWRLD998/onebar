"""Phase 5 live proof: kill the worker mid-trip, restart it, and the overdue alert still arrives exactly once.

Starts a real Temporal dev server and a real worker process (template answers, no Tinker spend), registers a trip that
is due in ~2 minutes with a 1 minute grace, kills the worker, waits past the alert time, restarts the worker, and
checks the outbox. Takes about 5 minutes. Uses the live Open-Meteo forecast once, for the place's UTC offset.
"""
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from temporalio.client import Client

from onebar import trips
from onebar.facts.open_meteo import fetch_forecast
from onebar.temporal.models import Inbound
from onebar.temporal.starter import deliver, workflow_id

SENDER = "demo-hiker@example.org"
CONTACT = "demo-contact@example.org"
OUTBOX = ROOT / "data" / "demo_outbox.jsonl"
DB = ROOT / "data" / "demo-temporal.db"
LAT, LON = 46.55, 7.98


def rows() -> list[dict]:
    if not OUTBOX.is_file():
        return []
    return [json.loads(line) for line in OUTBOX.read_text(encoding="utf-8").splitlines() if line.strip()]


def start_worker() -> subprocess.Popen:
    env = {**os.environ, "ONEBAR_GRACE_MIN": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.Popen(
        [sys.executable, "-m", "onebar.temporal.worker", "--no-model", "--outbox", str(OUTBOX)],
        cwd=ROOT, env=env,
    )


def say(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


async def main() -> int:
    for p in (OUTBOX, DB):
        if p.exists():
            p.unlink()
    server = subprocess.Popen(
        [str(ROOT / ".tools" / "temporal.exe"), "server", "start-dev", "--headless", "--port", "7233",
         "--db-filename", str(DB)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    worker = None
    try:
        client = None
        for _ in range(60):
            try:
                client = await Client.connect("localhost:7233")
                break
            except Exception:
                await asyncio.sleep(1)
        if client is None:
            say("dev server did not come up")
            return 1
        say("dev server up")
        worker = start_worker()
        await asyncio.sleep(4)

        offset = int(fetch_forecast(LAT, LON)["utc_offset_seconds"])
        now = datetime.now(timezone.utc)
        back = trips.local_clock(now + timedelta(minutes=2), offset)
        await deliver(client, SENDER, Inbound("demo-trip", f"TRIP {LAT},{LON} BACK {back} CONTACT {CONTACT}", "demo", now.isoformat()))
        say(f"trip registered, back {back} local (about 2 minutes), grace 1 minute; alert due around 3 minutes")
        await asyncio.sleep(25)
        say("KILLING the worker mid-trip")
        worker.kill()
        worker.wait()
        say(f"worker dead; outbox has {len(rows())} message(s): {[r['key'] for r in rows()]}")
        await asyncio.sleep(170)  # well past return + grace while no worker exists
        say(f"alert time has passed with no worker; alerts so far: {len([r for r in rows() if r['key'].startswith('alert:')])}")
        worker = start_worker()
        say("worker RESTARTED")
        deadline = time.time() + 120
        while time.time() < deadline and not [r for r in rows() if r["key"].startswith("alert:")]:
            await asyncio.sleep(2)
        await asyncio.sleep(45)  # a duplicate, if any, would show up now
        alerts = [r for r in rows() if r["key"].startswith("alert:")]
        say(f"alerts delivered: {len(alerts)}")
        for r in alerts:
            say(f"  to {r['to']}: {r['text']}")
        st = await client.get_workflow_handle(workflow_id(SENDER)).query("status")
        say(f"workflow status: {st}")
        ok = len(alerts) == 1 and alerts[0]["to"] == CONTACT
        say("RESULT: " + ("PASS - the alert arrived once after the worker was killed and restarted" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        if worker and worker.poll() is None:
            worker.kill()
        server.kill()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
