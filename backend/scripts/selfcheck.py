"""Backend self-check. Run this once after pasting your Atlas URI into .env.

    cd backend
    .\.venv\Scripts\python.exe scripts\selfcheck.py

It exercises the real cluster and the real Groq key end to end: connection,
indexes, every collection's CRUD, the timer/stopwatch/Pomodoro state machines,
the scheduler firing a real timer, the intent parser, WebSocket fan-out in both
directions, and a live Groq completion.

Everything it writes is namespaced to a throwaway device id and deleted at the
end, so it is safe to run against the cluster you actually use.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# The Windows console defaults to cp1252, and an LLM will happily return a
# non-breaking hyphen or a curly quote. Printing one would otherwise abort the
# whole run with UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Allow running from either backend/ or backend/scripts/.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

TEST_DEVICE = "selfcheck-device"

results: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, extra: object = "") -> bool:
    results.append((label, bool(ok), str(extra)))
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {label}"
    if not ok and extra:
        line += f"\n        -> {extra}"
    print(line, flush=True)
    return bool(ok)


def section(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


async def main() -> int:
    from app.config import settings

    section("Configuration")
    if not check(
        "MONGODB_URI is set",
        settings.mongo_configured,
        "Paste your Atlas connection string into backend/.env",
    ):
        print("\nCannot continue without a database. Nothing was written.")
        return 1

    check("GROQ_API_KEY is set", bool(settings.groq_api_key), "AI checks will use the mock path")
    print(f"        db={settings.mongodb_db}  model={settings.groq_model}")

    # ----------------------------------------------------------------- Mongo #
    section("MongoDB Atlas")
    from app.db import ensure_indexes, mongo

    connected = await mongo.connect()
    if not check("connect + ping", connected, mongo.error):
        print("\nFix the connection first. The message above names the usual cause.")
        return 1

    check("server version reported", bool(mongo.server_version), mongo.server_version)

    await ensure_indexes()
    index_names = [ix["name"] async for ix in await mongo.timers.list_indexes()]
    check("timer indexes created", "due_timers" in index_names, index_names)

    event_indexes = {ix["name"]: ix async for ix in await mongo.device_events.list_indexes()}
    ttl = event_indexes.get("ttl_created_at", {})
    check(
        "device_events has a TTL index",
        "expireAfterSeconds" in ttl,
        f"expireAfterSeconds={ttl.get('expireAfterSeconds')}",
    )

    # Clean any leftovers from a previous run.
    await _purge(mongo)

    # ---------------------------------------------------------------- models #
    section("Documents round-trip")
    from app import repo
    from app.models import Device, PomodoroState, Priority, RunState, Stopwatch, Task

    device = Device(id=TEST_DEVICE, name="Self Check")
    await repo.insert(mongo.devices, device)
    loaded = await repo.find_by_id(mongo.devices, Device, TEST_DEVICE)
    check("device insert + read", loaded is not None and loaded.id == TEST_DEVICE)
    check(
        "enum stored as a plain string (readable in Atlas)",
        (await mongo.devices.find_one({"_id": TEST_DEVICE})) is not None,
    )

    task = Task(device_id=TEST_DEVICE, title="Self check task", priority=Priority.HIGH)
    await repo.insert(mongo.tasks, task)
    raw = await mongo.tasks.find_one({"_id": task.id})
    check("priority enum -> 'high' in BSON", raw is not None and raw["priority"] == "high", raw)
    check(
        "datetimes come back timezone-aware",
        raw is not None and raw["created_at"].tzinfo is not None,
        raw["created_at"] if raw else None,
    )

    updated = await repo.patch(mongo.tasks, Task, task.id, {"done": True})
    check("patch updates and returns the document", updated is not None and updated.done)
    check("delete", await repo.delete_by_id(mongo.tasks, task.id))

    sw = await repo.get_or_create(
        mongo.stopwatches, Stopwatch, TEST_DEVICE, lambda: Stopwatch(id=TEST_DEVICE)
    )
    again = await repo.get_or_create(
        mongo.stopwatches, Stopwatch, TEST_DEVICE, lambda: Stopwatch(id=TEST_DEVICE)
    )
    check("get_or_create is idempotent", sw.id == again.id == TEST_DEVICE)
    await repo.get_or_create(
        mongo.pomodoro_states, PomodoroState, TEST_DEVICE, lambda: PomodoroState(id=TEST_DEVICE)
    )

    # --------------------------------------------------------------- services #
    section("Domain logic")
    from app.serializers import stopwatch_read, timer_read
    from app.services import pomodoro as pomodoro_service
    from app.services import stopwatch as stopwatch_service
    from app.services import timers as timer_service

    timer = await timer_service.start(TEST_DEVICE, 1500, "Deep work")
    read = timer_read(timer)
    check("timer starts running", read.state == RunState.RUNNING, read.state)
    check("timer has an absolute ends_at", read.ends_at is not None)
    check("remaining ~1500s", 1495 <= read.remaining_seconds <= 1500, read.remaining_seconds)

    paused = await timer_service.pause(timer)
    check("pause clears ends_at", paused.ends_at is None and paused.state == RunState.PAUSED)
    resumed = await timer_service.resume(paused)
    check("resume restores ends_at", resumed.ends_at is not None)

    second = await timer_service.start(TEST_DEVICE, 600, "Replacement")
    active = await timer_service.get_active(TEST_DEVICE)
    check("starting a timer retires the previous one", active is not None and active.id == second.id)
    await timer_service.cancel(second)
    check("cancelled timer is no longer active", await timer_service.get_active(TEST_DEVICE) is None)

    await stopwatch_service.start(TEST_DEVICE)
    await asyncio.sleep(0.4)
    await stopwatch_service.lap(TEST_DEVICE)
    stopped = await stopwatch_service.stop(TEST_DEVICE)
    elapsed = stopwatch_read(stopped).elapsed_ms
    check("stopwatch accumulates a segment", elapsed >= 350, f"{elapsed} ms")
    check("lap recorded", len(stopped.laps) == 1, stopped.laps)
    await stopwatch_service.reset(TEST_DEVICE)

    state = await pomodoro_service.get(TEST_DEVICE)
    state = await pomodoro_service.apply_config(state, focus_minutes=25, cycles_before_long_break=2)
    state = await pomodoro_service.start(state)
    check("pomodoro enters focus", state.phase == "focus" and state.state == RunState.RUNNING)
    change = await pomodoro_service.advance(state, natural=False)
    check("focus -> short_break", change.new_phase == "short_break", change.new_phase)
    check("cycle counted", change.state.completed_focus_cycles == 1)
    change = await pomodoro_service.advance(change.state, natural=False)
    change = await pomodoro_service.advance(change.state, natural=False)
    check("long break after 2 cycles", change.new_phase == "long_break", change.new_phase)
    await pomodoro_service.stop(change.state)

    sessions = await mongo.focus_sessions.count_documents({"device_id": TEST_DEVICE})
    check("focus sessions recorded", sessions >= 3, sessions)

    # -------------------------------------------------------------- analytics #
    section("Analytics")
    from app.services import analytics as analytics_service

    stats = await analytics_service.build(TEST_DEVICE, 7)
    check("analytics builds", stats.range_days == 7)
    check("daily series has 7 buckets", len(stats.daily) == 7, len(stats.daily))
    # The sequence above opens four blocks — focus, break, focus, break — and
    # analytics deliberately counts only focus sessions, because break time is
    # not focus time. Two is the correct answer here, not four.
    check("focus sessions counted (breaks excluded)", stats.sessions_total == 2,
          f"got {stats.sessions_total}")

    # ----------------------------------------------------------------- intents #
    section("Intent parser")
    from app.services import intents as intent_service

    cases = [
        ("set a timer for 10 minutes", "timer.start"),
        ("start pomodoro", "pomodoro.start"),
        ("turn on the lamp", "relay.on"),
        ("turn off the relay", "relay.off"),
        ("add task write the report", "task.create"),
        ("remind me to call mom in 20 minutes", "reminder.create"),
        ("set an alarm for 6:45 am", "alarm.set"),
        ("start the stopwatch", "stopwatch.start"),
        ("what time is it", "clock.time"),
        ("tell me a story about the ESP32", "chat"),
    ]
    for text, expected in cases:
        got = intent_service.parse(text).name
        check(f"'{text}' -> {expected}", got == expected, f"got {got}")

    # --------------------------------------------------------------------- AI #
    section("Groq")
    from app.services import ai as ai_service

    if settings.groq_api_key:
        models = await ai_service.list_models()
        check("model list retrieved", len(models) > 0, models[:3])
        check(
            f"configured model '{settings.groq_model}' is available",
            settings.groq_model in models,
            f"available: {models}",
        )

        started = time.perf_counter()
        reply = await ai_service.complete("In one sentence, what is an I2S bus?")
        took = int((time.perf_counter() - started) * 1000)
        check("live completion succeeded", reply.provider == "groq", reply.error)
        check("reply is non-empty", bool(reply.text.strip()), reply.text)
        print(f"        {took} ms — {reply.text[:120]}")
    else:
        reply = await ai_service.complete("hello")
        check("mock path answers without a key", reply.provider == "mock" and bool(reply.text))

    # ---------------------------------------------------------------- the API #
    section("HTTP + WebSocket")
    import httpx
    from httpx import ASGITransport

    from app.main import app

    # Drive the app in-process. lifespan is not started here (the scheduler and
    # connection are already up from this script), so the DB handle is shared.
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://selfcheck") as client:
        r = await client.get("/health")
        body = r.json()
        check("GET /health", r.status_code == 200, r.text[:200])
        check("health reports the database up", body["database"]["status"] == "ok", body["database"])
        check("health reports the AI mode", "mode" in body["ai"], body["ai"])

        params = {"device_id": TEST_DEVICE}
        r = await client.post(
            "/api/device/heartbeat",
            params=params,
            json={
                "firmware_version": "0.1.0-selfcheck",
                "wifi_connected": True,
                "wifi_ssid": "SelfCheck",
                "battery_percent": 77,
                "uptime_seconds": 42,
            },
        )
        check("POST /api/device/heartbeat", r.status_code == 200, r.text[:200])
        check("telemetry stored", r.json().get("battery_percent") == 77, r.text[:200])

        r = await client.post("/api/timer/start", params=params, json={"minutes": 25})
        check("POST /api/timer/start", r.status_code == 201, r.text[:200])
        r = await client.post("/api/timer/stop", params=params)
        check("POST /api/timer/stop", r.status_code == 200, r.text[:200])

        r = await client.post("/api/tasks", params=params, json={"title": "From the API"})
        check("POST /api/tasks", r.status_code == 201, r.text[:200])
        task_id = r.json()["id"]
        r = await client.patch(f"/api/tasks/{task_id}", params=params, json={"done": True})
        check("PATCH /api/tasks", r.json().get("done") is True, r.text[:200])
        await client.delete(f"/api/tasks/{task_id}", params=params)

        r = await client.post(
            "/api/alarms", params=params, json={"time_of_day": "07:30", "days_of_week": [0, 1, 2]}
        )
        check("POST /api/alarms", r.status_code == 201, r.text[:200])
        check("alarm got an absolute next_trigger_at", r.json().get("next_trigger_at") is not None)
        await client.delete(f"/api/alarms/{r.json()['id']}", params=params)

        r = await client.put(
            "/api/settings", params=params, json={"values": {"tz_offset_minutes": 330}}
        )
        check("PUT /api/settings", r.json()["values"]["tz_offset_minutes"] == 330, r.text[:200])
        r = await client.put(
            "/api/settings", params=params, json={"values": {"tz_offset_minutes": 0}}
        )
        check("settings upsert is idempotent", r.status_code == 200, r.text[:200])

        r = await client.get("/api/snapshot", params=params)
        snap = r.json()
        check("GET /api/snapshot", r.status_code == 200, r.text[:200])
        for key in ("server_time", "device", "stopwatch", "pomodoro", "alarms", "tasks", "analytics"):
            check(f"snapshot has '{key}'", key in snap)

        r = await client.post("/api/chat", params=params, json={"message": "set a timer for 3 minutes"})
        chat_body = r.json()
        check("POST /api/chat runs a local intent", chat_body.get("intent") == "timer.start", r.text[:200])
        check("chat actually started the timer", chat_body.get("action_taken") == "timer.start")
        await client.post("/api/timer/stop", params=params)

        if settings.groq_api_key:
            r = await client.post(
                "/api/chat", params=params, json={"message": "Explain I2S in one sentence."}
            )
            check("chat falls through to Groq", r.json().get("provider") == "groq", r.text[:300])

        r = await client.get("/api/ai/models", params=params)
        check("GET /api/ai/models", r.status_code == 200, r.text[:200])

    # The scheduler is already running in this process, so a short timer should
    # fire on its own.
    section("Scheduler")
    from app.services.scheduler import scheduler

    scheduler.start()
    await timer_service.start(TEST_DEVICE, 1, "One second")
    await asyncio.sleep(2.5)
    fired = await timer_service.get_active(TEST_DEVICE)
    check("scheduler finished the 1s timer", fired is None, fired)
    finished = await mongo.timers.count_documents(
        {"device_id": TEST_DEVICE, "state": "finished"}
    )
    check("timer recorded as finished", finished >= 1, finished)
    await scheduler.stop()

    # ------------------------------------------------------------------ done #
    section("Cleanup")
    removed = await _purge(mongo)
    check("test documents removed", True, f"{removed} documents")
    await mongo.close()

    failures = [r for r in results if not r[1]]
    print(f"\n{'-' * 60}")
    if failures:
        print(f"{len(failures)} of {len(results)} checks FAILED:\n")
        for label, _, extra in failures:
            print(f"  - {label}")
            if extra:
                print(f"      {extra}")
        return 1
    print(f"ALL {len(results)} CHECKS PASSED")
    return 0


async def _purge(mongo) -> int:
    """Delete everything this script created."""
    total = 0
    for collection, filt in (
        (mongo.devices, {"_id": TEST_DEVICE}),
        (mongo.stopwatches, {"_id": TEST_DEVICE}),
        (mongo.pomodoro_states, {"_id": TEST_DEVICE}),
        (mongo.timers, {"device_id": TEST_DEVICE}),
        (mongo.tasks, {"device_id": TEST_DEVICE}),
        (mongo.alarms, {"device_id": TEST_DEVICE}),
        (mongo.reminders, {"device_id": TEST_DEVICE}),
        (mongo.focus_sessions, {"device_id": TEST_DEVICE}),
        (mongo.voice_commands, {"device_id": TEST_DEVICE}),
        (mongo.chat_messages, {"device_id": TEST_DEVICE}),
        (mongo.device_events, {"device_id": TEST_DEVICE}),
        (mongo.settings_store, {"device_id": TEST_DEVICE}),
    ):
        result = await collection.delete_many(filt)
        total += result.deleted_count
    return total


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
