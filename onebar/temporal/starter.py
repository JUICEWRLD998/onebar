"""Deliver an inbound message to its sender's workflow, starting the workflow if it is not running."""
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from onebar.temporal.models import TASK_QUEUE, Inbound, WorkflowState
from onebar.temporal.workflows import TripWorkflow


def normalize(sender: str) -> str:
    return sender.strip().lower()


def workflow_id(sender: str) -> str:
    return "onebar-" + normalize(sender)


async def deliver(client: Client, sender: str, msg: Inbound, task_queue: str = TASK_QUEUE, can_after: int = 100,
                  idle_s: int = 7 * 24 * 3600) -> str:
    """Signal-with-start. Returns the workflow id. Safe to call twice with the same msg.id."""
    wid = workflow_id(sender)
    await client.start_workflow(
        TripWorkflow.run,
        WorkflowState(sender=normalize(sender), can_after=can_after, idle_s=idle_s),
        id=wid,
        task_queue=task_queue,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
        start_signal="message_received",
        start_signal_args=[msg],
    )
    return wid
