"""MongoDB document models.

Plain pydantic, not an ODM. The driver speaks dicts; pydantic validates them at
the boundary. That keeps the mapping visible instead of hidden behind metaclass
magic, and it means a malformed document in Atlas fails loudly at read time.

Conventions
-----------
* `_id` is our own uuid4 hex, exposed as `id`. No ObjectId ever reaches the API,
  so ids stay identical to what earlier clients already store.
* Singleton-per-device documents (stopwatch, pomodoro state) use the device id as
  `_id`, which makes "get or create" a single idempotent upsert.
* `use_enum_values=True`: fields hold the plain string after validation, so BSON
  stores `"running"` rather than an unencodable Enum, and documents are readable
  in the Atlas UI. Compare with `==`, never `is` — the runtime value is a str.
* Every datetime is UTC. The client is opened with `tz_aware=True`, so reads come
  back timezone-aware and the naive-datetime bug class simply does not exist here.
  BSON stores millisecond precision; microseconds are truncated.

Design note: every countdown-shaped object stores an absolute UTC `ends_at`
rather than a remaining duration. Device, backend and dashboard each compute
"remaining" locally from that instant, so nothing has to stream per-second ticks
and no restart can shift a deadline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- #
# Enums — values match the API and the firmware's run_state.h
# --------------------------------------------------------------------------- #


class RunState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class PomodoroPhase(str, Enum):
    IDLE = "idle"
    FOCUS = "focus"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class CommandSource(str, Enum):
    VOICE = "voice"
    TOUCH = "touch"
    DASHBOARD = "dashboard"
    MOBILE = "mobile"
    # The firmware itself, as opposed to a person touching it. The WebSocket
    # layer publishes device-originated frames with origin="device"; without this
    # member `CommandSource("device")` raised and the event log recorded them as
    # "system", making firmware activity indistinguishable from the scheduler's.
    DEVICE = "device"
    SYSTEM = "system"


class SessionKind(str, Enum):
    POMODORO_FOCUS = "pomodoro_focus"
    POMODORO_BREAK = "pomodoro_break"
    TIMER = "timer"
    MANUAL = "manual"


class InviteStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #


class Document(BaseModel):
    """Shared config for everything stored in Mongo."""

    model_config = ConfigDict(
        populate_by_name=True,   # accept both "id" and "_id"
        use_enum_values=True,    # store plain strings, not Enum objects
        extra="ignore",          # tolerate fields added by a newer version
    )

    def to_doc(self) -> dict[str, Any]:
        """Dict ready for insert/replace, with `id` renamed back to `_id`."""
        return self.model_dump(by_alias=True)

    def changes(self) -> dict[str, Any]:
        """Dict for `$set`, excluding the immutable `_id`."""
        data = self.model_dump(by_alias=True)
        data.pop("_id", None)
        return data


# --------------------------------------------------------------------------- #
# Collections
# --------------------------------------------------------------------------- #


class User(Document):
    id: str = Field(default_factory=new_id, alias="_id")
    email: Optional[str] = None
    username: str = "alok"
    display_name: str = "Demo User"
    password_hash: Optional[str] = None
    auth_token: Optional[str] = None
    competition_code: str = ""
    competitors: list[str] = Field(default_factory=list)
    device_id: str = "deskmate-01"
    avatar: str = "⚡"
    status: str = "Active"
    is_demo: bool = False
    hidden: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Device(Document):
    # Human-readable stable id, e.g. "deskmate-01" — the ESP32 reports this.
    id: str = Field(alias="_id")
    user_id: Optional[str] = None
    name: str = "AI DeskMate"
    firmware_version: Optional[str] = None

    # Liveness / telemetry, refreshed by the device heartbeat.
    last_seen_at: Optional[datetime] = None
    wifi_connected: bool = False
    wifi_ssid: Optional[str] = None
    wifi_rssi: Optional[int] = None
    ip_address: Optional[str] = None
    battery_percent: Optional[int] = None
    battery_voltage: Optional[float] = None
    charging: bool = False
    free_heap_bytes: Optional[int] = None
    uptime_seconds: Optional[int] = None

    # Actuators / UI state mirrored from firmware.
    relay_on: bool = False
    current_screen: str = "home"

    # Configured Wi-Fi credentials stored in database
    wifi_config_ssid: Optional[str] = None
    wifi_config_password: Optional[str] = None
    wifi_configured_at: Optional[datetime] = None

    # Competitive access & friend codes
    competition_code: Optional[str] = None
    competitors: list[str] = Field(default_factory=list)
    referral_code: Optional[str] = None
    competitive_unlocked: bool = True
    referred_by: Optional[str] = None
    referrals_count: int = 0

    created_at: datetime = Field(default_factory=utcnow)


class Timer(Document):
    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    label: str = "Timer"
    duration_seconds: int = 0
    state: RunState = RunState.IDLE

    # Absolute UTC instant the timer fires. None while idle/paused.
    ends_at: Optional[datetime] = None
    # Seconds left at the moment it was paused.
    remaining_seconds: Optional[int] = None

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Stopwatch(Document):
    """One document per device; `_id` is the device id."""

    id: str = Field(alias="_id")
    state: RunState = RunState.IDLE
    # Absolute instant the current run segment began. None while stopped.
    started_at: Optional[datetime] = None
    # Milliseconds banked from previous run segments.
    accumulated_ms: int = 0
    laps: list[int] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def device_id(self) -> str:
        return self.id


class Alarm(Document):
    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    label: str = "Alarm"
    # Local wall-clock time on the device, 24h "HH:MM".
    time_of_day: str = "07:00"
    # 0 = Monday ... 6 = Sunday. Empty list means "once, next occurrence".
    days_of_week: list[int] = Field(default_factory=list)
    enabled: bool = True
    sound: str = "beep"
    last_triggered_at: Optional[datetime] = None
    # Absolute next fire time, recomputed whenever the alarm changes.
    next_trigger_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class Reminder(Document):
    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    text: str
    remind_at: datetime
    done: bool = False
    notified_at: Optional[datetime] = None
    source: CommandSource = CommandSource.DASHBOARD
    created_at: datetime = Field(default_factory=utcnow)


class Task(Document):
    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    title: str
    notes: Optional[str] = None
    priority: Priority = Priority.NORMAL
    done: bool = False
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    list_type: str = "personal"  # "personal" | "competitive"
    xp: int = 50  # XP awarded when completed (especially for competitive challenges)
    source: CommandSource = CommandSource.DASHBOARD
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PomodoroState(Document):
    """One document per device; `_id` is the device id."""

    id: str = Field(alias="_id")
    phase: PomodoroPhase = PomodoroPhase.IDLE
    state: RunState = RunState.IDLE
    focus_minutes: int = 25
    short_break_minutes: int = 5
    long_break_minutes: int = 15
    cycles_before_long_break: int = 4

    completed_focus_cycles: int = 0
    ends_at: Optional[datetime] = None
    remaining_seconds: Optional[int] = None
    current_session_id: Optional[str] = None
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def device_id(self) -> str:
        return self.id


class FocusSession(Document):
    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    kind: SessionKind = SessionKind.POMODORO_FOCUS
    planned_seconds: int = 0
    actual_seconds: int = 0
    completed: bool = False
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: Optional[datetime] = None


class VoiceCommand(Document):
    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    transcript: str
    intent: Optional[str] = None
    entities: dict[str, Any] = Field(default_factory=dict)
    response_text: Optional[str] = None
    handled_locally: bool = False
    source: CommandSource = CommandSource.VOICE
    latency_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow)


class DeviceEvent(Document):
    """Append-only event log. A TTL index on `created_at` expires these."""

    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    type: str
    origin: CommandSource = CommandSource.SYSTEM
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class Setting(Document):
    """`_id` is "<device_id>:<key>", which makes upserts idempotent for free."""

    id: str = Field(alias="_id")
    device_id: str
    key: str
    value: Any = None
    updated_at: datetime = Field(default_factory=utcnow)

    @staticmethod
    def make_id(device_id: str, key: str) -> str:
        return f"{device_id}:{key}"


class ChatMessage(Document):
    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    role: str = "user"  # user | assistant | system
    content: str
    source: CommandSource = CommandSource.DASHBOARD
    created_at: datetime = Field(default_factory=utcnow)


class Note(Document):
    """A study file the user uploaded for exam prep. We keep the extracted TEXT,
    not the original binary — same approach as the voice upload path."""

    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    title: str                      # usually the filename
    kind: str = "text"              # pdf | docx | xlsx | text — how it was read
    text: str = ""                  # extracted plain text, capped on upload
    char_count: int = 0
    source: CommandSource = CommandSource.DASHBOARD
    created_at: datetime = Field(default_factory=utcnow)


class QuizQuestionDoc(Document):
    """One question inside a quiz session. Embedded, not a separate collection."""

    question: str
    answer: str                     # reference answer, hidden until graded
    options: list[str] = Field(default_factory=list)  # empty = short-answer
    hint: str = ""
    user_answer: Optional[str] = None
    correct: Optional[bool] = None
    score: Optional[float] = None   # 0..1
    feedback: Optional[str] = None


class QuizSession(Document):
    """A quiz generated from one note, plus the user's progress through it."""

    id: str = Field(default_factory=new_id, alias="_id")
    device_id: str
    note_id: str
    note_title: str = ""
    questions: list[QuizQuestionDoc] = Field(default_factory=list)
    current_index: int = 0          # which question is being answered
    finished: bool = False
    correct_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CompetitionInvite(Document):
    id: str = Field(default_factory=new_id, alias="_id")
    sender_user_id: str
    sender_username: str
    sender_name: str
    sender_code: str
    sender_device_id: str
    sender_avatar: str = "⚡"

    recipient_user_id: str
    recipient_username: str
    recipient_name: str
    recipient_code: str
    recipient_device_id: str
    recipient_avatar: str = "🎓"

    status: InviteStatus = InviteStatus.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    responded_at: Optional[datetime] = None

