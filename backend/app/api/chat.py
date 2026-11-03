"""Chat + voice command endpoints.

One pipeline, three entry points (dashboard chat, mobile chat, firmware voice):

    transcript -> local intent parser -> execute + broadcast
                                     \\-> unmatched? -> Groq -> reply

Everything is logged to voice_commands so the dashboard can show recent commands,
and to chat_messages so the conversation survives a reload.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response

from .. import events as ev
from .. import repo
from ..config import settings
from ..db import mongo
from ..deps import DeviceDep, UserDep
from ..models import ChatMessage, CommandSource, Device, Note, User, VoiceCommand
from ..realtime import hub
from ..schemas import (
    ChatMessageRead,
    ChatRequest,
    ChatResponse,
    TranscriptionRead,
    VoiceCommandCreate,
    VoiceCommandRead,
)
from ..serializers import chat_message_read, voice_command_read
from ..services import ai as ai_service
from ..services import conversation
from ..services import intents as intent_service
from ..services import quiz as quiz_service
from ..services import tts as tts_service
from ..services.executor import execute

router = APIRouter(tags=["chat"])


def _save_debug_clip(audio: bytes) -> None:
    """Keep the last 20 device recordings when VOICE_DEBUG_DIR is set."""
    if not settings.voice_debug_dir or not audio:
        return
    try:
        folder = Path(settings.voice_debug_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"clip_{time.strftime('%Y%m%d_%H%M%S')}.wav").write_bytes(audio)
        for old in sorted(folder.glob("clip_*.wav"))[:-20]:
            old.unlink(missing_ok=True)
    except OSError:
        pass  # diagnostics must never break the voice path


async def _history(device_id: str, user: Optional[User] = None) -> list[dict[str, str]]:
    filt: dict = {}
    if user:
        filt["$or"] = [
            {"user_id": user.id},
            {"username": user.username},
            {"device_id": user.device_id},
        ]
    else:
        filt["device_id"] = device_id

    rows = await repo.find_many(
        mongo.chat_messages,
        ChatMessage,
        filt,
        sort=[("created_at", repo.DESC)],
        limit=10,
    )
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


async def _handle(
    device: Device,
    transcript: str,
    *,
    source: CommandSource,
    handled_locally: bool = False,
    latency_ms: Optional[int] = None,
) -> tuple[str, intent_service.Intent, Optional[str], str, VoiceCommand]:
    """Shared pipeline. Returns (reply, intent, action, provider, logged command)."""
    intent = intent_service.parse(transcript)
    provider = "local"
    action: Optional[str] = None
    reply: str

    # intent_name/entities start from the regex parse and may be upgraded by the
    # LLM below, so the command log records what actually ran.
    intent_name = intent.name
    entities = dict(intent.entities)

    STOP_QUIZ_WORDS = {
        "no", "no more", "stop", "stop quiz", "end quiz", "quit", "exit",
        "cancel", "no thanks", "nahi", "bas", "done", "enough", "stop questioning",
        "finish quiz", "end", "stop it", "bye", "nahi chahiye", "khatam", "band karo", "ruk jao",
    }
    YES_CONTINUE_WORDS = {
        "yes", "yeah", "yep", "sure", "ok", "okay", "haan", "ha", "bilkul",
        "next", "next question", "continue", "aur", "more", "agla", "agla sawal",
    }
    quiz_ref = conversation.recall_quiz(device.id)
    clean_trans = transcript.strip().lower().rstrip(" .,!?")

    if quiz_ref and (
        clean_trans in STOP_QUIZ_WORDS
        or clean_trans.startswith(("stop ", "no ", "exit ", "cancel ", "nahi ", "bas ", "khatam "))
    ):
        sess = conversation.end_quiz_session(device.id)
        if sess and sess.records:
            total = sess.total_answered
            correct = sess.correct_count
            pct = int(round((correct / total) * 100)) if total > 0 else 0
            feedback_note = "🌟 Excellent revision!" if pct >= 80 else ("👍 Good practice session!" if pct >= 50 else "Keep studying these notes and try again!")
            reply = (
                f"📊 Quiz Summary for {sess.note_title}:\n"
                f"• Score: {correct}/{total} ({pct}%)\n"
                f"• Total Answered: {total}\n"
                f"{feedback_note}\n\n"
                "Quiz ended! Say 'quiz me' whenever you want to practice again."
            )
        else:
            conversation.clear_quiz(device.id)
            reply = "Quiz ended! Great revision session. Say 'quiz me' whenever you want to practice again."
        intent_name = "notes.quiz_stop"
        action = "notes.quiz_stop"
        intent = intent_service.Intent(name=intent_name, entities={}, reply=reply)
        provider = "local"
    elif (
        quiz_ref
        and clean_trans in YES_CONTINUE_WORDS
        and not any(w in quiz_ref.reference_answer.lower() for w in ("yes", "no", "true", "false", "haan", "nahi"))
    ):
        # User confirmed they want another question or asked to skip to next
        target_note = await repo.find_by_id(mongo.notes, Note, quiz_ref.note_id)
        if not target_note:
            recent_notes = await repo.find_many(
                mongo.notes, Note, {"device_id": device.id}, sort=[("created_at", repo.DESC)], limit=1
            )
            if recent_notes:
                target_note = recent_notes[0]

        next_q = None
        if target_note and quiz_service.available():
            asked_list = conversation.get_asked_questions(device.id)
            new_questions = await quiz_service.generate_questions(
                target_note.text, count=3, difficulty="mixed", style="open", exclude=asked_list
            )
            for candidate in new_questions:
                if not conversation.was_question_asked(device.id, candidate.question):
                    next_q = candidate
                    break

        if next_q and target_note:
            conversation.remember_quiz(
                device.id,
                target_note.id,
                target_note.title,
                next_q.question,
                next_q.answer,
            )
            reply = (
                f"📝 Next Question from {target_note.title}:\n{next_q.question}\n\n"
                "💡 Speak your answer, or say 'no' to finish."
            )
            intent_name = "notes.quiz"
            action = "notes.quiz"
            intent = intent_service.Intent(name=intent_name, entities={"question": next_q.question}, reply=reply)
            provider = "groq"
        else:
            sess = conversation.end_quiz_session(device.id)
            score_line = ""
            if sess and sess.records:
                total = sess.total_answered
                correct = sess.correct_count
                pct = int(round((correct / total) * 100)) if total > 0 else 0
                score_line = f"\n• Score: {correct}/{total} ({pct}%)"
            reply = f"🎉 You've completed all questions from {quiz_ref.note_title}!{score_line}"
            intent_name = "notes.quiz_stop"
            action = "notes.quiz_stop"
            intent = intent_service.Intent(name=intent_name, entities={}, reply=reply)
            provider = "local"
    elif quiz_ref and not (intent.is_local and intent.name != "notes.quiz"):
        # User is answering the active quiz question.
        target_note = await repo.find_by_id(mongo.notes, Note, quiz_ref.note_id)
        if not target_note:
            recent_notes = await repo.find_many(
                mongo.notes, Note, {"device_id": device.id}, sort=[("created_at", repo.DESC)], limit=1
            )
            if recent_notes:
                target_note = recent_notes[0]

        note_text = target_note.text if target_note else ""
        grade = await quiz_service.grade_answer(
            quiz_ref.question, quiz_ref.reference_answer, transcript, note_text=note_text
        )

        is_correct = grade.correct or grade.score >= 0.7
        is_partial = 0.3 <= grade.score < 0.7
        status_tag = "Correct" if is_correct else ("Partially Correct" if is_partial else "Needs Review")

        conversation.record_quiz_answer(
            device.id,
            question=quiz_ref.question,
            user_answer=transcript,
            is_correct=is_correct,
            score=grade.score,
            feedback=grade.feedback,
        )

        suggestion = "Keep this momentum going!" if is_correct else "Review this topic in your notes."

        # Automatically generate the NEXT non-repeating question from the note!
        next_q = None
        if target_note and quiz_service.available():
            asked_list = conversation.get_asked_questions(device.id)
            new_questions = await quiz_service.generate_questions(
                target_note.text, count=3, difficulty="mixed", style="open", exclude=asked_list
            )
            for candidate in new_questions:
                if not conversation.was_question_asked(device.id, candidate.question):
                    next_q = candidate
                    break

        if next_q and target_note:
            conversation.remember_quiz(
                device.id,
                target_note.id,
                target_note.title,
                next_q.question,
                next_q.answer,
            )
            reply = (
                f"🎯 Evaluation: {status_tag}\n{grade.feedback}\n\n"
                f"💡 Suggestion: {suggestion}\n\n"
                f"📝 Next Question from {target_note.title}:\n{next_q.question}\n\n"
                "💡 Speak your answer, or say 'no' to finish."
            )
            intent_name = "notes.quiz"
            action = "notes.quiz"
            intent = intent_service.Intent(name=intent_name, entities={"question": next_q.question}, reply=reply)
            provider = "groq"
        else:
            sess = conversation.end_quiz_session(device.id)
            score_line = ""
            if sess and sess.records:
                total = sess.total_answered
                correct = sess.correct_count
                pct = int(round((correct / total) * 100)) if total > 0 else 0
                score_line = f"\n\n📊 Final Score: {correct}/{total} ({pct}%)"
            reply = (
                f"🎯 Evaluation: {status_tag}\n{grade.feedback}\n\n"
                f"💡 Suggestion: {suggestion}\n\n"
                f"🎉 You've completed all questions from {quiz_ref.note_title}!{score_line}"
            )
            intent_name = "notes.quiz_stop"
            action = "notes.quiz_stop"
            intent = intent_service.Intent(name=intent_name, entities={}, reply=reply)
            provider = "groq"
    elif intent.is_local and not handled_locally:
        result = await execute(device, intent, source=source)
        reply = result.reply or intent.reply or "Done."
        action = result.action
    elif intent.is_local and handled_locally:
        # The firmware already acted on it; just record what happened.
        reply = intent.reply or "Done."
        action = intent.name
    else:
        # The regex parser did not recognise a command. Before treating this as
        # plain chat, let the LLM try to understand free-form speech ("it's dark
        # in here", "wake me before my meeting") as an action, using history for
        # context. If it maps to a real intent, run it through the same executor.
        history = await _history(device.id)
        notes_context = await quiz_service.get_notes_context(device.id, transcript)
        resolution = await ai_service.resolve_intent(
            transcript, history, notes_context=notes_context
        )
        provider = resolution.provider

        if resolution.intent:
            llm_intent = intent_service.Intent(
                name=resolution.intent,
                entities=resolution.entities,
                reply=resolution.reply or None,
            )
            result = await execute(device, llm_intent, source=source)
            reply = result.reply or resolution.reply or "Done."
            action = result.action
            intent_name = resolution.intent
            entities = resolution.entities
        else:
            # Genuinely conversational — speak the LLM's reply, do nothing.
            reply = resolution.reply

    # Reflect what actually ran (possibly upgraded by the LLM) onto the returned
    # intent, since callers read intent.name / intent.entities for the response
    # and the spoken frame.
    intent.name = intent_name
    intent.entities = entities

    command = VoiceCommand(
        device_id=device.id,
        transcript=transcript,
        intent=intent_name,
        entities=entities,
        response_text=reply,
        handled_locally=handled_locally or intent.is_local or action is not None,
        source=source,
        latency_ms=latency_ms,
    )
    await repo.insert(mongo.voice_commands, command)

    await hub.publish(
        ev.VOICE_COMMAND,
        voice_command_read(command).model_dump(mode="json"),
        device_id=device.id,
        origin=source.value,
        persist=False,
    )
    return reply, intent, action, provider, command


@router.post("/chat", response_model=ChatResponse)
async def chat(device: DeviceDep, user: UserDep, payload: ChatRequest) -> ChatResponse:
    user_msg = ChatMessage(
        device_id=device.id,
        user_id=user.id if user else None,
        username=user.username if user else None,
        role="user",
        content=payload.message,
        source=payload.source,
    )
    await repo.insert(mongo.chat_messages, user_msg)

    reply, intent, action, provider, _ = await _handle(
        device, payload.message, source=payload.source
    )

    assistant_msg = ChatMessage(
        device_id=device.id,
        user_id=user.id if user else None,
        username=user.username if user else None,
        role="assistant",
        content=reply,
        source=payload.source,
    )
    await repo.insert(mongo.chat_messages, assistant_msg)

    messages = [chat_message_read(user_msg), chat_message_read(assistant_msg)]
    for message in messages:
        await hub.publish(
            ev.CHAT_MESSAGE,
            message.model_dump(mode="json"),
            device_id=device.id,
            origin=payload.source.value,
            persist=False,
        )

    if payload.speak:
        # Ask the firmware to speak the reply through the MAX98357.
        await hub.to_device(
            device.id,
            {
                "type": "speak",
                "device_id": device.id,
                "origin": "server",
                "payload": {"text": reply, "intent": intent.name},
            },
        )

    return ChatResponse(
        reply=reply,
        intent=intent.name,
        entities=intent.entities,
        action_taken=action,
        provider=provider,
        messages=messages,
    )


@router.get("/chat/history", response_model=list[ChatMessageRead])
async def chat_history(
    device: DeviceDep,
    user: UserDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ChatMessageRead]:
    filt: dict = {}
    if user:
        filt["$or"] = [
            {"user_id": user.id},
            {"username": user.username},
            {"device_id": user.device_id},
        ]
    else:
        filt["device_id"] = device.id

    rows = await repo.find_many(
        mongo.chat_messages,
        ChatMessage,
        filt,
        sort=[("created_at", repo.DESC)],
        limit=limit,
    )
    return [chat_message_read(r) for r in reversed(rows)]


@router.delete("/chat/history")
async def clear_chat_history(device: DeviceDep, user: UserDep) -> dict[str, int]:
    filt: dict = {}
    if user:
        filt["$or"] = [
            {"user_id": user.id},
            {"username": user.username},
            {"device_id": user.device_id},
        ]
    else:
        filt["device_id"] = device.id

    res = await mongo.chat_messages.delete_many(filt)
    return {"deleted": res.deleted_count}
    result = await mongo.chat_messages.delete_many({"device_id": device.id})
    return {"deleted": result.deleted_count}


@router.post("/voice/command", response_model=VoiceCommandRead)
async def voice_command(device: DeviceDep, payload: VoiceCommandCreate) -> VoiceCommandRead:
    """Entry point for the firmware: post a transcript, get the reply to speak."""
    _, _, _, _, command = await _handle(
        device,
        payload.transcript,
        source=payload.source,
        handled_locally=payload.handled_locally,
        latency_ms=payload.latency_ms,
    )
    return voice_command_read(command)


@router.get("/voice/commands", response_model=list[VoiceCommandRead])
async def voice_commands(
    device: DeviceDep,
    limit: int = Query(default=25, ge=1, le=200),
) -> list[VoiceCommandRead]:
    rows = await repo.find_many(
        mongo.voice_commands,
        VoiceCommand,
        {"device_id": device.id},
        sort=[("created_at", repo.DESC)],
        limit=limit,
    )
    return [voice_command_read(r) for r in rows]


@router.post("/voice/transcribe", response_model=TranscriptionRead)
async def voice_transcribe(
    device: DeviceDep,
    file: UploadFile = File(..., description="16 kHz mono 16-bit PCM WAV"),
    speak: bool = Query(default=True, description="Send the reply back to the device"),
) -> TranscriptionRead:
    """The device's voice entry point: audio in, action taken, reply out.

    One round trip does everything, because the ESP32 should not have to
    orchestrate a multi-step conversation over a flaky link:

        WAV -> Whisper -> intent parser -> execute (or Groq) -> reply

    A local intent (timer, relay, weather...) is executed and broadcast before
    this returns, so by the time the device sees the reply the action has already
    happened. Only genuinely open-ended speech reaches the LLM.
    """
    started = time.perf_counter()

    audio = await file.read()
    _save_debug_clip(audio)
    try:
        transcription = await ai_service.transcribe(
            audio,
            filename=file.filename or "speech.wav",
            content_type=file.content_type or "audio/wav",
        )
    except ai_service.TranscriptionError as exc:
        # 502: the request was fine, the upstream or the audio was not.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    await hub.publish(
        ev.VOICE_TRANSCRIBED,
        {
            "transcript": transcription.text,
            "duration_seconds": transcription.duration_seconds,
            "language": transcription.language,
        },
        device_id=device.id,
        origin="device",
        persist=False,
    )

    reply, intent, action, provider, _ = await _handle(
        device,
        transcription.text,
        source=CommandSource.VOICE,
        latency_ms=transcription.latency_ms,
    )

    # Persist and broadcast both messages so hardware voice interactions
    # appear in real time on the dashboard Chat page (user transcript + evaluation & suggestions).
    if transcription.text.strip():
        user_msg = ChatMessage(
            device_id=device.id,
            role="user",
            content=transcription.text,
            source=CommandSource.VOICE,
        )
        await repo.insert(mongo.chat_messages, user_msg)
        await hub.publish(
            ev.CHAT_MESSAGE,
            chat_message_read(user_msg).model_dump(mode="json"),
            device_id=device.id,
            origin="voice",
            persist=False,
        )

        if reply:
            assistant_msg = ChatMessage(
                device_id=device.id,
                role="assistant",
                content=reply,
                source=CommandSource.VOICE,
            )
            await repo.insert(mongo.chat_messages, assistant_msg)
            await hub.publish(
                ev.CHAT_MESSAGE,
                chat_message_read(assistant_msg).model_dump(mode="json"),
                device_id=device.id,
                origin="voice",
                persist=False,
            )

    if speak:
        # The firmware shows this and chimes; real TTS is still unimplemented.
        await hub.to_device(
            device.id,
            {
                "type": "speak",
                "device_id": device.id,
                "origin": "server",
                "payload": {"text": reply, "transcript": transcription.text},
            },
        )

    return TranscriptionRead(
        transcript=transcription.text,
        reply=reply,
        intent=intent.name,
        entities=intent.entities,
        action_taken=action,
        provider=provider,
        model=transcription.model,
        audio_bytes=len(audio),
        audio_seconds=transcription.duration_seconds,
        transcribe_ms=transcription.latency_ms,
        total_ms=int((time.perf_counter() - started) * 1000),
        spoken=speak,
    )


@router.post("/voice/listening")
async def voice_listening(
    device: DeviceDep,
    listening: bool = Query(default=True),
) -> dict[str, bool]:
    """Firmware tells dashboards the mic is open so the UI can show LISTENING."""
    await hub.publish(
        ev.VOICE_LISTENING,
        {"listening": listening},
        device_id=device.id,
        origin="device",
        persist=False,
    )
    return {"listening": listening}


@router.get("/ai/models", tags=["chat"])
async def ai_models() -> dict[str, Any]:
    """What this Groq key can actually use.

    GroqCloud retires models on a regular cadence — the Llama models moved to
    Enterprise-only in 2026 — so when chat starts returning the offline fallback,
    this is the first thing to check.
    """
    available = await ai_service.list_models()
    return {
        "provider": settings.ai_provider,
        "configured_model": settings.groq_model,
        "configured_model_available": settings.groq_model in available if available else None,
        "reasoning_effort": settings.groq_reasoning_effort,
        "transcribe_model": settings.groq_transcribe_model,
        "available_models": available,
    }


@router.post("/voice/speak")
async def voice_speak(
    request: Request,
    text: Optional[str] = Query(default=None, description="Text to synthesize into speech"),
    voice: str = Query(default="", description="Edge TTS voice name (empty = use config)"),
) -> Response:
    """Synthesize text into a WAV file for the ESP32 speaker.

    Returns audio/wav at the sample rate matching the firmware's I2S config
    (default 22050 Hz, 16-bit mono). The firmware downloads this into PSRAM
    and plays it straight through the chime I2S driver.

    No API key needed — uses Microsoft Edge TTS, same free-tier approach
    as Open-Meteo for weather.
    """
    if not text:
        body = await request.body()
        if body:
            try:
                ct = request.headers.get("content-type", "")
                if "application/json" in ct:
                    data = await request.json()
                    text = data.get("text", "")
                elif "x-www-form-urlencoded" in ct:
                    form = await request.form()
                    text = form.get("text", "")
                else:
                    text = body.decode("utf-8", errors="ignore").strip()
            except Exception:
                text = body.decode("utf-8", errors="ignore").strip()

    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text provided for TTS",
        )

    if not tts_service.available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS unavailable: edge-tts package not installed. "
            "Run: pip install edge-tts miniaudio",
        )

    selected_voice = voice.strip() or settings.tts_voice
    wav = await tts_service.synthesize(
        text,
        voice=selected_voice,
        sample_rate=settings.tts_sample_rate,
    )

    if wav is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="TTS synthesis returned no audio. Check the text and voice name.",
        )

    return Response(
        content=wav,
        media_type="audio/wav",
        headers={
            "Content-Disposition": "inline; filename=speech.wav",
            "X-Audio-Duration": f"{(len(wav) - 44) / (settings.tts_sample_rate * 2):.2f}",
        },
    )

