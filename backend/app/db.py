"""MongoDB Atlas connection, indexes and first-run seed.

Uses PyMongo's native async API (`AsyncMongoClient`). Motor reached end of life in
May 2026 and MongoDB now points all new async work here, so there is no reason to
take that dependency.

Because the driver is genuinely async, endpoints are async all the way down. The
awkward tradeoff the SQLite version carried — synchronous sessions called from
async handlers — is gone.

Failure policy: a missing or unreachable Atlas cluster does **not** crash the
process. `/health` reports `database: "down"` with the reason, and the API returns
503 on data endpoints. Starting up and explaining the problem beats dying on
import when the cause is usually one wrong character in a connection string.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pymongo import AsyncMongoClient, ASCENDING, DESCENDING
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from .config import settings

log = logging.getLogger(__name__)

# Collection names, in one place so a typo is a NameError not a silent new
# collection. Mongo creates collections on first write, which is convenient right
# up until "device_evnets" quietly starts collecting your data.
USERS = "users"
DEVICES = "devices"
TIMERS = "timers"
STOPWATCHES = "stopwatches"
ALARMS = "alarms"
REMINDERS = "reminders"
TASKS = "tasks"
POMODORO_STATES = "pomodoro_states"
FOCUS_SESSIONS = "focus_sessions"
VOICE_COMMANDS = "voice_commands"
DEVICE_EVENTS = "device_events"
SETTINGS = "settings"
CHAT_MESSAGES = "chat_messages"
NOTES = "notes"
QUIZ_SESSIONS = "quiz_sessions"
COMPETITION_INVITES = "competition_invites"

ALL_COLLECTIONS = (
    USERS, DEVICES, TIMERS, STOPWATCHES, ALARMS, REMINDERS, TASKS,
    POMODORO_STATES, FOCUS_SESSIONS, VOICE_COMMANDS, DEVICE_EVENTS,
    SETTINGS, CHAT_MESSAGES, NOTES, QUIZ_SESSIONS, COMPETITION_INVITES,
)


class Mongo:
    """Holds the client and reports why it is not working, if it is not."""

    def __init__(self) -> None:
        self._client: Optional[AsyncMongoClient] = None
        self._db: Optional[AsyncDatabase] = None
        self.ready: bool = False
        self.error: Optional[str] = None
        self.server_version: Optional[str] = None

    # ----------------------------------------------------------- lifecycle #
    async def connect(self) -> bool:
        if not settings.mongo_configured:
            self.error = (
                "MONGODB_URI is not set. Put your Atlas connection string in "
                "backend/.env — see .env.example."
            )
            log.error("[mongo] %s", self.error)
            return False

        try:
            self._client = AsyncMongoClient(
                settings.mongodb_uri,
                # Aware UTC datetimes on read. Without this every timestamp comes
                # back naive and every comparison becomes a latent bug.
                tz_aware=True,
                serverSelectionTimeoutMS=settings.mongo_timeout_ms,
                connectTimeoutMS=settings.mongo_timeout_ms,
                appname="ai-deskmate-backend",
                retryWrites=True,
            )
            info = await self._client.admin.command("ping")
            if not info.get("ok"):
                raise PyMongoError(f"ping returned {info!r}")

            build = await self._client.admin.command("buildInfo")
            self.server_version = build.get("version")

            self._db = self._client[settings.mongodb_db]
            self.ready = True
            self.error = None
            log.info(
                "[mongo] connected to '%s' (MongoDB %s)",
                settings.mongodb_db,
                self.server_version,
            )
            return True
        except Exception as exc:  # noqa: BLE001 - report, do not crash
            self.ready = False
            self.error = _explain(exc)
            log.error("[mongo] connection failed: %s", self.error)
            await self.close()
            return False

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass
        self._client = None
        self._db = None
        self.ready = False

    # -------------------------------------------------------- collections #
    @property
    def database(self) -> AsyncDatabase:
        if self._db is None:
            raise RuntimeError(self.error or "MongoDB is not connected")
        return self._db

    def collection(self, name: str) -> AsyncCollection:
        return self.database[name]

    @property
    def users(self) -> AsyncCollection:
        return self.collection(USERS)

    @property
    def devices(self) -> AsyncCollection:
        return self.collection(DEVICES)

    @property
    def timers(self) -> AsyncCollection:
        return self.collection(TIMERS)

    @property
    def stopwatches(self) -> AsyncCollection:
        return self.collection(STOPWATCHES)

    @property
    def alarms(self) -> AsyncCollection:
        return self.collection(ALARMS)

    @property
    def reminders(self) -> AsyncCollection:
        return self.collection(REMINDERS)

    @property
    def tasks(self) -> AsyncCollection:
        return self.collection(TASKS)

    @property
    def pomodoro_states(self) -> AsyncCollection:
        return self.collection(POMODORO_STATES)

    @property
    def focus_sessions(self) -> AsyncCollection:
        return self.collection(FOCUS_SESSIONS)

    @property
    def voice_commands(self) -> AsyncCollection:
        return self.collection(VOICE_COMMANDS)

    @property
    def device_events(self) -> AsyncCollection:
        return self.collection(DEVICE_EVENTS)

    @property
    def settings_store(self) -> AsyncCollection:
        return self.collection(SETTINGS)

    @property
    def chat_messages(self) -> AsyncCollection:
        return self.collection(CHAT_MESSAGES)

    @property
    def notes(self) -> AsyncCollection:
        return self.collection(NOTES)

    @property
    def quiz_sessions(self) -> AsyncCollection:
        return self.collection(QUIZ_SESSIONS)

    @property
    def competition_invites(self) -> AsyncCollection:
        return self.collection(COMPETITION_INVITES)

    # ------------------------------------------------------------- health #
    async def health(self) -> dict[str, Any]:
        if not self.ready:
            return {"status": "down", "detail": self.error}
        try:
            await self._client.admin.command("ping")  # type: ignore[union-attr]
            return {
                "status": "ok",
                "database": settings.mongodb_db,
                "server_version": self.server_version,
            }
        except Exception as exc:  # noqa: BLE001
            self.ready = False
            self.error = _explain(exc)
            return {"status": "down", "detail": self.error}


mongo = Mongo()


def _explain(exc: Exception) -> str:
    """Turn driver errors into something that points at the actual fix."""
    text = str(exc)
    lowered = text.lower()

    if "authentication failed" in lowered or "bad auth" in lowered:
        return (
            "Atlas rejected the credentials. Check the username and password in "
            "MONGODB_URI, and remember the password must be percent-encoded if it "
            "contains @ : / ? # [ ] or %."
        )
    if "timed out" in lowered or "serverselectiontimeout" in lowered:
        return (
            "Could not reach the cluster before timing out. The usual cause is "
            "Atlas Network Access: add your current IP (or 0.0.0.0/0 for a "
            "throwaway demo cluster) under Security > Network Access. "
            f"Driver said: {text[:200]}"
        )
    if "dns" in lowered or "srv" in lowered:
        return (
            "Could not resolve the mongodb+srv host. Check the cluster hostname, "
            f"and that dnspython is installed. Driver said: {text[:200]}"
        )
    if "invalid uri" in lowered or "scheme" in lowered:
        return (
            "MONGODB_URI is malformed. It should start with mongodb+srv:// for "
            f"Atlas. Driver said: {text[:200]}"
        )
    return text[:400]


# --------------------------------------------------------------------------- #
# Indexes
# --------------------------------------------------------------------------- #


async def ensure_indexes() -> None:
    """Idempotent. Safe to run on every startup."""
    if not mongo.ready:
        return

    try:
        await mongo.users.create_index([("email", ASCENDING)], unique=True, name="email_unique")

        await mongo.timers.create_index(
            [("device_id", ASCENDING), ("state", ASCENDING)], name="device_state"
        )
        await mongo.timers.create_index(
            [("device_id", ASCENDING), ("created_at", DESCENDING)], name="device_recent"
        )
        # The scheduler asks "which running timers are already due?" every second.
        await mongo.timers.create_index(
            [("state", ASCENDING), ("ends_at", ASCENDING)], name="due_timers"
        )

        await mongo.alarms.create_index([("device_id", ASCENDING)], name="device")
        await mongo.alarms.create_index(
            [("enabled", ASCENDING), ("next_trigger_at", ASCENDING)], name="due_alarms"
        )

        await mongo.reminders.create_index(
            [("device_id", ASCENDING), ("remind_at", ASCENDING)], name="device_schedule"
        )
        await mongo.reminders.create_index(
            [("done", ASCENDING), ("notified_at", ASCENDING), ("remind_at", ASCENDING)],
            name="due_reminders",
        )

        await mongo.tasks.create_index(
            [("device_id", ASCENDING), ("done", ASCENDING), ("created_at", DESCENDING)],
            name="device_open",
        )

        await mongo.pomodoro_states.create_index([("state", ASCENDING)], name="running")

        await mongo.focus_sessions.create_index(
            [("device_id", ASCENDING), ("kind", ASCENDING), ("started_at", DESCENDING)],
            name="device_kind_recent",
        )

        await mongo.voice_commands.create_index(
            [("device_id", ASCENDING), ("created_at", DESCENDING)], name="device_recent"
        )

        await mongo.chat_messages.create_index(
            [("device_id", ASCENDING), ("created_at", DESCENDING)], name="device_recent"
        )

        await mongo.settings_store.create_index(
            [("device_id", ASCENDING), ("key", ASCENDING)], unique=True, name="device_key_unique"
        )

        await mongo.notes.create_index(
            [("device_id", ASCENDING), ("created_at", DESCENDING)], name="device_recent"
        )
        await mongo.quiz_sessions.create_index(
            [("device_id", ASCENDING), ("created_at", DESCENDING)], name="device_recent"
        )

        # Event log: recent-first reads, plus a TTL so it cannot fill a 512 MB
        # free-tier cluster. Mongo's TTL monitor sweeps about once a minute.
        await mongo.device_events.create_index(
            [("device_id", ASCENDING), ("created_at", DESCENDING)], name="device_recent"
        )
        await mongo.device_events.create_index(
            [("created_at", ASCENDING)],
            name="ttl_created_at",
            expireAfterSeconds=settings.event_retention_days * 86400,
        )

        log.info("[mongo] indexes ensured (events expire after %sd)",
                 settings.event_retention_days)
    except Exception as exc:  # noqa: BLE001
        # An existing index with different options raises. Worth knowing about,
        # not worth refusing to start over.
        log.warning("[mongo] index creation issue: %s", _explain(exc))


# --------------------------------------------------------------------------- #
# Seed
# --------------------------------------------------------------------------- #


async def seed() -> None:
    """Create the default user, device and a few tasks on a clean cluster."""
    if not mongo.ready or not settings.seed_demo_data:
        return

    from .models import Device, FocusSession, PomodoroState, Priority, SessionKind, Stopwatch, Task, User
    from .utils import utcnow

    try:
        # 1. Primary user: Alok (linked to deskmate-01)
        user_doc = await mongo.users.find_one({"username": "alok"})
        if user_doc is None:
            old_doc = await mongo.users.find_one({"email": settings.default_user_email})
            if old_doc:
                await mongo.users.update_one(
                    {"_id": old_doc["_id"]},
                    {
                        "$set": {
                            "username": "alok",
                            "display_name": "Alok Gupta",
                            "competition_code": "ALOK-2026",
                            "device_id": settings.default_device_id,
                            "avatar": "⚡",
                        }
                    },
                )
                user_id = old_doc["_id"]
            else:
                user = User(
                    username="alok",
                    email=settings.default_user_email,
                    display_name="Alok Patel",
                    competition_code="ALOK-2026",
                    device_id=settings.default_device_id,
                    avatar="⚡",
                )
                await mongo.users.insert_one(user.to_doc())
                user_id = user.id
            log.info("[mongo] seeded user alok (ALOK-2026)")
        else:
            user_id = user_doc["_id"]
            if not user_doc.get("competition_code"):
                await mongo.users.update_one({"_id": user_id}, {"$set": {"competition_code": "ALOK-2026", "device_id": settings.default_device_id}})

        device_id = settings.default_device_id
        dev_doc = await mongo.devices.find_one({"_id": device_id})
        if dev_doc is None:
            device = Device(
                id=device_id,
                user_id=user_id,
                name=settings.default_device_name,
                competition_code="ALOK-2026",
                competitive_unlocked=True,
            )
            await mongo.devices.insert_one(device.to_doc())
            log.info("[mongo] seeded device %s", device_id)
        elif not dev_doc.get("competition_code"):
            await mongo.devices.update_one({"_id": device_id}, {"$set": {"competition_code": "ALOK-2026", "competitive_unlocked": True}})

        # 2. Secondary peer user: Sarah Connor (SARA-8840)
        sarah_doc = await mongo.users.find_one({"username": "sarah"})
        if sarah_doc is None:
            sarah_user = User(
                username="sarah",
                email="sarah@deskmate.local",
                display_name="Sarah Connor",
                competition_code="SARA-8840",
                device_id="dev-sarah",
                avatar="👩‍🎓",
                status="Studying Physics",
            )
            await mongo.users.insert_one(sarah_user.to_doc())

            # Sarah's device
            if await mongo.devices.find_one({"_id": "dev-sarah"}) is None:
                sarah_dev = Device(
                    id="dev-sarah",
                    user_id=sarah_user.id,
                    name="Sarah's DeskMate",
                    competition_code="SARA-8840",
                    competitive_unlocked=True,
                )
                await mongo.devices.insert_one(sarah_dev.to_doc())

            # Sarah's real completed tasks & focus session for genuine XP
            sarah_tasks = [
                Task(
                    device_id="dev-sarah",
                    title="Solve Thermodynamics MCQs",
                    priority=Priority.HIGH,
                    list_type="competitive",
                    xp=60,
                    done=True,
                    completed_at=utcnow(),
                ),
                Task(
                    device_id="dev-sarah",
                    title="Review Optics Diagram Chapter 5",
                    priority=Priority.NORMAL,
                    list_type="competitive",
                    xp=50,
                    done=True,
                    completed_at=utcnow(),
                ),
            ]
            await mongo.tasks.insert_many([t.to_doc() for t in sarah_tasks])

            # Sarah's completed focus session (25 mins = 25 XP + 10 XP = 35 XP)
            sarah_focus = FocusSession(
                device_id="dev-sarah",
                kind=SessionKind.POMODORO_FOCUS,
                planned_seconds=1500,
                actual_seconds=1500,
                completed=True,
                started_at=utcnow(),
                ended_at=utcnow(),
            )
            await mongo.focus_sessions.insert_one(sarah_focus.to_doc())
            log.info("[mongo] seeded peer account sarah (SARA-8840)")

        # Singletons keyed by device id, so this is an idempotent no-op on rerun.
        if await mongo.stopwatches.find_one({"_id": device_id}) is None:
            await mongo.stopwatches.insert_one(Stopwatch(id=device_id).to_doc())
        if await mongo.pomodoro_states.find_one({"_id": device_id}) is None:
            await mongo.pomodoro_states.insert_one(PomodoroState(id=device_id).to_doc())

        if await mongo.tasks.count_documents({"device_id": device_id}, limit=1) == 0:
            starters = [
                Task(
                    device_id=device_id,
                    title="Confirm MAX98357 VIN rail (5V vs 3V3)",
                    priority=Priority.HIGH,
                    notes="Outstanding item #1 from the hardware validation doc.",
                    list_type="personal",
                ),
                Task(
                    device_id=device_id,
                    title="Complete Stage 16 Hardware Challenge",
                    priority=Priority.HIGH,
                    notes="Earn +75 XP for completing hardware verification.",
                    list_type="competitive",
                    xp=75,
                ),
                Task(
                    device_id=device_id,
                    title="Study 20 Minutes of Quantum Physics Notes",
                    priority=Priority.HIGH,
                    list_type="competitive",
                    xp=50,
                ),
            ]
            await mongo.tasks.insert_many([task.to_doc() for task in starters])
            log.info("[mongo] seeded %d starter tasks", len(starters))
    except Exception as exc:  # noqa: BLE001
        log.warning("[mongo] seed skipped: %s", _explain(exc))


async def init_db() -> None:
    connected = await mongo.connect()
    if connected:
        await ensure_indexes()
        await seed()
