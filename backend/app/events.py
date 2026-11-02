"""Canonical event names for the WebSocket channel.

The ESP32 firmware, the backend and the dashboard all agree on these strings.
Keep them stable; add new ones rather than renaming.
"""

from __future__ import annotations

# --- connection / presence -------------------------------------------------- #
HELLO = "hello"                        # server -> client, first frame after connect
DEVICE_ONLINE = "device.online"
DEVICE_OFFLINE = "device.offline"
DEVICE_HEARTBEAT = "device.heartbeat"  # device -> server (telemetry)
DEVICE_STATUS = "device.status"        # server -> clients (full snapshot)
PING = "ping"
PONG = "pong"

# --- timer ------------------------------------------------------------------ #
TIMER_STARTED = "timer.started"
TIMER_PAUSED = "timer.paused"
TIMER_RESUMED = "timer.resumed"
TIMER_CANCELLED = "timer.cancelled"
TIMER_FINISHED = "timer.finished"

# --- stopwatch -------------------------------------------------------------- #
STOPWATCH_STARTED = "stopwatch.started"
STOPWATCH_STOPPED = "stopwatch.stopped"
STOPWATCH_LAPPED = "stopwatch.lapped"
STOPWATCH_RESET = "stopwatch.reset"

# --- alarms ----------------------------------------------------------------- #
ALARM_CREATED = "alarm.created"
ALARM_UPDATED = "alarm.updated"
ALARM_DELETED = "alarm.deleted"
ALARM_TRIGGERED = "alarm.triggered"

# --- pomodoro --------------------------------------------------------------- #
POMODORO_STARTED = "pomodoro.started"
POMODORO_PAUSED = "pomodoro.paused"
POMODORO_RESUMED = "pomodoro.resumed"
POMODORO_STOPPED = "pomodoro.stopped"
POMODORO_PHASE_CHANGED = "pomodoro.phase_changed"
POMODORO_SKIPPED = "pomodoro.skipped"

# --- tasks ------------------------------------------------------------------ #
TASK_CREATED = "task.created"
TASK_UPDATED = "task.updated"
TASK_DELETED = "task.deleted"

# --- reminders -------------------------------------------------------------- #
REMINDER_CREATED = "reminder.created"
REMINDER_UPDATED = "reminder.updated"
REMINDER_DELETED = "reminder.deleted"
REMINDER_DUE = "reminder.due"

# --- relay / hardware ------------------------------------------------------- #
RELAY_SET = "relay.set"
SCREEN_CHANGED = "screen.changed"
TOUCH = "touch"
WIFI_CONFIG_SET = "device.wifi_set"

# --- voice / AI ------------------------------------------------------------- #
VOICE_COMMAND = "voice.command"
VOICE_LISTENING = "voice.listening"
VOICE_TRANSCRIBED = "voice.transcribed"
CHAT_MESSAGE = "chat.message"

# --- study notes / quiz ----------------------------------------------------- #
NOTE_CREATED = "note.created"
NOTE_DELETED = "note.deleted"
QUIZ_STARTED = "quiz.started"
QUIZ_GRADED = "quiz.graded"

# --- weather ---------------------------------------------------------------- #
WEATHER_UPDATED = "weather.updated"

# --- settings --------------------------------------------------------------- #
SETTINGS_UPDATED = "settings.updated"

# --- competition invites ---------------------------------------------------- #
COMPETITION_INVITE = "competition.invite"
COMPETITION_ACCEPTED = "competition.accepted"
COMPETITION_DECLINED = "competition.declined"

# Events we do not persist to device_events (too chatty to be useful).
EPHEMERAL: frozenset[str] = frozenset(
    {HELLO, PING, PONG, DEVICE_HEARTBEAT, DEVICE_STATUS}
)
