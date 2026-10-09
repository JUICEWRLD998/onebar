"""ASGI app for the web phone: uvicorn onebar.channels.web_server:app --port 8000

Connects to Temporal on first use, so the server starts even if Temporal is briefly down.
"""
import os

from temporalio.client import Client

from onebar.channels import wiring
from onebar.channels.web_api import create_app
from onebar.env import load_env
from onebar.temporal.starter import deliver

load_env()
_stores = wiring.stores()
_client: Client | None = None


async def _deliver(sender, inbound) -> None:
    global _client
    if _client is None:
        _client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
                                       namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"))
    await deliver(_client, sender, inbound)


app = create_app(_deliver, _stores.web, _stores.traces)
