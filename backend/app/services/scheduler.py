"""Background loop that fires anything whose absolute timestamp has passed.

Nothing here counts down. Once per tick it asks the database "what is already
due?" — each of those queries is served by a dedicated index — and emits the
corresponding event. A backend restart, a paused laptop or a dropped WebSocket
cannot desync the schedule: the truth is always the stored timestamp.
"""

from __future__ import annotations

import asyncio
import logging

from .. import events as ev
from .. import repo
from ..config import settings
from ..db import mongo
from ..models import Device
from ..realtime import hub
from ..serializers import alarm_read, device_read, pomodoro_read, reminder_read, timer_read
from ..utils import as_utc, utcnow
from . import alarms as alarm_service
from . import pomodoro as pomodoro_service
from . import timers as timer_service

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._offline_announced: set[str] = set()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="deskmate-scheduler")
        log.info("Scheduler started (tick %.1fs)", settings.scheduler_interval_seconds)

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                pass
            self._task = None
            log.info("Scheduler stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                if mongo.ready:
                    await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a bad tick must not kill the loop
                log.exception("Scheduler tick failed")
            await asyncio.sleep(settings.scheduler_interval_seconds)

    async def _tick(self) -> None:
        await self._fire_timers()
        await self._fire_pomodoro()
        await self._fire_alarms()
        await self._fire_reminders()
        await self._check_presence()

    # ------------------------------------------------------------------ timers
    async def _fire_timers(self) -> None:
        for timer in await timer_service.due_timers():
            finished = await timer_service.finish(timer)
            log.info("Timer finished: %s (%s)", finished.label, finished.id)
            await hub.publish(
                ev.TIMER_FINISHED,
                timer_read(finished).model_dump(mode="json"),
                device_id=finished.device_id,
                origin="system",
            )

    # ---------------------------------------------------------------- pomodoro
    async def _fire_pomodoro(self) -> None:
        for state in await pomodoro_service.running_states():
            if not pomodoro_service.is_due(state):
                continue
            change = await pomodoro_service.advance(state, natural=True)
            payload = pomodoro_read(change.state).model_dump(mode="json")
            payload["previous_phase"] = change.previous_phase
            log.info(
                "Pomodoro %s -> %s (device %s)",
                change.previous_phase,
                change.new_phase,
                state.id,
            )
            await hub.publish(
                ev.POMODORO_PHASE_CHANGED, payload, device_id=state.id, origin="system"
            )

    # ------------------------------------------------------------------ alarms
    async def _fire_alarms(self) -> None:
        for alarm in await alarm_service.due_alarms():
            payload = alarm_read(alarm).model_dump(mode="json")
            await alarm_service.mark_triggered(alarm)
            log.info("Alarm triggered: %s %s", alarm.label, alarm.time_of_day)
            await hub.publish(
                ev.ALARM_TRIGGERED, payload, device_id=alarm.device_id, origin="system"
            )

    # --------------------------------------------------------------- reminders
    async def _fire_reminders(self) -> None:
        for reminder in await alarm_service.due_reminders():
            await alarm_service.mark_notified(reminder)
            log.info("Reminder due: %s", reminder.text)
            await hub.publish(
                ev.REMINDER_DUE,
                reminder_read(reminder).model_dump(mode="json"),
                device_id=reminder.device_id,
                origin="system",
            )

    # ---------------------------------------------------------------- presence
    async def _check_presence(self) -> None:
        """Announce a device going quiet so dashboards can grey out."""
        devices = await repo.find_many(mongo.devices, Device, {}, limit=50)
        for device in devices:
            last_seen = as_utc(device.last_seen_at)
            if last_seen is None:
                continue
            silent_for = (utcnow() - last_seen).total_seconds()
            offline = (
                silent_for > settings.device_offline_after_seconds
                and not hub.device_connected(device.id)
            )
            if offline and device.id not in self._offline_announced:
                self._offline_announced.add(device.id)
                await hub.publish(
                    ev.DEVICE_OFFLINE,
                    device_read(device).model_dump(mode="json"),
                    device_id=device.id,
                    origin="system",
                )
            elif not offline:
                self._offline_announced.discard(device.id)


scheduler = Scheduler()
