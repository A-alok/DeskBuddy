"""Turns a parsed Intent into real state changes plus broadcast events.

This is the one place that knows how a command becomes an action, so voice,
dashboard chat and mobile chat all behave identically.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from .. import events as ev
from .. import repo
from ..db import mongo
from ..models import (
    Alarm,
    CommandSource,
    Device,
    Note,
    Priority,
    Reminder,
    RunState,
    Task,
)
from ..realtime import hub
from ..serializers import (
    alarm_read,
    device_read,
    pomodoro_read,
    reminder_read,
    stopwatch_read,
    task_read,
    timer_read,
)
from ..utils import iso, next_occurrence, utcnow
from . import alarms as alarm_service
from . import conversation
from . import intents as intent_service
from . import pomodoro as pomodoro_service
from . import quiz as quiz_service
from . import stopwatch as stopwatch_service
from . import timers as timer_service
from . import weather as weather_service

log = logging.getLogger(__name__)


class ExecutionResult:
    def __init__(self, reply: str, action: Optional[str] = None, data: Any = None) -> None:
        self.reply = reply
        self.action = action
        self.data = data


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


async def execute(
    device: Device,
    intent: intent_service.Intent,
    *,
    source: CommandSource = CommandSource.VOICE,
) -> ExecutionResult:
    name = intent.name
    entities = intent.entities
    origin = source.value if isinstance(source, CommandSource) else str(source)
    device_id = device.id

    # ---------------------------------------------------------------- timer #
    if name == "timer.start":
        seconds = int(entities.get("duration_seconds") or 0)
        if seconds < 1:
            return ExecutionResult("How long should the timer run?")
        label = str(entities.get("label") or "Timer")
        timer = await timer_service.start(device_id, seconds, label)
        await hub.publish(
            ev.TIMER_STARTED, _dump(timer_read(timer)), device_id=device_id, origin=origin
        )
        return ExecutionResult(intent.reply or f"Timer has been set for {_human_seconds(seconds)}.", "timer.start", timer)

    if name in {"timer.pause", "timer.resume", "timer.cancel", "timer.status"}:
        timer = await timer_service.get_active(device_id)
        if timer is None:
            return ExecutionResult("No timer is running.")
        if name == "timer.pause":
            timer = await timer_service.pause(timer)
            await hub.publish(ev.TIMER_PAUSED, _dump(timer_read(timer)), device_id=device_id, origin=origin)
            return ExecutionResult("Timer paused.", "timer.pause", timer)
        if name == "timer.resume":
            timer = await timer_service.resume(timer)
            await hub.publish(ev.TIMER_RESUMED, _dump(timer_read(timer)), device_id=device_id, origin=origin)
            return ExecutionResult("Timer resumed.", "timer.resume", timer)
        if name == "timer.cancel":
            timer = await timer_service.cancel(timer)
            await hub.publish(ev.TIMER_CANCELLED, _dump(timer_read(timer)), device_id=device_id, origin=origin)
            return ExecutionResult("Timer has been cancelled.", "timer.cancel", timer)
        read = timer_read(timer)
        return ExecutionResult(
            f"{_human_seconds(read.remaining_seconds)} left on {read.label}.",
            "timer.status",
            timer,
        )

    # ------------------------------------------------------------ stopwatch #
    if name.startswith("stopwatch."):
        action = name.split(".", 1)[1]
        mapping = {
            "start": (stopwatch_service.start, ev.STOPWATCH_STARTED, "Stopwatch running."),
            "stop": (stopwatch_service.stop, ev.STOPWATCH_STOPPED, "Stopwatch stopped."),
            "lap": (stopwatch_service.lap, ev.STOPWATCH_LAPPED, "Lap recorded."),
            "reset": (stopwatch_service.reset, ev.STOPWATCH_RESET, "Stopwatch reset."),
        }
        if action in mapping:
            fn, event_name, reply = mapping[action]
            sw = await fn(device_id)
            await hub.publish(event_name, _dump(stopwatch_read(sw)), device_id=device_id, origin=origin)
            return ExecutionResult(reply, name, sw)

    # ------------------------------------------------------------- pomodoro #
    if name == "pomodoro.start":
        state = await pomodoro_service.get(device_id)
        if entities.get("focus_minutes"):
            state = await pomodoro_service.apply_config(
                state, focus_minutes=int(entities["focus_minutes"])
            )
        state = await pomodoro_service.start(state)
        await hub.publish(ev.POMODORO_STARTED, _dump(pomodoro_read(state)), device_id=device_id, origin=origin)
        return ExecutionResult(
            intent.reply or f"Pomodoro focus session started for {state.focus_minutes} minutes.", "pomodoro.start", state
        )

    if name in {"pomodoro.pause", "pomodoro.resume", "pomodoro.stop", "pomodoro.skip"}:
        state = await pomodoro_service.get(device_id)
        if name == "pomodoro.pause":
            state = await pomodoro_service.pause(state)
            await hub.publish(ev.POMODORO_PAUSED, _dump(pomodoro_read(state)), device_id=device_id, origin=origin)
            return ExecutionResult("Pomodoro paused.", name, state)
        if name == "pomodoro.resume":
            state = await pomodoro_service.resume(state)
            await hub.publish(ev.POMODORO_RESUMED, _dump(pomodoro_read(state)), device_id=device_id, origin=origin)
            return ExecutionResult("Pomodoro resumed.", name, state)
        if name == "pomodoro.stop":
            state = await pomodoro_service.stop(state)
            await hub.publish(ev.POMODORO_STOPPED, _dump(pomodoro_read(state)), device_id=device_id, origin=origin)
            return ExecutionResult("Pomodoro has been stopped.", name, state)
        if state.state == RunState.IDLE:
            return ExecutionResult("No Pomodoro is running.")
        change = await pomodoro_service.advance(state, natural=False)
        payload = _dump(pomodoro_read(change.state))
        payload["previous_phase"] = change.previous_phase
        await hub.publish(ev.POMODORO_SKIPPED, payload, device_id=device_id, origin=origin)
        return ExecutionResult(
            f"Moved to {str(change.new_phase).replace('_', ' ')}.", name, change.state
        )

    # ---------------------------------------------------------------- alarm #
    if name == "alarm.set":
        time_of_day = str(entities.get("time_of_day") or "07:00")
        days = list(entities.get("days_of_week") or [])
        alarm = Alarm(
            device_id=device_id,
            label=str(entities.get("label") or "Alarm"),
            time_of_day=time_of_day,
            days_of_week=days,
        )
        alarm.next_trigger_at = next_occurrence(
            time_of_day, days, tz_offset_minutes=await alarm_service.tz_offset_for(device_id)
        )
        await repo.insert(mongo.alarms, alarm)
        await hub.publish(ev.ALARM_CREATED, _dump(alarm_read(alarm)), device_id=device_id, origin=origin)
        try:
            h, m = map(int, time_of_day.split(":"))
            period = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            spoken_clock = f"{h12}:{m:02d} {period}"
        except Exception:
            spoken_clock = time_of_day
        return ExecutionResult(intent.reply or f"Alarm has been set for {spoken_clock}.", "alarm.set", alarm)

    if name == "alarm.cancel":
        active = [a for a in await alarm_service.list_for_device(device_id) if a.enabled]
        if not active:
            return ExecutionResult("No alarms are enabled.")
        for alarm in active:
            updated = await repo.patch(
                mongo.alarms, Alarm, alarm.id, {"enabled": False, "next_trigger_at": None}
            )
            if updated is not None:
                await hub.publish(
                    ev.ALARM_UPDATED, _dump(alarm_read(updated)), device_id=device_id, origin=origin
                )
        word = "alarm" if len(active) == 1 else "alarms"
        return ExecutionResult(f"Cancelled {len(active)} {word}.", "alarm.cancel", active)

    if name == "alarm.list":
        items = await alarm_service.list_for_device(device_id)
        enabled = [a for a in items if a.enabled]
        if not enabled:
            return ExecutionResult("No alarms set.")
        listed = ", ".join(a.time_of_day for a in enabled[:4])
        return ExecutionResult(f"Alarms at {listed}.", "alarm.list", enabled)

    # ------------------------------------------------------------- reminder #
    if name == "reminder.create":
        text = str(entities.get("text") or "Reminder")
        if entities.get("in_minutes"):
            remind_at = utcnow() + timedelta(minutes=int(entities["in_minutes"]))
        elif entities.get("at_time"):
            remind_at = next_occurrence(
                str(entities["at_time"]),
                [],
                tz_offset_minutes=await alarm_service.tz_offset_for(device_id),
            )
        else:
            remind_at = utcnow() + timedelta(minutes=10)

        reminder = Reminder(device_id=device_id, text=text, remind_at=remind_at, source=source)
        await repo.insert(mongo.reminders, reminder)
        await hub.publish(ev.REMINDER_CREATED, _dump(reminder_read(reminder)), device_id=device_id, origin=origin)
        conversation.remember(device_id, "reminder", reminder.id, reminder.text)
        return ExecutionResult(f"Reminder saved for {iso(remind_at)}.", "reminder.create", reminder)

    # ---------------------------------------------------------------- tasks #
    if name == "task.create":
        title = str(entities.get("title") or "").strip()
        if not title:
            return ExecutionResult("What should the task say?")
        priority = Priority(str(entities.get("priority") or "normal"))
        task = Task(device_id=device_id, title=title, priority=priority, source=source)
        await repo.insert(mongo.tasks, task)
        await hub.publish(ev.TASK_CREATED, _dump(task_read(task)), device_id=device_id, origin=origin)
        # Remember it so a follow-up ("remove the last task", "delete it") works.
        conversation.remember(device_id, "task", task.id, task.title)
        return ExecutionResult(f"Added: {title}.", "task.create", task)

    if name in {"task.complete", "task.delete"}:
        open_tasks = await repo.find_many(
            mongo.tasks, Task, {"device_id": device_id, "done": False}, limit=200
        )
        if not open_tasks:
            return ExecutionResult("Nothing open to change.")

        ref = str(entities.get("ref") or "")
        title = str(entities.get("title") or "").strip().lower()
        match: Optional[Task] = None

        if ref:
            # "the last task" / "it" / "that one" — use the remembered task, or
            # fall back to the most recently created open task.
            remembered = conversation.recall(device_id, "task")
            if remembered is not None:
                match = next((t for t in open_tasks if t.id == remembered.entity_id), None)
            if match is None and ref == "last":
                match = max(open_tasks, key=lambda t: t.created_at)
            if match is None:
                return ExecutionResult("I'm not sure which task you mean. Say the task name.")
        elif title:
            match = next((t for t in open_tasks if title in t.title.lower()), None)
            if match is None:
                words = [w for w in title.split() if len(w) > 3]
                match = next(
                    (t for t in open_tasks if any(w in t.title.lower() for w in words)), None
                )
            if match is None:
                return ExecutionResult("I could not find that task.")
        else:
            return ExecutionResult("Which task?")

        if name == "task.delete":
            await repo.delete_by_id(mongo.tasks, match.id)
            await hub.publish(
                ev.TASK_DELETED, {"id": match.id}, device_id=device_id, origin=origin
            )
            conversation.clear(device_id)  # it no longer exists to refer to
            return ExecutionResult(f"Removed: {match.title}.", "task.delete", match)

        now = utcnow()
        updated = await repo.patch(
            mongo.tasks, Task, match.id, {"done": True, "completed_at": now, "updated_at": now}
        )
        final = updated or match
        await hub.publish(ev.TASK_UPDATED, _dump(task_read(final)), device_id=device_id, origin=origin)
        conversation.remember(device_id, "task", final.id, final.title)
        return ExecutionResult(f"Completed: {final.title}.", "task.complete", final)

    if name == "task.list":
        open_tasks = await repo.find_many(
            mongo.tasks, Task, {"device_id": device_id, "done": False}, limit=5
        )
        if not open_tasks:
            return ExecutionResult("Your task list is empty.")
        listed = "; ".join(t.title for t in open_tasks)
        return ExecutionResult(f"{len(open_tasks)} open: {listed}.", "task.list", open_tasks)

    # ---------------------------------------------------------------- relay #
    if name == "relay.toggle":
        # "toggle the light": flip whatever the stored state is.
        name = "relay.off" if device.relay_on else "relay.on"
    if name in {"relay.on", "relay.off"}:
        target = name == "relay.on"
        updated = await repo.patch(mongo.devices, Device, device_id, {"relay_on": target})
        final = updated or device
        await hub.publish(
            ev.RELAY_SET,
            {"on": target, "device": _dump(device_read(final))},
            device_id=device_id,
            origin=origin,
        )
        return ExecutionResult(f"Light turned {'on' if target else 'off'}.", name, final)

    # -------------------------------------------------------------- weather #
    if name == "weather.current":
        try:
            reading = await weather_service.get()
        except weather_service.WeatherError as exc:
            return ExecutionResult(f"I cannot get the weather: {exc}", None)
        summary = weather_service.spoken_summary(reading)
        # Push it to every client so the device can show its weather screen
        # without a separate request.
        await hub.publish(
            ev.WEATHER_UPDATED,
            _dump(reading),
            device_id=device_id,
            origin=origin,
            persist=False,
        )
        return ExecutionResult(summary, "weather.current", reading)

    # ---------------------------------------------------------------- clock #
    if name == "clock.time":
        return ExecutionResult(f"Server time is {iso(utcnow())}.", name)
    if name == "clock.date":
        return ExecutionResult(utcnow().strftime("Today is %A, %d %B %Y."), name)

    # --------------------------------------------------------------- device #
    if name == "device.battery":
        if device.battery_percent is None:
            return ExecutionResult("No battery reading yet; the device is on USB power.")
        return ExecutionResult(f"Battery at {device.battery_percent} percent.", name, device)

    if name == "device.status":
        read = device_read(device)
        state = "online" if read.online else "offline"
    # ----------------------------------------------------------- notes quiz #
    if name == "notes.quiz":
        notes = await repo.find_many(
            mongo.notes,
            Note,
            {"device_id": device_id},
            sort=[("created_at", repo.DESC)],
            limit=10,
        )
        if not notes:
            return ExecutionResult(
                "You haven't uploaded any study notes yet. Please upload a PDF or document on the Study Notes page first.",
                "notes.quiz",
            )

        topic = str(entities.get("topic") or entities.get("title") or "").strip().lower()
        target_note = notes[0]
        if topic:
            for n in notes:
                if topic in n.title.lower() or topic in n.text.lower():
                    target_note = n
                    break

        if not quiz_service.available():
            return ExecutionResult(
                f"Groq API connection is required to quiz from '{target_note.title}'. Please ensure GROQ_API_KEY is active in .env.",
                "notes.quiz",
            )

        # Generate 1 question grounded strictly in the note
        questions = await quiz_service.generate_questions(
            target_note.text, count=1, difficulty="mixed", style="open"
        )
        if not questions:
            questions = await quiz_service.generate_questions(
                target_note.text, count=1, difficulty="mixed", style="mixed"
            )

        if not questions:
            return ExecutionResult(
                f"I couldn't generate a question from '{target_note.title}'. Try uploading a note with more text.",
                "notes.quiz",
            )

        q = questions[0]
        conversation.remember_quiz(device_id, target_note.id, target_note.title, q.question, q.answer)
        reply = f"📝 Question from {target_note.title}:\n{q.question}"
        if q.options:
            reply += "\n\n" + "\n".join(f"{chr(65 + i)}) {opt}" for i, opt in enumerate(q.options))
        reply += "\n\n💡 Speak or type your answer, and I will evaluate it and suggest your next step!"

        return ExecutionResult(
            reply,
            "notes.quiz",
            {
                "note_id": target_note.id,
                "note_title": target_note.title,
                "question": q.question,
                "answer": q.answer,
            },
        )

    return ExecutionResult(intent.reply or "", None)


def _human_seconds(total: int) -> str:
    hours, rem = divmod(max(total, 0), 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"
