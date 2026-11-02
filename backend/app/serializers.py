"""Document -> API shape conversion, including the computed "remaining" fields.

These stay synchronous: they are pure functions over already-loaded documents, so
nothing here touches the database.
"""

from __future__ import annotations

from typing import Optional

from .config import settings
from .models import (
    Alarm,
    ChatMessage,
    Device,
    PomodoroPhase,
    PomodoroState,
    Reminder,
    RunState,
    Stopwatch,
    Note,
    QuizSession,
    Task,
    Timer,
    VoiceCommand,
)
from .realtime import hub
from .schemas import (
    AlarmRead,
    ChatMessageRead,
    DeviceRead,
    NoteRead,
    PomodoroRead,
    QuizQuestionRead,
    QuizSessionRead,
    ReminderRead,
    StopwatchRead,
    TaskRead,
    TimerRead,
    VoiceCommandRead,
)
from .utils import as_utc, seconds_until, utcnow


def device_read(device: Device) -> DeviceRead:
    last_seen = as_utc(device.last_seen_at)
    since: Optional[int] = None
    if last_seen is not None:
        since = int((utcnow() - last_seen).total_seconds())

    ws_connected = hub.device_connected(device.id)
    online = ws_connected or (
        since is not None and since <= settings.device_offline_after_seconds
    )

    return DeviceRead(
        id=device.id,
        name=device.name,
        firmware_version=device.firmware_version,
        online=online,
        websocket_connected=ws_connected,
        last_seen_at=last_seen,
        seconds_since_seen=since,
        wifi_connected=device.wifi_connected,
        wifi_ssid=device.wifi_ssid,
        wifi_rssi=device.wifi_rssi,
        ip_address=device.ip_address,
        battery_percent=device.battery_percent,
        battery_voltage=device.battery_voltage,
        charging=device.charging,
        free_heap_bytes=device.free_heap_bytes,
        uptime_seconds=device.uptime_seconds,
        relay_on=device.relay_on,
        current_screen=device.current_screen,
    )


def timer_remaining(timer: Timer) -> int:
    if timer.state == RunState.RUNNING:
        return seconds_until(timer.ends_at)
    if timer.state == RunState.PAUSED:
        return timer.remaining_seconds or 0
    if timer.state == RunState.IDLE:
        return timer.duration_seconds
    return 0


def timer_read(timer: Timer) -> TimerRead:
    return TimerRead(
        id=timer.id,
        device_id=timer.device_id,
        label=timer.label,
        duration_seconds=timer.duration_seconds,
        state=timer.state,
        ends_at=as_utc(timer.ends_at),
        remaining_seconds=timer_remaining(timer),
        started_at=as_utc(timer.started_at),
        finished_at=as_utc(timer.finished_at),
        created_at=as_utc(timer.created_at) or utcnow(),
        updated_at=as_utc(timer.updated_at) or utcnow(),
    )


def stopwatch_elapsed_ms(sw: Stopwatch) -> int:
    total = sw.accumulated_ms
    if sw.state == RunState.RUNNING and sw.started_at is not None:
        started = as_utc(sw.started_at)
        if started is not None:
            total += int((utcnow() - started).total_seconds() * 1000)
    return max(total, 0)


def stopwatch_read(sw: Stopwatch) -> StopwatchRead:
    return StopwatchRead(
        device_id=sw.id,
        state=sw.state,
        started_at=as_utc(sw.started_at),
        accumulated_ms=sw.accumulated_ms,
        elapsed_ms=stopwatch_elapsed_ms(sw),
        laps=list(sw.laps or []),
        updated_at=as_utc(sw.updated_at) or utcnow(),
    )


def pomodoro_phase_seconds(state: PomodoroState, phase: Optional[str] = None) -> int:
    phase = phase or state.phase
    if phase == PomodoroPhase.FOCUS:
        return state.focus_minutes * 60
    if phase == PomodoroPhase.SHORT_BREAK:
        return state.short_break_minutes * 60
    if phase == PomodoroPhase.LONG_BREAK:
        return state.long_break_minutes * 60
    return 0


def pomodoro_remaining(state: PomodoroState) -> int:
    if state.state == RunState.RUNNING:
        return seconds_until(state.ends_at)
    if state.state == RunState.PAUSED:
        return state.remaining_seconds or 0
    return 0


def pomodoro_read(state: PomodoroState) -> PomodoroRead:
    return PomodoroRead(
        device_id=state.id,
        phase=state.phase,
        state=state.state,
        focus_minutes=state.focus_minutes,
        short_break_minutes=state.short_break_minutes,
        long_break_minutes=state.long_break_minutes,
        cycles_before_long_break=state.cycles_before_long_break,
        completed_focus_cycles=state.completed_focus_cycles,
        ends_at=as_utc(state.ends_at),
        remaining_seconds=pomodoro_remaining(state),
        phase_total_seconds=pomodoro_phase_seconds(state),
        updated_at=as_utc(state.updated_at) or utcnow(),
    )


def alarm_read(alarm: Alarm) -> AlarmRead:
    next_at = as_utc(alarm.next_trigger_at)
    return AlarmRead(
        id=alarm.id,
        device_id=alarm.device_id,
        label=alarm.label,
        time_of_day=alarm.time_of_day,
        days_of_week=list(alarm.days_of_week or []),
        enabled=alarm.enabled,
        sound=alarm.sound,
        next_trigger_at=next_at,
        seconds_until_trigger=seconds_until(next_at) if next_at else None,
        last_triggered_at=as_utc(alarm.last_triggered_at),
        created_at=as_utc(alarm.created_at) or utcnow(),
    )


def reminder_read(reminder: Reminder) -> ReminderRead:
    remind_at = as_utc(reminder.remind_at) or utcnow()
    return ReminderRead(
        id=reminder.id,
        device_id=reminder.device_id,
        text=reminder.text,
        remind_at=remind_at,
        seconds_until=seconds_until(remind_at),
        done=reminder.done,
        notified_at=as_utc(reminder.notified_at),
        source=reminder.source,
        created_at=as_utc(reminder.created_at) or utcnow(),
    )


def task_read(task: Task) -> TaskRead:
    return TaskRead(
        id=task.id,
        device_id=task.device_id,
        title=task.title,
        notes=task.notes,
        priority=task.priority,
        done=task.done,
        due_at=as_utc(task.due_at),
        completed_at=as_utc(task.completed_at),
        list_type=getattr(task, "list_type", "personal") or "personal",
        xp=getattr(task, "xp", 50) or 50,
        source=task.source,
        created_at=as_utc(task.created_at) or utcnow(),
        updated_at=as_utc(task.updated_at) or utcnow(),
    )


def voice_command_read(cmd: VoiceCommand) -> VoiceCommandRead:
    return VoiceCommandRead(
        id=cmd.id,
        device_id=cmd.device_id,
        transcript=cmd.transcript,
        intent=cmd.intent,
        entities=dict(cmd.entities or {}),
        response_text=cmd.response_text,
        handled_locally=cmd.handled_locally,
        source=cmd.source,
        latency_ms=cmd.latency_ms,
        created_at=as_utc(cmd.created_at) or utcnow(),
    )


def chat_message_read(msg: ChatMessage) -> ChatMessageRead:
    return ChatMessageRead(
        id=msg.id,
        device_id=msg.device_id,
        role=msg.role,
        content=msg.content,
        source=msg.source,
        created_at=as_utc(msg.created_at) or utcnow(),
    )


def note_read(note: Note, *, include_text: bool = False) -> NoteRead:
    return NoteRead(
        id=note.id,
        device_id=note.device_id,
        title=note.title,
        kind=note.kind,
        char_count=note.char_count,
        text=note.text if include_text else None,
        source=note.source,
        created_at=as_utc(note.created_at) or utcnow(),
    )


def quiz_session_read(session: QuizSession) -> QuizSessionRead:
    questions: list[QuizQuestionRead] = []
    for index, q in enumerate(session.questions):
        graded = q.correct is not None
        # The reference answer is revealed only once a question has been graded,
        # and only for questions at or before where the user currently is — so
        # reading the session can never leak an upcoming answer.
        reveal = graded and index <= session.current_index
        questions.append(
            QuizQuestionRead(
                question=q.question,
                options=list(q.options or []),
                hint=q.hint,
                user_answer=q.user_answer,
                correct=q.correct,
                score=q.score,
                feedback=q.feedback,
                answer=q.answer if reveal else None,
            )
        )
    return QuizSessionRead(
        id=session.id,
        device_id=session.device_id,
        note_id=session.note_id,
        note_title=session.note_title,
        questions=questions,
        current_index=session.current_index,
        finished=session.finished,
        correct_count=session.correct_count,
        total=len(session.questions),
        created_at=as_utc(session.created_at) or utcnow(),
    )
