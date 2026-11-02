"""Study notes + AI quizzing.

Upload exam-prep files (PDF, Word, Excel, text), the backend extracts the text,
and the AI generates questions from it and grades your answers. Only the
extracted text is stored, never the original file.

Flow:
    POST /api/notes/upload   file -> extract text -> store Note
    GET  /api/notes          list notes (no text)
    GET  /api/notes/{id}     one note, with text
    DELETE /api/notes/{id}
    POST /api/quiz/start     {note_id, count, style} -> QuizSession with questions
    GET  /api/quiz/{id}      current session state
    POST /api/quiz/{id}/answer {answer} -> grades, advances, returns session
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from .. import events as ev
from .. import repo
from ..config import settings
from ..db import mongo
from ..deps import DeviceDep
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
async def list_notes(device: DeviceDep, limit: int = Query(default=50, ge=1, le=200)) -> list[NoteRead]:
    notes = await repo.find_many(
        mongo.notes,
        Note,
        {"device_id": device.id},
        sort=[("created_at", repo.DESC)],
        limit=limit,
    )
    return [note_read(n) for n in notes]  # list omits the full text on purpose


@router.get("/notes/{note_id}", response_model=NoteRead)
async def get_note(device: DeviceDep, note_id: str) -> NoteRead:
    note = await repo.find_by_id(mongo.notes, Note, note_id)
    if note is None or note.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note_read(note, include_text=True)


@router.post("/notes/upload", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def upload_note(
    device: DeviceDep,
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
        # 422: the request was valid, the file's content was not usable.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    title = (file.filename or "Untitled note").rsplit("/", 1)[-1]
    note = Note(
        device_id=device.id,
        title=title,
        kind=extracted.kind,
        text=extracted.text,
        char_count=len(extracted.text),
        source=CommandSource.DASHBOARD,
    )
    await repo.insert(mongo.notes, note)

    # Keep the collection bounded: drop the oldest notes past the cap.
    existing = await repo.find_many(
        mongo.notes, Note, {"device_id": device.id}, sort=[("created_at", repo.DESC)]
    )
    for old in existing[settings.notes_max_count :]:
        await repo.delete_by_id(mongo.notes, old.id)

    read = note_read(note)
    await hub.publish(ev.NOTE_CREATED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read


@router.delete("/notes/{note_id}", response_model=OkResponse)
async def delete_note(device: DeviceDep, note_id: str) -> OkResponse:
    note = await repo.find_by_id(mongo.notes, Note, note_id)
    if note is None or note.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    await repo.delete_by_id(mongo.notes, note_id)
    await hub.publish(ev.NOTE_DELETED, {"id": note_id}, device_id=device.id, origin="dashboard")
    return OkResponse(detail=note_id)


# --------------------------------------------------------------------------- #
# Quiz
# --------------------------------------------------------------------------- #


@router.post("/quiz/start", response_model=QuizSessionRead, status_code=status.HTTP_201_CREATED)
async def start_quiz(device: DeviceDep, payload: QuizStartRequest) -> QuizSessionRead:
    note = await repo.find_by_id(mongo.notes, Note, payload.note_id)
    if note is None or note.device_id != device.id:
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
async def get_quiz(device: DeviceDep, session_id: str) -> QuizSessionRead:
    session = await repo.find_by_id(mongo.quiz_sessions, QuizSession, session_id)
    if session is None or session.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return quiz_session_read(session)


@router.get("/quiz", response_model=list[QuizSessionRead])
async def list_quizzes(device: DeviceDep, limit: int = Query(default=10, ge=1, le=50)) -> list[QuizSessionRead]:
    sessions = await repo.find_many(
        mongo.quiz_sessions,
        QuizSession,
        {"device_id": device.id},
        sort=[("created_at", repo.DESC)],
        limit=limit,
    )
    return [quiz_session_read(s) for s in sessions]


@router.post("/quiz/{session_id}/answer", response_model=QuizSessionRead)
async def answer_quiz(device: DeviceDep, session_id: str, payload: QuizAnswerRequest) -> QuizSessionRead:
    session = await repo.find_by_id(mongo.quiz_sessions, QuizSession, session_id)
    if session is None or session.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    if session.finished:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This quiz is already finished.")
    if session.current_index >= len(session.questions):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No question is pending.")

    note = await repo.find_by_id(mongo.notes, Note, session.note_id)
    question = session.questions[session.current_index]

    grade = await quiz_service.grade_answer(
        question.question, question.answer, payload.answer, note.text if note else ""
    )
    question.user_answer = payload.answer
    question.correct = grade.correct
    question.score = grade.score
    question.feedback = grade.feedback

    if grade.correct:
        session.correct_count += 1
    session.current_index += 1
    session.finished = session.current_index >= len(session.questions)
    session.updated_at = utcnow()
    await repo.replace(mongo.quiz_sessions, session)

    read = quiz_session_read(session)
    await hub.publish(ev.QUIZ_GRADED, read.model_dump(mode="json"), device_id=device.id, origin="dashboard")
    return read
