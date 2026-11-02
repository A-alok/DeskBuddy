"""Request and response shapes for the REST API.

Read models carry BOTH the absolute `ends_at` and a convenience
`remaining_seconds` snapshot. Clients should tick from `ends_at`;
`remaining_seconds` is only there to make curl output readable and to seed the
first render.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import CommandSource, PomodoroPhase, Priority, RunState, SessionKind


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# --------------------------------------------------------------------------- #
# Device
# --------------------------------------------------------------------------- #


class DeviceHeartbeat(BaseModel):
    firmware_version: Optional[str] = None
    wifi_connected: Optional[bool] = None
    wifi_ssid: Optional[str] = None
    wifi_rssi: Optional[int] = None
    ip_address: Optional[str] = None
    battery_percent: Optional[int] = Field(default=None, ge=0, le=100)
    battery_voltage: Optional[float] = Field(default=None, ge=0, le=6)
    charging: Optional[bool] = None
    free_heap_bytes: Optional[int] = Field(default=None, ge=0)
    uptime_seconds: Optional[int] = Field(default=None, ge=0)
    relay_on: Optional[bool] = None
    current_screen: Optional[str] = None


class DeviceRead(ApiModel):
    id: str
    name: str
    firmware_version: Optional[str] = None
    online: bool = False
    websocket_connected: bool = False
    last_seen_at: Optional[datetime] = None
    seconds_since_seen: Optional[int] = None
    wifi_connected: bool = False
    wifi_ssid: Optional[str] = None
    wifi_rssi: Optional[int] = None
    ip_address: Optional[str] = None
    battery_percent: Optional[int] = None
    battery_voltage: Optional[float] = None
    charging: bool = False
    free_heap_bytes: Optional[int] = None
    uptime_seconds: Optional[int] = None
    relay_on: bool = False
    current_screen: str = "home"


class RelayRequest(BaseModel):
    on: bool
    source: CommandSource = CommandSource.DASHBOARD


class ScreenRequest(BaseModel):
    screen: str = Field(min_length=1, max_length=32)


class WifiConfigRequest(BaseModel):
    ssid: str = Field(min_length=1, max_length=64)
    password: Optional[str] = Field(default="", max_length=64)


class WifiConfigRead(BaseModel):
    device_id: str
    ssid: str
    password_set: bool
    configured_at: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# Timer
# --------------------------------------------------------------------------- #


class TimerCreate(BaseModel):
    label: str = Field(default="Timer", max_length=64)
    hours: int = Field(default=0, ge=0, le=99)
    minutes: int = Field(default=0, ge=0, le=59)
    seconds: int = Field(default=0, ge=0, le=59)
    duration_seconds: Optional[int] = Field(default=None, ge=1, le=99 * 3600)
    source: CommandSource = CommandSource.DASHBOARD

    def total_seconds(self) -> int:
        if self.duration_seconds:
            return self.duration_seconds
        return self.hours * 3600 + self.minutes * 60 + self.seconds


class TimerRead(ApiModel):
    id: str
    device_id: str
    label: str
    duration_seconds: int
    state: RunState
    ends_at: Optional[datetime] = None
    remaining_seconds: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Stopwatch
# --------------------------------------------------------------------------- #


class StopwatchRead(ApiModel):
    device_id: str
    state: RunState
    started_at: Optional[datetime] = None
    accumulated_ms: int = 0
    elapsed_ms: int = 0
    laps: list[int] = Field(default_factory=list)
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Alarms
# --------------------------------------------------------------------------- #


class AlarmCreate(BaseModel):
    label: str = Field(default="Alarm", max_length=64)
    time_of_day: str = Field(default="07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days_of_week: list[int] = Field(default_factory=list)
    enabled: bool = True
    sound: str = "beep"

    @field_validator("days_of_week")
    @classmethod
    def _valid_days(cls, value: list[int]) -> list[int]:
        for day in value:
            if not 0 <= day <= 6:
                raise ValueError("days_of_week entries must be 0 (Mon) to 6 (Sun)")
        return sorted(set(value))


class AlarmUpdate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=64)
    time_of_day: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days_of_week: Optional[list[int]] = None
    enabled: Optional[bool] = None
    sound: Optional[str] = None


class AlarmRead(ApiModel):
    id: str
    device_id: str
    label: str
    time_of_day: str
    days_of_week: list[int] = Field(default_factory=list)
    enabled: bool
    sound: str
    next_trigger_at: Optional[datetime] = None
    seconds_until_trigger: Optional[int] = None
    last_triggered_at: Optional[datetime] = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Reminders
# --------------------------------------------------------------------------- #


class ReminderCreate(BaseModel):
    text: str = Field(min_length=1, max_length=280)
    remind_at: Optional[datetime] = None
    in_minutes: Optional[int] = Field(default=None, ge=1, le=60 * 24 * 365)
    source: CommandSource = CommandSource.DASHBOARD


class ReminderUpdate(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=280)
    remind_at: Optional[datetime] = None
    done: Optional[bool] = None


class ReminderRead(ApiModel):
    id: str
    device_id: str
    text: str
    remind_at: datetime
    seconds_until: int = 0
    done: bool
    notified_at: Optional[datetime] = None
    source: CommandSource
    created_at: datetime


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    notes: Optional[str] = Field(default=None, max_length=1000)
    priority: Priority = Priority.NORMAL
    due_at: Optional[datetime] = None
    list_type: str = Field(default="personal", description="personal or competitive")
    xp: int = Field(default=50, ge=10, le=500)
    source: CommandSource = CommandSource.DASHBOARD


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=140)
    notes: Optional[str] = Field(default=None, max_length=1000)
    priority: Optional[Priority] = None
    done: Optional[bool] = None
    due_at: Optional[datetime] = None
    list_type: Optional[str] = None
    xp: Optional[int] = None


class TaskRead(ApiModel):
    id: str
    device_id: str
    title: str
    notes: Optional[str] = None
    priority: Priority
    done: bool
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    list_type: str = "personal"
    xp: int = 50
    source: CommandSource
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Pomodoro
# --------------------------------------------------------------------------- #


class PomodoroConfig(BaseModel):
    focus_minutes: Optional[int] = Field(default=None, ge=1, le=180)
    short_break_minutes: Optional[int] = Field(default=None, ge=1, le=60)
    long_break_minutes: Optional[int] = Field(default=None, ge=1, le=120)
    cycles_before_long_break: Optional[int] = Field(default=None, ge=1, le=12)


class PomodoroStartRequest(PomodoroConfig):
    source: CommandSource = CommandSource.DASHBOARD


class PomodoroRead(ApiModel):
    device_id: str
    phase: PomodoroPhase
    state: RunState
    focus_minutes: int
    short_break_minutes: int
    long_break_minutes: int
    cycles_before_long_break: int
    completed_focus_cycles: int
    ends_at: Optional[datetime] = None
    remaining_seconds: int = 0
    phase_total_seconds: int = 0
    updated_at: datetime


class FocusSessionRead(ApiModel):
    id: str
    device_id: str
    kind: SessionKind
    planned_seconds: int
    actual_seconds: int
    completed: bool
    started_at: datetime
    ended_at: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# Voice / chat
# --------------------------------------------------------------------------- #


class VoiceCommandCreate(BaseModel):
    transcript: str = Field(min_length=1, max_length=500)
    source: CommandSource = CommandSource.VOICE
    latency_ms: Optional[int] = Field(default=None, ge=0)
    # When true the backend only logs it; the firmware already acted on it.
    handled_locally: bool = False


class VoiceCommandRead(ApiModel):
    id: str
    device_id: str
    transcript: str
    intent: Optional[str] = None
    entities: dict[str, Any] = Field(default_factory=dict)
    response_text: Optional[str] = None
    handled_locally: bool
    source: CommandSource
    latency_ms: Optional[int] = None
    created_at: datetime


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    source: CommandSource = CommandSource.DASHBOARD
    speak: bool = False


class ChatMessageRead(ApiModel):
    id: str
    device_id: str
    role: str
    content: str
    source: CommandSource
    created_at: datetime


class ChatResponse(BaseModel):
    reply: str
    intent: Optional[str] = None
    entities: dict[str, Any] = Field(default_factory=dict)
    action_taken: Optional[str] = None
    provider: str = "mock"
    messages: list[ChatMessageRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Analytics / settings
# --------------------------------------------------------------------------- #


class DailyPoint(BaseModel):
    date: str
    focus_minutes: int = 0
    sessions: int = 0
    tasks_completed: int = 0


class AnalyticsRead(BaseModel):
    range_days: int
    focus_minutes_today: int = 0
    focus_minutes_total: int = 0
    sessions_today: int = 0
    sessions_total: int = 0
    tasks_completed_today: int = 0
    tasks_open: int = 0
    tasks_completed_total: int = 0
    pomodoro_cycles_today: int = 0
    current_streak_days: int = 0
    voice_commands_total: int = 0
    daily: list[DailyPoint] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Weather
# --------------------------------------------------------------------------- #


class WeatherRead(BaseModel):
    """Current conditions, shaped for a 128x64 panel as much as for the web UI.

    `short` is a <=12 character condition label, because the OLED has to fit it
    beside a temperature. `stale` is true when the upstream call failed and this
    is a cached reading being served rather than nothing at all.
    """

    location: str
    country: str = ""
    latitude: float
    longitude: float
    observed_at: datetime
    fetched_at: datetime

    temperature: Optional[float] = None
    feels_like: Optional[float] = None
    humidity: Optional[int] = None
    wind_speed: Optional[float] = None
    precipitation: Optional[float] = None
    is_day: bool = True

    weather_code: Optional[int] = None
    description: str = "Unknown"
    short: str = "Unknown"

    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    precipitation_chance: Optional[int] = None
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None

    temperature_unit: str = "°C"
    wind_unit: str = "km/h"
    timezone: str = ""
    stale: bool = False


# --------------------------------------------------------------------------- #
# Voice transcription
# --------------------------------------------------------------------------- #


class TranscriptionRead(BaseModel):
    """Result of POST /api/voice/transcribe."""

    transcript: str
    reply: str
    intent: Optional[str] = None
    entities: dict[str, Any] = Field(default_factory=dict)
    action_taken: Optional[str] = None
    provider: str = "groq"
    model: Optional[str] = None
    audio_bytes: int = 0
    audio_seconds: Optional[float] = None
    transcribe_ms: Optional[int] = None
    total_ms: Optional[int] = None
    spoken: bool = False


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


class SettingsRead(BaseModel):
    device_id: str
    values: dict[str, Any] = Field(default_factory=dict)


class SnapshotRead(BaseModel):
    """Everything a client needs for a first paint, in one round trip."""

    server_time: datetime
    device: DeviceRead
    weather: Optional[WeatherRead] = None
    timer: Optional[TimerRead] = None
    timers: list[TimerRead] = Field(default_factory=list)
    stopwatch: StopwatchRead
    pomodoro: PomodoroRead
    alarms: list[AlarmRead] = Field(default_factory=list)
    reminders: list[ReminderRead] = Field(default_factory=list)
    tasks: list[TaskRead] = Field(default_factory=list)
    recent_commands: list[VoiceCommandRead] = Field(default_factory=list)
    analytics: AnalyticsRead
    settings: dict[str, Any] = Field(default_factory=dict)


class OkResponse(BaseModel):
    ok: bool = True
    detail: Optional[str] = None


# --------------------------------------------------------------------------- #
# Study notes & quizzes
# --------------------------------------------------------------------------- #


class NoteRead(ApiModel):
    id: str
    device_id: str
    title: str
    kind: str
    char_count: int
    # The full text is only sent on request (GET /notes/{id}); the list omits it
    # so a page of large PDFs stays small.
    text: Optional[str] = None
    source: CommandSource = CommandSource.DASHBOARD
    created_at: datetime


class QuizStartRequest(BaseModel):
    note_id: str
    count: int = Field(default=5, ge=1, le=15)
    difficulty: str = Field(default="mixed")  # easy | medium | hard | mixed
    style: str = Field(default="mixed")        # mcq | open | mixed


class QuizAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


class QuizQuestionRead(ApiModel):
    question: str
    options: list[str] = Field(default_factory=list)
    hint: str = ""
    # Grading fields, present only after this question is answered.
    user_answer: Optional[str] = None
    correct: Optional[bool] = None
    score: Optional[float] = None
    feedback: Optional[str] = None
    # The reference answer is withheld until the question has been graded, so a
    # peek at the API cannot reveal upcoming answers.
    answer: Optional[str] = None


class QuizSessionRead(ApiModel):
    id: str
    device_id: str
    note_id: str
    note_title: str
    questions: list[QuizQuestionRead] = Field(default_factory=list)
    current_index: int
    finished: bool
    correct_count: int
    total: int
    created_at: datetime


# --------------------------------------------------------------------------- #
# Competitive Learning
# --------------------------------------------------------------------------- #


class BadgeRead(ApiModel):
    id: str
    name: str
    description: str
    icon: str
    unlocked: bool
    unlocked_at: Optional[datetime] = None


class CompetitivePillarStats(ApiModel):
    xp: int
    details: dict[str, Any] = Field(default_factory=dict)


class CompetitiveSummaryRead(ApiModel):
    total_xp: int
    level: int
    current_level_xp: int
    next_level_xp: int
    progress_pct: int
    league: str  # Bronze | Silver | Gold | Platinum | Diamond
    rank: int
    streak_days: int
    unlocked: bool = True
    my_referral_code: str = ""
    competition_code: str = ""
    competitors: list[str] = Field(default_factory=list)
    referred_by: Optional[str] = None
    referrals_count: int = 0
    pomodoro: CompetitivePillarStats
    tasks: CompetitivePillarStats
    quizzes: CompetitivePillarStats
    badges: list[BadgeRead] = Field(default_factory=list)


class ReferralUnlockRequest(BaseModel):
    referral_code: str = Field(min_length=3, max_length=32)


class ReferralAccessRead(ApiModel):
    unlocked: bool
    my_referral_code: str
    referred_by: Optional[str] = None
    referrals_count: int = 0
    message: Optional[str] = None


class CompetitorAddRequest(BaseModel):
    competition_code: str = Field(min_length=3, max_length=32)


class CompetitorAddResponse(BaseModel):
    ok: bool = True
    message: str
    competitor_name: str
    competitor_code: str
    competitors: list[str] = Field(default_factory=list)


class CompetitionInviteRead(ApiModel):
    id: str
    sender_user_id: str
    sender_username: str
    sender_name: str
    sender_code: str
    sender_device_id: str
    sender_avatar: str
    recipient_user_id: str
    recipient_username: str
    recipient_name: str
    recipient_code: str
    recipient_device_id: str
    recipient_avatar: str
    status: str
    created_at: datetime
    responded_at: Optional[datetime] = None


class InvitesListRead(ApiModel):
    incoming: list[CompetitionInviteRead] = Field(default_factory=list)
    outgoing: list[CompetitionInviteRead] = Field(default_factory=list)


class ChallengeRequest(BaseModel):
    competition_code: str = Field(min_length=3, max_length=32)


class ChallengeResponse(BaseModel):
    ok: bool = True
    message: str
    invite: CompetitionInviteRead


class InviteActionResponse(BaseModel):
    ok: bool = True
    message: str
    competitor_name: Optional[str] = None
    competitor_code: Optional[str] = None


class LeaderboardEntry(ApiModel):
    rank: int
    name: str
    avatar: str
    league: str
    level: int
    total_xp: int
    streak_days: int
    is_user: bool = False
    status: str = "Active"
    competition_code: Optional[str] = None


class CompetitiveActivityItem(ApiModel):
    id: str
    kind: str  # pomodoro | task | quiz
    title: str
    description: str
    xp_earned: int
    timestamp: datetime


# --------------------------------------------------------------------------- #
# User Accounts & Auth
# --------------------------------------------------------------------------- #


class UserAccountRead(ApiModel):
    id: str
    username: str
    display_name: str
    competition_code: str
    device_id: str
    avatar: str = "⚡"
    status: str = "Active"
    competitors: list[str] = Field(default_factory=list)
    token: Optional[str] = None
    has_password: bool = False
    created_at: datetime


class LoginRequest(BaseModel):
    username: str
    password: Optional[str] = None


class RegisterRequest(BaseModel):
    username: str
    password: Optional[str] = None
    display_name: Optional[str] = None
    avatar: Optional[str] = "⚡"
    device_id: Optional[str] = None

