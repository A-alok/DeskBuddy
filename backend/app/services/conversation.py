"""Short-term conversational memory, per device.

The intent parser is stateless: it only sees the current sentence. That is fine
for "add a task buy milk" but useless for the follow-ups people actually say —
"remove the last one", "delete it", "mark that done". Those words only mean
something relative to what was just said.

This module remembers, per device, the last thing the user created or acted on,
so the parser can resolve "it" / "that" / "the last task". It is deliberately
tiny: an in-memory dict, one slot per device, with a time-to-live. It is a
convenience layer, not storage — the tasks, reminders and alarms themselves live
in MongoDB. If the backend restarts, the user simply names the thing again.

Why in-memory and not a DB field: this is throwaway state that is only useful for
a few seconds after a command. Writing it to Mongo on every turn would add a
round trip to the hot path for something a restart is allowed to forget.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, Optional

# What kind of thing the last command touched. "the last task" resolves only
# against a task; "it"/"that" resolve against whatever the most recent one was.
RefKind = Literal["task", "reminder", "alarm", "timer"]

# References older than this are ignored. Long enough for a natural follow-up,
# short enough that an unrelated command minutes later is never misread as "it".
_TTL_SECONDS = 180.0


@dataclass
class LastRef:
    kind: RefKind
    entity_id: str
    label: str  # human text, e.g. the task title — only for the spoken reply
    at: float  # monotonic timestamp, for the TTL


# device_id -> LastRef. Bounded by the number of devices (here, one).
_last: dict[str, LastRef] = {}


def remember(device_id: str, kind: RefKind, entity_id: str, label: str = "") -> None:
    """Record the thing the current command created or acted on."""
    _last[device_id] = LastRef(kind=kind, entity_id=entity_id, label=label, at=time.monotonic())


def recall(device_id: str, kind: Optional[RefKind] = None) -> Optional[LastRef]:
    """The last remembered reference, or None if there is none, it expired, or
    a specific kind was asked for and the last one is a different kind."""
    ref = _last.get(device_id)
    if ref is None:
        return None
    if time.monotonic() - ref.at > _TTL_SECONDS:
        _last.pop(device_id, None)
        return None
    if kind is not None and ref.kind != kind:
        return None
    return ref


def clear(device_id: str) -> None:
    _last.pop(device_id, None)


@dataclass
class QuizRef:
    note_id: str
    note_title: str
    question: str
    reference_answer: str
    at: float  # monotonic timestamp


@dataclass
class QuizAnswerRecord:
    question: str
    user_answer: str
    is_correct: bool
    score: float  # 0.0 to 1.0
    feedback: str
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class QuizSession:
    note_id: str
    note_title: str
    asked_questions: list[str] = field(default_factory=list)
    records: list[QuizAnswerRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)

    @property
    def total_answered(self) -> int:
        return len(self.records)

    @property
    def correct_count(self) -> int:
        return sum(1 for r in self.records if r.is_correct)


_last_quiz: dict[str, QuizRef] = {}
_quiz_sessions: dict[str, QuizSession] = {}


def get_or_create_session(device_id: str, note_id: str, note_title: str) -> QuizSession:
    sess = _quiz_sessions.get(device_id)
    now = time.monotonic()
    if sess and sess.note_id == note_id and (now - sess.last_activity < 600.0):
        sess.last_activity = now
        return sess
    sess = QuizSession(note_id=note_id, note_title=note_title, started_at=now, last_activity=now)
    _quiz_sessions[device_id] = sess
    return sess


def get_quiz_session(device_id: str, max_age_seconds: float = 600.0) -> Optional[QuizSession]:
    sess = _quiz_sessions.get(device_id)
    if sess is None:
        return None
    if time.monotonic() - sess.last_activity > max_age_seconds:
        _quiz_sessions.pop(device_id, None)
        return None
    return sess


def record_quiz_answer(
    device_id: str,
    question: str,
    user_answer: str,
    is_correct: bool,
    score: float,
    feedback: str,
) -> None:
    sess = _quiz_sessions.get(device_id)
    if sess:
        sess.records.append(
            QuizAnswerRecord(
                question=question,
                user_answer=user_answer,
                is_correct=is_correct,
                score=score,
                feedback=feedback,
            )
        )
        sess.last_activity = time.monotonic()


def _normalize_q(q: str) -> str:
    return "".join(c.lower() for c in q if c.isalnum())


def was_question_asked(device_id: str, question: str) -> bool:
    sess = _quiz_sessions.get(device_id)
    if not sess or not sess.asked_questions:
        return False
    norm = _normalize_q(question)
    if not norm:
        return False
    return any(
        _normalize_q(asked) == norm
        or (len(norm) > 15 and norm in _normalize_q(asked))
        or (len(_normalize_q(asked)) > 15 and _normalize_q(asked) in norm)
        for asked in sess.asked_questions
    )


def get_asked_questions(device_id: str) -> list[str]:
    sess = _quiz_sessions.get(device_id)
    return list(sess.asked_questions) if sess else []


def remember_quiz(
    device_id: str, note_id: str, note_title: str, question: str, reference_answer: str
) -> None:
    now = time.monotonic()
    _last_quiz[device_id] = QuizRef(
        note_id=note_id,
        note_title=note_title,
        question=question,
        reference_answer=reference_answer,
        at=now,
    )
    sess = get_or_create_session(device_id, note_id, note_title)
    norm = _normalize_q(question)
    if not any(_normalize_q(asked) == norm for asked in sess.asked_questions):
        sess.asked_questions.append(question)
    sess.last_activity = now


def recall_quiz(device_id: str, max_age_seconds: float = 300.0) -> Optional[QuizRef]:
    ref = _last_quiz.get(device_id)
    if ref is None:
        return None
    if time.monotonic() - ref.at > max_age_seconds:
        _last_quiz.pop(device_id, None)
        return None
    return ref


def end_quiz_session(device_id: str) -> Optional[QuizSession]:
    _last_quiz.pop(device_id, None)
    return _quiz_sessions.pop(device_id, None)


def clear_quiz(device_id: str) -> None:
    _last_quiz.pop(device_id, None)


