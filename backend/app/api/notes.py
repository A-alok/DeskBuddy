"""Study notes + AI quizzing with independent per-user data isolation."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from .. import events as ev
from .. import repo
from ..config import settings
from ..db import mongo
from ..deps import DeviceDep, UserDep
from ..models import CommandSource, Note, QuizQuestionDoc, QuizSession
from ..realtime import hub
from ..schemas import NoteRead, OkResponse, QuizAnswerRequest, QuizSessionRead, QuizStartRequest
from ..serializers import note_read, quiz_session_read
from ..services import extract as extract_service
from ..services import quiz as quiz_service
from ..utils import utcnow

router = APIRouter(tags=["study"])


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #


@router.get("/notes", response_model=list[NoteRead])
async def list_notes(
    device: DeviceDep, user: UserDep, limit: int = Query(default=50, ge=1, le=200)
) -> list[NoteRead]:
    filt: dict = {}
    if user:
        filt["$or"] = [
            {"user_id": user.id},
            {"username": user.username},
            {"device_id": user.device_id},
        ]
    else:
        filt["device_id"] = device.id

    notes = await repo.find_many(
        mongo.notes,
        Note,
        filt,
        sort=[("created_at", repo.DESC)],
        limit=limit,
    )
    return [note_read(n) for n in notes]


@router.get("/notes/{note_id}", response_model=NoteRead)
async def get_note(device: DeviceDep, user: UserDep, note_id: str) -> NoteRead:
    note = await repo.find_by_id(mongo.notes, Note, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    is_owner = (
        note.device_id == device.id
        or (user and (note.user_id == user.id or note.username == user.username))
        or (user and getattr(user, "device_id", None) == note.device_id)
    )
    if not is_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    return note_read(note, include_text=True)


@router.post("/notes/upload", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def upload_note(
    device: DeviceDep,
    user: UserDep,
    file: UploadFile = File(..., description="PDF, Word (.docx), Excel (.xlsx) or text file"),
) -> NoteRead:
    data = await file.read()
    if len(data) > settings.notes_max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is {len(data) // (1024 * 1024)} MB, over the "
            f"{settings.notes_max_upload_bytes // (1024 * 1024)} MB limit.",
        )

    try:
        extracted = extract_service.extract(
            file.filename or "note", data, max_chars=settings.notes_max_extract_chars
        )
    except extract_service.ExtractError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    title = (file.filename or "Untitled note").rsplit("/", 1)[-1]
    note = Note(
        device_id=device.id,
        user_id=user.id if user else None,
        username=user.username if user else None,
        title=title,
        kind=extracted.kind,
        text=extracted.text,
        char_count=len(extracted.text),
        source=CommandSource.DASHBOARD,
    )
    await repo.insert(mongo.notes, note)

    # Keep the user's collection bounded
    bound_filter = {"user_id": user.id} if user else {"device_id": device.id}
    existing = await repo.find_many(
        mongo.notes, Note, bound_filter, sort=[("created_at", repo.DESC)]
    )
    for old in existing[settings.notes_max_count :]:
        await repo.delete_by_id(mongo.notes, old.id)

    read = note_read(note)
    await hub.publish(ev.NOTE_CREATED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.delete("/notes/{note_id}", response_model=OkResponse)
async def delete_note(device: DeviceDep, user: UserDep, note_id: str) -> OkResponse:
    note = await repo.find_by_id(mongo.notes, Note, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    is_owner = (
        note.device_id == device.id
        or (user and (note.user_id == user.id or note.username == user.username))
        or (user and getattr(user, "device_id", None) == note.device_id)
    )
    if not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for this note")

    await repo.delete_by_id(mongo.notes, note_id)
    await hub.publish(ev.NOTE_DELETED, {"id": note_id}, device_id=device.id, origin="dashboard")
    return OkResponse(detail=note_id)


# --------------------------------------------------------------------------- #
# Quiz
# --------------------------------------------------------------------------- #


@router.post("/quiz/start", response_model=QuizSessionRead, status_code=status.HTTP_201_CREATED)
async def start_quiz(device: DeviceDep, user: UserDep, payload: QuizStartRequest) -> QuizSessionRead:
    note = await repo.find_by_id(mongo.notes, Note, payload.note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    if not quiz_service.available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is offline, so a quiz cannot be generated. Check GROQ_API_KEY.",
        )

    generated = await quiz_service.generate_questions(
        note.text, count=payload.count, difficulty=payload.difficulty, style=payload.style
    )
    if not generated:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate questions from that note. Try a note with more text.",
        )

    session = QuizSession(
        device_id=device.id,
        user_id=user.id if user else None,
        username=user.username if user else None,
        note_id=note.id,
        note_title=note.title,
        questions=[
            QuizQuestionDoc(question=q.question, answer=q.answer, options=q.options, hint=q.hint)
            for q in generated
        ],
    )
    await repo.insert(mongo.quiz_sessions, session)

    read = quiz_session_read(session)
    await hub.publish(ev.QUIZ_STARTED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.get("/quiz/{session_id}", response_model=QuizSessionRead)
async def get_quiz(device: DeviceDep, user: UserDep, session_id: str) -> QuizSessionRead:
    session = await repo.find_by_id(mongo.quiz_sessions, QuizSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return quiz_session_read(session)


@router.get("/quiz", response_model=list[QuizSessionRead])
async def list_quizzes(
    device: DeviceDep, user: UserDep, limit: int = Query(default=10, ge=1, le=50)
) -> list[QuizSessionRead]:
    filt: dict = {}
    if user:
        filt["$or"] = [
            {"user_id": user.id},
            {"username": user.username},
            {"device_id": user.device_id},
        ]
    else:
        filt["device_id"] = device.id

    sessions = await repo.find_many(
        mongo.quiz_sessions,
        QuizSession,
        filt,
        sort=[("created_at", repo.DESC)],
        limit=limit,
    )
    return [quiz_session_read(s) for s in sessions]


@router.post("/quiz/{session_id}/answer", response_model=QuizSessionRead)
async def answer_quiz(
    device: DeviceDep, user: UserDep, session_id: str, payload: QuizAnswerRequest
) -> QuizSessionRead:
    session = await repo.find_by_id(mongo.quiz_sessions, QuizSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    if session.finished:
        return quiz_session_read(session)

    if session.current_index >= len(session.questions):
        session.finished = True
        await repo.replace(mongo.quiz_sessions, QuizSession, session.id, session)
        return quiz_session_read(session)

    current_q = session.questions[session.current_index]
    graded = await quiz_service.grade_answer(
        question=current_q.question,
        reference_answer=current_q.answer,
        user_answer=payload.answer,
    )

    current_q.user_answer = payload.answer
    current_q.correct = graded.correct
    current_q.score = graded.score
    current_q.feedback = graded.feedback
    if graded.correct:
        session.correct_count += 1

    session.current_index += 1
    if session.current_index >= len(session.questions):
        session.finished = True

    session.updated_at = utcnow()
    await repo.replace(mongo.quiz_sessions, QuizSession, session.id, session)

    read = quiz_session_read(session)
    await hub.publish(ev.QUIZ_ANSWERED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read
