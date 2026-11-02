"""AI layer — GroqCloud, optional by design.

With `AI_PROVIDER=mock` (or no key) the assistant answers from the local intent
parser plus a few canned responses, so the whole demo runs with no key and no
internet. That is not a fallback bolted on afterwards; it is the product
requirement that the device stays useful when the network does not.

Groq speaks the OpenAI chat-completions shape at
`https://api.groq.com/openai/v1`, so this is a thin HTTP client rather than
another SDK dependency.

Model notes (verified against the live API, Sep 2026)
----------------------------------------------------
* Self-serve production models are `openai/gpt-oss-20b` (~1000 tok/s) and
  `openai/gpt-oss-120b` (~500 tok/s). The Llama models are Enterprise-only now
  and return 404 `model_not_found` on a free key.
* These are *reasoning* models. Left at default effort they spend most of the
  token budget thinking: measured 109 reasoning tokens and 220 ms, versus 5
  tokens and 85 ms at `reasoning_effort="low"`. We want two short spoken
  sentences, so low effort is both faster and better.
* The reply arrives in `message.content`; `message.reasoning` is separate and is
  deliberately ignored — it is scratch work, not something to speak aloud.

The key is read from the environment on the backend only. It never reaches the
dashboard, the phone or the ESP32.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from ..config import settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are DeskBuddy, an AI assistant living inside a small ESP32-S3 desk device "
    "with a 128x64 OLED screen, a speaker and a single touch button. "
    "Answer in at most two short sentences: replies are spoken aloud and may be "
    "shown on a tiny display. Be concrete and skip pleasantries. "
    "If the user asks who you are or what you do, YOU MUST REPLY EXACTLY WITH: "
    "\"I am DeskBuddy, an AI assistant designed to be on your desk and help you with small tasks.\" "
    "Never state who created, made, built, or developed you, and never name any person as your creator; "
    "if asked who made you, just say you are DeskBuddy, a desk assistant, and offer to help. "
    "The device already handles timers, alarms, stopwatch, Pomodoro, reminders "
    "and tasks locally, so do not explain how to do those things manually. "
    "You cannot switch the light, start timers or change anything yourself; "
    "commands are handled before they reach you. Never claim you did an action "
    "(e.g. never say 'Light turned on'). If the user seems to want the light, "
    "tell them to say 'turn on the light' or 'turn off the light'."
)

OFFLINE_FALLBACK = (
    "I'm having trouble connecting to the AI service right now. You can still use timers, alarms, "
    "Pomodoro, tasks, and notes revision."
)

# Values GroqCloud accepts for reasoning_effort, per the API's own 400 message.
VALID_EFFORTS = {"none", "default", "minimal", "low", "medium", "high", "xhigh", "max"}


@dataclass
class AiReply:
    text: str
    provider: str
    model: Optional[str] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None


@dataclass
class Transcription:
    text: str
    model: Optional[str] = None
    duration_seconds: Optional[float] = None
    language: Optional[str] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())


class TranscriptionError(RuntimeError):
    """Raised with a message meant to be actionable, not just logged."""


def available() -> bool:
    return settings.ai_live


def describe() -> str:
    """Short status string for /health."""
    if not available():
        return "offline-mock"
    return f"groq:{settings.groq_model}"


async def _build_payload(
    message: str,
    history: Optional[list[dict[str, str]]],
    notes_context: str = "",
) -> dict[str, Any]:
    from ..services import weather as weather_service
    
    prompt_context = ""
    if settings.weather_configured:
        try:
            w = await weather_service.get()
            prompt_context = (
                f"Current weather: {w.temperature}°C ({w.short}). "
                f"High {w.temp_max}°C, Low {w.temp_min}°C. "
                f"Precipitation chance: {w.precipitation_chance}%. "
            )
        except Exception:
            prompt_context = "Current weather: unavailable right now. "

    system_prompt = SYSTEM_PROMPT
    if prompt_context:
        system_prompt = f"{prompt_context}\n{SYSTEM_PROMPT}"
    if notes_context:
        system_prompt += (
            f"\n\nSTUDY NOTES:\n{notes_context}\n"
            "You have access to the user's uploaded study notes. When the user asks about their notes "
            "or answers a study question, use these notes to answer accurately and evaluate their response. "
            "Give clear, constructive feedback and offer another question if appropriate."
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in (history or [])[-8:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    payload: dict[str, Any] = {
        "model": settings.groq_model,
        "messages": messages,
        "max_completion_tokens": settings.groq_max_completion_tokens,
        "temperature": settings.groq_temperature,
    }

    effort = (settings.groq_reasoning_effort or "").strip().lower()
    if effort and effort in VALID_EFFORTS:
        payload["reasoning_effort"] = effort
    elif effort:
        log.warning(
            "[ai] ignoring GROQ_REASONING_EFFORT=%r; allowed values are %s",
            effort,
            ", ".join(sorted(VALID_EFFORTS)),
        )
    return payload


async def complete(
    message: str,
    history: Optional[list[dict[str, str]]] = None,
    notes_context: str = "",
) -> AiReply:
    """Ask Groq, or answer locally when Groq is not configured/reachable."""
    if not available():
        return AiReply(text=_local_answer(message), provider="mock")

    url = f"{settings.groq_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = await _build_payload(message, history, notes_context)

    try:
        async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)

            # Some parameters are model-specific. If Groq rejects reasoning_effort
            # (because the configured model is not a reasoning model), retry once
            # without it rather than failing the request.
            if response.status_code == 400 and "reasoning_effort" in response.text:
                log.info("[ai] model rejected reasoning_effort; retrying without it")
                payload.pop("reasoning_effort", None)
                response = await client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            raise _api_error(response)

        data = response.json()
        choice = data["choices"][0]
        text = (choice["message"].get("content") or "").strip()
        usage = data.get("usage") or {}

        if not text:
            # Reasoning models can burn the whole budget thinking and emit nothing.
            reason = choice.get("finish_reason")
            details = usage.get("completion_tokens_details") or {}
            raise ValueError(
                f"empty content (finish_reason={reason}, "
                f"reasoning_tokens={details.get('reasoning_tokens')}). "
                "Raise GROQ_MAX_COMPLETION_TOKENS or lower GROQ_REASONING_EFFORT."
            )

        latency = usage.get("total_time")
        return AiReply(
            text=text,
            provider="groq",
            model=settings.groq_model,
            latency_ms=int(latency * 1000) if isinstance(latency, (int, float)) else None,
        )

    except Exception as exc:  # noqa: BLE001 - the AI layer must never break the device
        log.warning("[ai] request failed, using local fallback: %s", exc)
        return AiReply(
            text=_local_answer(message),
            provider="mock",
            model=settings.groq_model,
            error=str(exc)[:300],
        )


# --------------------------------------------------------------------------- #
# LLM intent understanding
#
# The regex parser only catches fixed phrasings. This layer runs when the parser
# gives up, and lets the model map free-form, conversational speech onto one of
# the device's real actions — using recent chat history so follow-ups resolve.
# "it's dark in here" -> relay.on; "I need to focus" -> pomodoro.start; "wake me
# before my 9 am meeting" -> alarm.set 08:45. If nothing fits, it falls back to
# a normal spoken reply.
# --------------------------------------------------------------------------- #

# The action the model is allowed to choose, described in its own words. Kept in
# lock-step with executor.execute(): every name here must be handled there, and
# the entity keys are exactly what that handler reads.
_ACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "control_device",
        "description": (
            "Carry out a DeskBuddy action the user asked for in natural speech. "
            "Only call this when the user clearly wants the device to DO something "
            "(set a timer, switch the light, start focus, set an alarm, add/finish a "
            "task, ask the weather or time). For chit-chat, questions, or anything "
            "ambiguous, do NOT call this — reply normally instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "timer.start", "timer.pause", "timer.resume", "timer.cancel",
                        "pomodoro.start", "pomodoro.stop",
                        "alarm.set", "alarm.cancel",
                        "reminder.create",
                        "task.create", "task.complete", "task.delete", "task.list",
                        "relay.on", "relay.off", "relay.toggle",
                        "weather.current", "clock.time", "clock.date",
                        "notes.quiz",
                    ],
                    "description": "Which device action to run.",
                },
                "topic": {
                    "type": "string",
                    "description": "For notes.quiz: optional subject, topic or note title (e.g. 'biology', 'physics', 'chapter 1') if named.",
                },
                "duration_seconds": {
                    "type": "integer",
                    "description": "For timer.start: length in seconds (e.g. '10 minutes' -> 600).",
                },
                "time_of_day": {
                    "type": "string",
                    "description": "For alarm.set: 24-hour HH:MM, device local time. Convert '7am'->07:00, 'quarter to nine'->08:45.",
                },
                "focus_minutes": {
                    "type": "integer",
                    "description": "For pomodoro.start: focus length in minutes if the user named one.",
                },
                "text": {
                    "type": "string",
                    "description": "For reminder.create: what to be reminded about.",
                },
                "in_minutes": {
                    "type": "integer",
                    "description": "For reminder.create: minutes from now, if the user said 'in N minutes'.",
                },
                "title": {
                    "type": "string",
                    "description": "For task.create/complete/delete: the task text, when the user named it.",
                },
                "ref": {
                    "type": "string",
                    "enum": ["last", "it"],
                    "description": "For task.complete/delete when the user said 'it'/'that'/'the last one' instead of naming the task.",
                },
                "spoken_reply": {
                    "type": "string",
                    "description": "A short, friendly confirmation to say aloud, e.g. 'Turning the light on.'",
                },
            },
            "required": ["intent"],
            "additionalProperties": False,
        },
    },
}

_INTENT_SYSTEM = (
    "You are the intent understander for DeskBuddy, a small desk assistant. The "
    "user speaks naturally; work out whether they want a device action and, if so, "
    "call control_device with the right intent and details. Use the recent "
    "conversation for context: 'the last one', 'it', 'that', or a follow-up like "
    "'make it 10 minutes instead' refer to what was just discussed. Examples: "
    "'it's dark in here' or 'I can't see' -> relay.on; 'that's too bright' -> "
    "relay.off; 'I need to focus for a while' -> pomodoro.start; 'wake me at half "
    "past six' -> alarm.set 06:30; 'give me five more minutes' after a timer -> "
    "timer.start 300. Asking to be quizzed, tested, or asked a question from uploaded "
    "study notes or PDF (e.g. 'quiz me on my notes', 'ask me a question from my notes', "
    "'test me on biology', 'another question', 'next question') -> notes.quiz. "
    "A relative wake-up or nudge such as 'wake me in 20 minutes' "
    "or 'remind me in 10 minutes' is reminder.create with in_minutes (give it a "
    "text), NOT an alarm — alarms are only for a clock time of day. If the user "
    "is only chatting, asking a general question, answering a quiz question, or "
    "asking about their study notes, do NOT call control_device — answer in one or two short "
    "sentences instead. Keep spoken_reply brief; it is read aloud."
)


@dataclass
class IntentResolution:
    """What the LLM decided: either an action to run, or a plain reply to speak."""

    intent: Optional[str]  # None means "no action, just talk"
    entities: dict[str, Any]
    reply: str
    provider: str


async def resolve_intent(
    message: str,
    history: Optional[list[dict[str, str]]] = None,
    notes_context: str = "",
) -> IntentResolution:
    """Ask the model to map free-form speech onto a device action, with memory.

    Returns an IntentResolution. When `intent` is None the user was just talking,
    and `reply` is the conversational answer. This never raises: on any failure it
    degrades to a plain chat reply, because the regex parser already had its turn
    and the device must still say something.
    """
    if not available():
        # No LLM: nothing smarter than the regex parser is possible offline.
        return IntentResolution(None, {}, _local_answer(message), "mock")

    url = f"{settings.groq_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    system_content = _INTENT_SYSTEM
    if notes_context:
        system_content += (
            f"\n\nSTUDY NOTES REFERENCE:\n{notes_context}\n"
            "If the user is asking questions about these notes or answering a quiz question based on them, "
            "evaluate or answer conversationally using the notes (do NOT call control_device). "
            "If they want to be quizzed or asked a question from the notes, call control_device with notes.quiz."
        )

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    for turn in (history or [])[-8:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    payload: dict[str, Any] = {
        "model": settings.groq_model,
        "messages": messages,
        "tools": [_ACTION_TOOL],
        "tool_choice": "auto",
        "temperature": 0.2,  # low: this is classification, not creative writing
        "max_completion_tokens": settings.groq_max_completion_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            raise _api_error(response)

        choice = response.json()["choices"][0]["message"]
        tool_calls = choice.get("tool_calls") or []

        if tool_calls:
            import json

            args = json.loads(tool_calls[0]["function"]["arguments"] or "{}")
            intent = str(args.pop("intent", "")).strip()
            reply = str(args.pop("spoken_reply", "") or "").strip()
            # Whatever is left is the entity set the executor reads.
            entities = {k: v for k, v in args.items() if v is not None}
            if intent:
                return IntentResolution(intent, entities, reply, "groq")

        # No tool call: the model chose to just talk.
        text = (choice.get("content") or "").strip()
        if text:
            return IntentResolution(None, {}, text, "groq")
        return IntentResolution(None, {}, _local_answer(message), "mock")

    except Exception as exc:  # noqa: BLE001 - must never break the device
        log.warning("[ai] intent resolution failed, falling back to chat: %s", exc)
        reply = await complete(message, history)
        return IntentResolution(None, {}, reply.text, reply.provider)


def _api_error(response: httpx.Response) -> Exception:
    """Turn a Groq error response into something actionable in the log."""
    detail = ""
    code = ""
    try:
        body = response.json()
        error = body.get("error") or {}
        detail = str(error.get("message") or "")[:250]
        code = str(error.get("code") or "")
    except Exception:  # noqa: BLE001
        detail = response.text[:250]

    if response.status_code == 401:
        return RuntimeError(
            "Groq rejected the API key (401). Check GROQ_API_KEY in backend/.env."
        )
    if response.status_code == 404 or code == "model_not_found":
        return RuntimeError(
            f"Groq has no model '{settings.groq_model}' for this key (404). "
            "GroqCloud retires models regularly and the Llama models are now "
            "Enterprise-only. Try openai/gpt-oss-20b or openai/gpt-oss-120b; "
            "GET /api/ai/models lists what your key can actually use. "
            f"Groq said: {detail}"
        )
    if response.status_code == 429:
        return RuntimeError(f"Groq rate limit reached (429). {detail}")
    return RuntimeError(f"Groq HTTP {response.status_code}: {detail}")


async def transcribe(
    audio: bytes,
    filename: str = "speech.wav",
    content_type: str = "audio/wav",
) -> Transcription:
    """Speech to text via Groq Whisper.

    Verified against the live API: `POST /audio/transcriptions`, multipart with
    `file` + `model`. `verbose_json` additionally returns `duration` and
    `language`, which are worth having for telemetry — the ESP32 has no idea how
    long it actually recorded.

    Whisper returns the text with a **leading space** and normalises spoken
    numbers to digits ("ten" -> "10"). Both matter downstream: the space is
    stripped here, and the digits are why the intent parser accepts numerals.

    Unlike `complete()` there is no offline fallback. Nothing local can turn
    audio into words, so a failure here has to surface as a failure.
    """
    started = time.perf_counter()

    if not settings.groq_api_key:
        raise TranscriptionError(
            "No GROQ_API_KEY set, so speech cannot be transcribed. "
            "Voice needs the network; every other feature does not."
        )
    if not audio:
        raise TranscriptionError("No audio received (zero bytes).")
    if len(audio) > settings.transcribe_max_bytes:
        raise TranscriptionError(
            f"Audio is {len(audio) // 1024} kB, over the "
            f"{settings.transcribe_max_bytes // 1024} kB limit."
        )

    url = f"{settings.groq_base_url.rstrip('/')}/audio/transcriptions"
    data: dict[str, Any] = {
        "model": settings.groq_transcribe_model,
        "response_format": "verbose_json",
    }
    language = (settings.groq_transcribe_language or "").strip()
    if language:
        data["language"] = language
    prompt = (settings.groq_transcribe_prompt or "").strip()
    if prompt:
        data["prompt"] = prompt

    try:
        async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files={"file": (filename, audio, content_type)},
                data=data,
            )
    except Exception as exc:  # noqa: BLE001
        raise TranscriptionError(f"Could not reach Groq: {exc}") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)

    if response.status_code != 200:
        raise TranscriptionError(_transcribe_error(response))

    body = response.json()
    text = (body.get("text") or "").strip()

    # Hindi and Urdu sound the same, and on short clips Whisper sometimes picks
    # Urdu and writes Arabic script ("لائٹ چالو کر"), which nothing downstream can
    # read. Re-ask with Hindi forced. Costs one extra call, only in that case.
    if not language and _ARABIC_SCRIPT.search(text):
        retry_data = {**data, "language": "hi"}
        try:
            async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
                retry = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    files={"file": (filename, audio, content_type)},
                    data=retry_data,
                )
            if retry.status_code == 200:
                body = retry.json()
                log.info("[voice] Urdu script %r re-transcribed as Hindi: %r",
                         text, (body.get("text") or "").strip())
                text = (body.get("text") or "").strip()
                latency_ms = int((time.perf_counter() - started) * 1000)
        except Exception:  # noqa: BLE001
            pass  # keep the first result; the parser will treat it as chat

    # Whisper's stock output for silence. Without a prompt it invents these with
    # high confidence, so the logprob check below does not catch them.
    if _is_silence_hallucination(text):
        log.info("[voice] dropped %r as a silence hallucination", text)
        raise TranscriptionError("No clear speech heard. Try again, closer to the mic.")

    # Reject clips Whisper was not confident about. Silence and room noise come
    # back as invented words ("you", "So, let's go."), which must not reach the
    # command parser. See transcribe_min_avg_logprob for the measured numbers.
    segments = body.get("segments") or []
    logprobs = [s.get("avg_logprob") for s in segments if isinstance(s, dict)]
    logprobs = [p for p in logprobs if isinstance(p, (int, float))]
    if text and logprobs and max(logprobs) < settings.transcribe_min_avg_logprob:
        log.info("[voice] dropped %r as noise: avg_logprob best %.2f", text, max(logprobs))
        raise TranscriptionError("No clear speech heard. Try again, closer to the mic.")

    if not text:
        raise TranscriptionError(
            "Whisper returned no words. The recording was probably silent — "
            "check the INMP441 wiring and that L/R is tied to GND."
        )

    return Transcription(
        text=text,
        model=settings.groq_transcribe_model,
        duration_seconds=body.get("duration"),
        language=body.get("language"),
        latency_ms=latency_ms,
    )


_ARABIC_SCRIPT = re.compile(r"[\u0600-\u06FF]")

# Phrases Whisper is known to produce from silence or noise (it was trained on
# subtitled video). Measured here: 3 s of zeros -> "Thank you.", noise -> ".".
_SILENCE_PHRASES = {
    "", "you", "thank you", "thanks", "thank you very much", "thanks for watching",
    "thank you for watching", "bye", "bye bye", "okay", "oh", "so",
    "please subscribe", "subscribe", "music",
}


def _is_silence_hallucination(text: str) -> bool:
    core = re.sub(r"[^\w\s]", "", text.lower()).strip()
    core = re.sub(r"\s+", " ", core)
    return core in _SILENCE_PHRASES


def _transcribe_error(response: httpx.Response) -> str:
    detail = ""
    code = ""
    try:
        error = (response.json() or {}).get("error") or {}
        detail = str(error.get("message") or "")[:250]
        code = str(error.get("code") or "")
    except Exception:  # noqa: BLE001
        detail = response.text[:250]

    if response.status_code == 401:
        return "Groq rejected the API key (401). Check GROQ_API_KEY."
    if code == "empty_audio_file":
        return (
            "Groq says the audio file is empty. The device sent a header with no "
            "samples — check that the I2S read actually returned data."
        )
    if response.status_code == 404 or code == "model_not_found":
        return (
            f"Groq has no model '{settings.groq_transcribe_model}'. "
            "Try whisper-large-v3-turbo; GET /api/ai/models lists what the key allows."
        )
    if response.status_code == 413:
        return "Groq rejected the upload as too large."
    if response.status_code == 429:
        return f"Groq rate limit reached (429). {detail}"
    return f"Groq HTTP {response.status_code}: {detail}"


async def list_models() -> list[str]:
    """Model ids this key can use. Handy when a model id goes stale."""
    if not settings.groq_api_key:
        return []
    url = f"{settings.groq_base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
            response = await client.get(
                url, headers={"Authorization": f"Bearer {settings.groq_api_key}"}
            )
        response.raise_for_status()
        return sorted(item["id"] for item in response.json().get("data", []))
    except Exception as exc:  # noqa: BLE001
        log.warning("[ai] could not list models: %s", exc)
        return []


def _local_answer(message: str) -> str:
    """Friendly fallback layer for conversational queries."""
    low = message.lower().strip()

    if any(word in low for word in ("hello", "hi ", "hey", "good morning", "good evening")):
        return "Hey! I'm DeskBuddy. How can I help you today?"
    if "who are you" in low or "what are you" in low or "your name" in low:
        return "I'm DeskBuddy, your AI desk assistant running on an ESP32-S3."
    if "what can you do" in low or "help" in low or "commands" in low:
        return (
            "Try: ask me a question from my notes, set a timer for 10 minutes, start pomodoro, "
            "add task write report, or turn on the light."
        )
    if "thank" in low:
        return "You're welcome! Happy to help."
    if "battery" in low:
        return "Check the Device page for the live battery reading."
    if "wifi" in low or "wi-fi" in low or "internet" in low:
        return "Wi-Fi status is available on the Device page."
    if any(k in low for k in ("note", "notes", "quiz", "pdf", "study")):
        return "Say 'quiz me' or 'ask me a question from my notes' to start a quiz session."
    return OFFLINE_FALLBACK
