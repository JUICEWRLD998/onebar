"""TripWorkflow: one long-lived workflow per sender.

- A signal carries each inbound message. A message id already accepted is dropped in the signal handler, so a
  redelivered message never produces a second reply.
- A trip starts a durable timer for return time plus grace. OUT cancels the alert; if the timer fires first, the
  contact gets one alert (idempotency key per trip) that says plainly it is not a rescue service.
- After `can_after` messages the workflow continues as new with its state, so history stays small.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from onebar import commands, trips
    from onebar.temporal.activities import Activities
    from onebar.temporal.models import (
        AnswerReq, AnswerResult, Inbound, PlaceReq, PlaceResult, ResolveReq, ResolveResult, SendReq, TripState,
        WorkflowState,
    )

SEEN_KEEP = 1000
ALERT_RETRY_S = 300

NET_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), backoff_coefficient=2.0,
                        maximum_interval=timedelta(seconds=30), maximum_attempts=4)
SEND_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0,
                         maximum_interval=timedelta(seconds=30), maximum_attempts=6)


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(timezone.utc)


@workflow.defn
class TripWorkflow:
    @workflow.init
    def __init__(self, state: WorkflowState) -> None:
        self.s = state
        self.inbox: list = []
        self.done = False
        self.alert_failed = False

    # ---- input -----------------------------------------------------------------------------------------------

    @workflow.signal
    def message_received(self, msg: Inbound) -> None:
        if msg.id in self.s.seen:
            return  # redelivery: already accepted, already answered or queued
        self.s.seen.append(msg.id)
        del self.s.seen[:-SEEN_KEEP]
        self.inbox.append(msg)

    @workflow.query
    def status(self) -> dict:
        t = self.s.trip
        return {"trip": None if t is None else {"place": t.place, "back": t.back_local, "alerted": t.alerted},
                "pos": self.s.last_pos, "offset_s": self.s.last_offset_s,
                "queued": len(self.inbox), "processed": self.s.processed}

    # ---- main loop -------------------------------------------------------------------------------------------

    @workflow.run
    async def run(self, state: WorkflowState) -> str:
        while True:
            wait_s, for_alert = self._wait()
            try:
                await workflow.wait_condition(lambda: bool(self.inbox) or self.done, timeout=wait_s)
            except asyncio.TimeoutError:
                if for_alert:
                    await self._alert()
                    continue
                return "idle"
            while self.inbox:
                await self._handle(self.inbox.pop(0))
                if self.done:
                    return "forgotten"
            if self.s.processed >= self.s.can_after:
                self.s.processed = 0
                workflow.continue_as_new(self.s)

    def _wait(self) -> tuple[float, bool]:
        """Seconds to wait for a message, and whether a timeout then means "the alert is due"."""
        t = self.s.trip
        if t is not None and not t.alerted:
            if self.alert_failed:
                return float(ALERT_RETRY_S), True
            return max(0.0, (_dt(t.alert_iso) - workflow.now()).total_seconds()), True
        return float(self.s.idle_s), False

    # ---- handlers --------------------------------------------------------------------------------------------

    async def _handle(self, msg: Inbound) -> None:
        self.s.processed += 1
        self.s.last_msg_iso = msg.ts
        cmd = commands.parse(msg.text, allow_phone=self.s.allow_phone)
        if isinstance(cmd, commands.TripCmd):
            await self._register(msg, cmd)
        elif isinstance(cmd, commands.OutCmd):
            if self.s.trip is None:
                await self._reply(msg, "No active trip.")
            else:
                self.s.trip = None
                await self._reply(msg, "Checked out. Trip ended. Glad you are safe.")
        elif isinstance(cmd, commands.ForgetCmd):
            await self._reply(msg, "Done. Everything stored about you is deleted.")
            self.s = WorkflowState(sender=self.s.sender)
            self.done = True
        elif isinstance(cmd, commands.HelpCmd):
            await self._reply(msg, commands.HELP_TEXT)
        elif isinstance(cmd, commands.PlaceCmd):
            await self._place(msg, cmd)
        elif isinstance(cmd, commands.BadCmd):
            await self._reply(msg, cmd.reason)
        else:
            await self._question(msg, cmd.text)

    async def _register(self, msg: Inbound, cmd: "commands.TripCmd") -> None:
        try:
            res: ResolveResult = await workflow.execute_activity_method(
                Activities.resolve_trip,
                ResolveReq(place=cmd.place, coords=list(cmd.coords) if cmd.coords else None,
                           back=cmd.back.strftime("%H:%M"), now_iso=msg.ts),
                start_to_close_timeout=timedelta(seconds=60), retry_policy=NET_RETRY,
            )
        except ActivityError:
            await self._reply(msg, trips.FORECAST_DOWN)
            return
        if not res.ok:
            await self._reply(msg, res.error)
            return
        self.s.trip = TripState(
            place=res.place, lat=res.lat, lon=res.lon, contact=cmd.contact, back_local=res.back_local,
            offset_s=res.offset_s, deadline_iso=res.deadline_iso, alert_iso=res.alert_iso, trip_id=msg.id,
        )
        self.alert_failed = False
        self.s.last_pos = [res.lat, res.lon]
        self.s.last_offset_s = res.offset_s
        await self._reply(msg, trips.trip_saved_text(res.back_local, res.alert_local))

    async def _place(self, msg: Inbound, cmd: "commands.PlaceCmd") -> None:
        try:
            res: PlaceResult = await workflow.execute_activity_method(
                Activities.resolve_place,
                PlaceReq(place=cmd.place, coords=list(cmd.coords) if cmd.coords else None),
                start_to_close_timeout=timedelta(seconds=60), retry_policy=NET_RETRY,
            )
        except ActivityError:
            await self._reply(msg, trips.FORECAST_DOWN)
            return
        if not res.ok:
            await self._reply(msg, res.error)
            return
        self.s.last_pos = [res.lat, res.lon]
        self.s.last_offset_s = res.offset_s
        await self._reply(msg, f"Place set: {res.place}. Ask your question.")

    async def _question(self, msg: Inbound, text: str) -> None:
        t = self.s.trip
        pos = [t.lat, t.lon] if t else self.s.last_pos
        if pos is None:
            await self._reply(msg, trips.NEED_PLACE)
            return
        offset = t.offset_s if t else self.s.last_offset_s
        try:
            ans: AnswerResult = await workflow.execute_activity_method(
                Activities.answer_question,
                AnswerReq(question=text, lat=pos[0], lon=pos[1], now_iso=msg.ts, offset_s=offset,
                          return_local=t.back_local if t else None, msg_id=msg.id),
                start_to_close_timeout=timedelta(seconds=90), retry_policy=NET_RETRY,
            )
            reply = ans.text
        except ActivityError:
            reply = trips.FORECAST_DOWN
        await self._reply(msg, reply)

    async def _reply(self, msg: Inbound, text: str) -> None:
        await self._send(f"reply:{msg.id}", self.s.sender, text)

    async def _send(self, key: str, to: str, text: str) -> bool:
        try:
            await workflow.execute_activity_method(
                Activities.send, SendReq(key=key, to=to, text=text),
                start_to_close_timeout=timedelta(seconds=30), retry_policy=SEND_RETRY,
            )
            return True
        except ActivityError:
            return False  # the message stays unsent; the workflow carries on rather than stalling every later message

    async def _alert(self) -> None:
        t = self.s.trip
        if t is None or t.alerted:
            return
        last_local = None
        if self.s.last_msg_iso:
            last_local = trips.local_clock(_dt(self.s.last_msg_iso), t.offset_s)
        text = trips.alert_text(self.s.sender, t.place, t.lat, t.lon, t.back_local, last_local)
        if await self._send(f"alert:{t.trip_id}", t.contact, text):
            t.alerted = True
            self.alert_failed = False
        else:
            self.alert_failed = True  # try again in ALERT_RETRY_S; the key keeps a late success from doubling
