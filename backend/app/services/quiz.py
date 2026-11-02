"""Generate exam-style questions from a note's text, and grade free answers.

Both calls go to Groq directly (not ai.complete(), whose system prompt forces
two-sentence spoken replies). Questions are grounded strictly in the uploaded
text so the quiz tests the user's own material, not the model's world knowledge.

Everything degrades safely: if Groq is unreachable or returns junk, the caller
gets an empty list or a neutral grade rather than an exception, because a study
tool that crashes mid-revision is worse than one that says "try again".
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ..config import settings

log = logging.getLogger(__name__)

# The note text can be long; cap what we send so one huge PDF cannot blow the
# token budget. ~12k characters is a few thousand tokens, comfortably within the
# model's window while leaving room for the questions.
_MAX_CONTEXT_CHARS = 12_000


@dataclass
class QuizQuestion:
    question: str
    answer: str  # the reference answer, from the notes — not shown until graded
    options: list[str] = field(default_factory=list)  # for multiple-choice; empty = open
    hint: str = ""


@dataclass
class Grade:
    correct: bool
    score: float  # 0..1, so "partially right" is possible on open questions
    feedback: str
    reference: str


def available() -> bool:
    return settings.ai_live


async def _chat(messages: list[dict[str, str]], *, max_tokens: int, temperature: float) -> str:
    """One Groq chat call returning the message content, or "" on any failure."""
    url = f"{settings.groq_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": settings.groq_model,
        "messages": messages,
        "max_completion_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 400 and "response_format" in response.text:
                # Older/smaller models may not support JSON mode; retry without it.
                payload.pop("response_format", None)
                response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            log.warning("[quiz] Groq HTTP %s: %s", response.status_code, response.text[:200])
            return ""
        return (response.json()["choices"][0]["message"].get("content") or "").strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("[quiz] Groq call failed: %s", exc)
        return ""


def _parse_json(text: str) -> Optional[Any]:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Models sometimes wrap JSON in prose or a ```json fence. Salvage it.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


async def generate_questions(
    note_text: str,
    *,
    count: int = 5,
    difficulty: str = "mixed",
    style: str = "mixed",
    exclude: Optional[list[str]] = None,
) -> list[QuizQuestion]:
    """Make `count` exam questions grounded in `note_text`.

    style: "mcq" (multiple choice), "open" (short answer), or "mixed".
    exclude: optional list of previously asked question strings to avoid repeating.
    Returns [] if the AI is unavailable or returns nothing usable.
    """
    if not available():
        return []

    context = note_text[:_MAX_CONTEXT_CHARS]
    style_rule = {
        "mcq": "Every question must be multiple-choice with exactly 4 options.",
        "open": "Every question must be short-answer (no options).",
    }.get(style, "Mix multiple-choice (4 options) and short-answer questions.")

    exclude_clause = ""
    if exclude:
        recent_excluded = [q.strip() for q in exclude if q.strip()][-15:]
        if recent_excluded:
            bullets = "\n".join(f"- {q}" for q in recent_excluded)
            exclude_clause = (
                f"\nCRITICAL: DO NOT repeat or rephrase any of these previously asked questions:\n{bullets}\n"
                "Generate completely DIFFERENT questions from other parts of the notes."
            )

    system = (
        "You are an exam tutor. Write quiz questions that test ONLY the material in "
        "the provided notes — never outside knowledge. Each question must be "
        "answerable from the notes alone. Return STRICT JSON: "
        '{"questions":[{"question":str,"answer":str,"options":[str,...],"hint":str}]}. '
        "For short-answer questions use an empty options array. 'answer' is the "
        "correct answer taken from the notes. 'hint' is one short nudge. "
        f"{style_rule} Produce exactly {count} questions at {difficulty} difficulty. "
        f"Keep questions self-contained and clear when read aloud.{exclude_clause}"
    )
    user = f"NOTES:\n\n{context}\n\nGenerate the quiz now as JSON."

    content = await _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=1800,
        temperature=0.5 if exclude else 0.4,
    )
    data = _parse_json(content)
    if not isinstance(data, dict):
        return []

    raw = data.get("questions")
    if not isinstance(raw, list):
        return []

    def _norm(s: str) -> str:
        return "".join(c.lower() for c in s if c.isalnum())

    exclude_norms = [_norm(x) for x in (exclude or []) if _norm(x)]

    questions: list[QuizQuestion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question") or "").strip()
        a = str(item.get("answer") or "").strip()
        if not q or not a:
            continue
        q_norm = _norm(q)
        if exclude_norms and any(
            ex == q_norm or (len(ex) > 15 and ex in q_norm) or (len(q_norm) > 15 and q_norm in ex)
            for ex in exclude_norms
        ):
            continue
        options = [str(o).strip() for o in (item.get("options") or []) if str(o).strip()]
        questions.append(
            QuizQuestion(question=q, answer=a, options=options, hint=str(item.get("hint") or "").strip())
        )
    return questions[:count]


async def grade_answer(question: str, reference: str, user_answer: str, note_text: str = "") -> Grade:
    """Judge a free-form answer against the reference, leniently on wording.

    Falls back to a plain string comparison if the AI is unavailable, so grading
    still works offline for exact answers.
    """
    user_answer = (user_answer or "").strip()
    if not user_answer:
        return Grade(False, 0.0, "No answer given.", reference)

    if not available():
        hit = user_answer.lower() in reference.lower() or reference.lower() in user_answer.lower()
        return Grade(
            hit, 1.0 if hit else 0.0,
            "Correct." if hit else f"The expected answer was: {reference}", reference,
        )

    system = (
        "You grade a student's answer against a reference answer for an exam-prep "
        "quiz. Be fair about wording, synonyms and partial credit — judge meaning, "
        "not exact text. Return STRICT JSON: "
        '{"correct":bool,"score":number from 0 to 1,"feedback":str}. '
        "feedback is one or two short, encouraging sentences; if wrong, state the "
        "correct answer. Keep it brief enough to read aloud."
    )
    user = (
        f"QUESTION: {question}\n"
        f"REFERENCE ANSWER: {reference}\n"
        f"STUDENT ANSWER: {user_answer}\n\n"
        "Grade it as JSON."
    )
    content = await _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=300,
        temperature=0.1,
    )
    data = _parse_json(content)
    if not isinstance(data, dict):
        # The model is up but gave junk; do not block the user — mark neutral.
        return Grade(False, 0.0, f"Couldn't grade that automatically. Expected: {reference}", reference)

    score = data.get("score")
    try:
        score = max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        score = 1.0 if bool(data.get("correct")) else 0.0
    return Grade(
        correct=bool(data.get("correct")),
        score=score,
        feedback=str(data.get("feedback") or "").strip() or "Graded.",
        reference=reference,
    )


async def get_notes_context(device_id: str, query: str = "") -> str:
    """Fetch recent uploaded study notes to augment AI chat with user notes context."""
    from .. import repo
    from ..db import mongo
    from ..models import Note

    notes = await repo.find_many(
        mongo.notes,
        Note,
        {"device_id": device_id},
        sort=[("created_at", repo.DESC)],
        limit=5,
    )
    if not notes:
        return ""

    # Check if the query refers to a specific note
    target = notes[0]
    query_low = query.lower()
    for n in notes:
        if n.title.lower() in query_low or any(
            w in n.title.lower() for w in query_low.split() if len(w) > 3
        ):
            target = n
            break

    context = f"User has {len(notes)} uploaded study note(s): {', '.join(n.title for n in notes)}.\n"
    context += f"Active Note: {target.title} ({target.kind})\nContent excerpt:\n{target.text[:8000]}"
    return context

