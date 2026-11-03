"""Pomodoro cycle logic.

A small state machine: focus -> short break -> focus -> ... and a long break every
`cycles_before_long_break` completed focus blocks. Each block is recorded as a
FocusSession document, which is what the analytics endpoint aggregates over.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from .. import repo
from ..db import mongo
from ..models import FocusSession, PomodoroPhase, PomodoroState, RunState, SessionKind, User
from ..utils import as_utc, in_seconds, seconds_until, utcnow


@dataclass
class PhaseChange:
    state: PomodoroState
    previous_phase: str
    new_phase: str
    closed_session: Optional[FocusSession] = None
    completed_naturally: bool = False


async def get(device_id: str) -> PomodoroState:
    return await repo.get_or_create(
        mongo.pomodoro_states, PomodoroState, device_id, lambda: PomodoroState(id=device_id)
    )


def phase_seconds(state: PomodoroState, phase: str) -> int:
    if phase == PomodoroPhase.FOCUS:
        return state.focus_minutes * 60
    if phase == PomodoroPhase.SHORT_BREAK:
        return state.short_break_minutes * 60
    if phase == PomodoroPhase.LONG_BREAK:
        return state.long_break_minutes * 60
    return 0


def _session_kind(phase: str) -> str:
    return (
        SessionKind.POMODORO_FOCUS.value
        if phase == PomodoroPhase.FOCUS
        else SessionKind.POMODORO_BREAK.value
    )


async def _save(device_id: str, changes: dict) -> PomodoroState:
    changes["updated_at"] = utcnow()
    updated = await repo.patch(mongo.pomodoro_states, PomodoroState, device_id, changes)
    return updated or await get(device_id)


async def apply_config(
    state: PomodoroState,
    *,
    focus_minutes: Optional[int] = None,
    short_break_minutes: Optional[int] = None,
    long_break_minutes: Optional[int] = None,
    cycles_before_long_break: Optional[int] = None,
) -> PomodoroState:
    changes: dict = {}
    if focus_minutes is not None:
        changes["focus_minutes"] = focus_minutes
    if short_break_minutes is not None:
        changes["short_break_minutes"] = short_break_minutes
    if long_break_minutes is not None:
        changes["long_break_minutes"] = long_break_minutes
    if cycles_before_long_break is not None:
        changes["cycles_before_long_break"] = cycles_before_long_break
    if not changes:
        return state
    return await _save(state.id, changes)


async def _open_session(
    state: PomodoroState, phase: str, user: Optional[User] = None
) -> FocusSession:
    if not user:
        user_doc = await mongo.users.find_one({"device_id": state.id})
        if user_doc:
            user = User.model_validate(user_doc)

    session = FocusSession(
        device_id=state.id,
        user_id=user.id if user else None,
        username=user.username if user else None,
        kind=_session_kind(phase),
        planned_seconds=phase_seconds(state, phase),
        started_at=utcnow(),
    )
    await repo.insert(mongo.focus_sessions, session)
    return session


async def _close_session(state: PomodoroState, *, completed: bool) -> Optional[FocusSession]:
    if not state.current_session_id:
        return None

    session = await repo.find_by_id(mongo.focus_sessions, FocusSession, state.current_session_id)
    if session is None:
        return None

    now = utcnow()
    started = as_utc(session.started_at) or now
    elapsed = int((now - started).total_seconds())
    # A paused block should not count paused wall-clock time as focus.
    if state.state == RunState.PAUSED and state.remaining_seconds is not None:
        elapsed = max(session.planned_seconds - state.remaining_seconds, 0)

    actual = max(min(elapsed, session.planned_seconds or elapsed), 0)
    updated = await repo.patch(
        mongo.focus_sessions,
        FocusSession,
        session.id,
        {"actual_seconds": actual, "completed": completed, "ended_at": now},
    )
    return updated or session


async def start(state: PomodoroState) -> PomodoroState:
    """Begin (or restart) the cycle at a focus block."""
    await _close_session(state, completed=False)

    now = utcnow()
    focus_total = phase_seconds(state, PomodoroPhase.FOCUS.value)
    state = await _save(
        state.id,
        {
            "phase": PomodoroPhase.FOCUS.value,
            "state": RunState.RUNNING.value,
            "ends_at": now + timedelta(seconds=focus_total),
            "remaining_seconds": None,
            "current_session_id": None,
        },
    )

    session = await _open_session(state, PomodoroPhase.FOCUS.value)
    return await _save(state.id, {"current_session_id": session.id})


async def pause(state: PomodoroState) -> PomodoroState:
    if state.state != RunState.RUNNING:
        return state
    return await _save(
        state.id,
        {
            "remaining_seconds": seconds_until(state.ends_at),
            "state": RunState.PAUSED.value,
            "ends_at": None,
        },
    )


async def resume(state: PomodoroState) -> PomodoroState:
    if state.state != RunState.PAUSED:
        return state
    remaining = max(state.remaining_seconds or 0, 1)
    return await _save(
        state.id,
        {
            "state": RunState.RUNNING.value,
            "ends_at": in_seconds(remaining),
            "remaining_seconds": None,
        },
    )


async def stop(state: PomodoroState) -> PomodoroState:
    await _close_session(state, completed=False)
    return await _save(
        state.id,
        {
            "phase": PomodoroPhase.IDLE.value,
            "state": RunState.IDLE.value,
            "ends_at": None,
            "remaining_seconds": None,
            "current_session_id": None,
        },
    )


async def reset_cycles(state: PomodoroState) -> PomodoroState:
    return await _save(state.id, {"completed_focus_cycles": 0})


def next_phase_from(previous: str, completed_cycles: int, cycles_per_long: int) -> str:
    """Phase that follows `previous`, given cycles already completed."""
    if previous == PomodoroPhase.FOCUS:
        if cycles_per_long > 0 and completed_cycles % cycles_per_long == 0:
            return PomodoroPhase.LONG_BREAK.value
        return PomodoroPhase.SHORT_BREAK.value
    return PomodoroPhase.FOCUS.value


async def advance(state: PomodoroState, *, natural: bool) -> PhaseChange:
    """Close the current block and start the next one."""
    previous = state.phase
    closed = await _close_session(state, completed=natural)

    cycles = state.completed_focus_cycles
    if previous == PomodoroPhase.FOCUS:
        cycles += 1

    upcoming = next_phase_from(previous, cycles, state.cycles_before_long_break)
    now = utcnow()
    total = phase_seconds(state, upcoming)

    state = await _save(
        state.id,
        {
            "completed_focus_cycles": cycles,
            "phase": upcoming,
            "state": RunState.RUNNING.value,
            "ends_at": now + timedelta(seconds=total),
            "remaining_seconds": None,
            "current_session_id": None,
        },
    )

    session = await _open_session(state, upcoming)
    state = await _save(state.id, {"current_session_id": session.id})

    return PhaseChange(
        state=state,
        previous_phase=previous,
        new_phase=upcoming,
        closed_session=closed,
        completed_naturally=natural,
    )


def is_due(state: PomodoroState) -> bool:
    if state.state != RunState.RUNNING:
        return False
    ends = as_utc(state.ends_at)
    return ends is not None and ends <= utcnow()


async def running_states() -> list[PomodoroState]:
    return await repo.find_many(
        mongo.pomodoro_states,
        PomodoroState,
        {"state": RunState.RUNNING.value, "ends_at": {"$lte": utcnow()}},
        limit=50,
    )
