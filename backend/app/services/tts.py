"""Text-to-speech via Microsoft Edge TTS (free, no API key).

Same philosophy as Open-Meteo for weather: no account, no key, no quota to hit.
Edge TTS returns MP3; we decode to raw 16-bit PCM at the sample rate the ESP32
expects so the firmware can play it straight off the wire with no decoder.

The voice is configurable via TTS_VOICE in .env, defaulting to en-IN-NeerjaNeural
(Indian English, female, clear).
"""

from __future__ import annotations

import io
import logging
import re
import struct
import time
from typing import Optional

log = logging.getLogger(__name__)

# edge-tts is async (uses aiohttp internally), so it fits FastAPI's async model.
try:
    import edge_tts

    _EDGE_AVAILABLE = True
except ImportError:
    _EDGE_AVAILABLE = False
    log.warning("[tts] edge-tts not installed — TTS will be unavailable")


def available() -> bool:
    return _EDGE_AVAILABLE


def _clean_for_speech(text: str) -> str:
    """Strip emojis, markdown formatting, and non-spoken markers for natural TTS."""
    if not text:
        return ""
    # Strip emojis and non-standard symbols
    s = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    s = re.sub(r"[\u2600-\u27bf\u2300-\u23ff]", "", s)
    # Clean common tags into natural phrasing
    s = s.replace("🎯 Evaluation:", "Evaluation: ")
    s = s.replace("💡 Suggestion:", "Tip: ")
    s = s.replace("📝 Next Question", "Next Question")
    s = s.replace("💡 Speak your answer, or say 'no' to finish.", "Speak your answer, or say no to stop.")
    # Remove markdown bullets, bold/italic asterisks, hash headers
    s = re.sub(r"[*_#`]", "", s)
    s = re.sub(r"^[•\-]\s*", "", s, flags=re.MULTILINE)
    # Collapse multiple newlines into a short pause / period
    lines = [line.strip() for line in s.splitlines() if line.strip()]
    return ". ".join(lines)


async def synthesize(
    text: str,
    voice: str = "en-IN-NeerjaNeural",
    sample_rate: int = 22050,
) -> Optional[bytes]:
    """Convert text to a WAV file (16-bit mono PCM at the requested sample rate).

    Returns the complete WAV bytes, or None if synthesis fails.
    The WAV can be streamed directly to the ESP32's I2S driver after skipping the
    44-byte header.
    """
    if not _EDGE_AVAILABLE:
        log.warning("[tts] edge-tts not installed")
        return None

    speech_text = _clean_for_speech(text)
    if not speech_text:
        return None

    started = time.perf_counter()

    try:
        # edge-tts returns MP3 chunks. Collect them all.
        communicate = edge_tts.Communicate(speech_text, voice)
        mp3_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_chunks.append(chunk["data"])

        if not mp3_chunks:
            log.warning("[tts] edge-tts returned no audio chunks")
            return None

        mp3_data = b"".join(mp3_chunks)

        # Decode MP3 → raw PCM using miniaudio (self-contained, no ffmpeg).
        import miniaudio

        decoded = miniaudio.decode(
            mp3_data,
            nchannels=1,
            sample_rate=sample_rate,
            output_format=miniaudio.SampleFormat.SIGNED16,
        )

        # decoded.samples is an array.array of signed 16-bit integers.
        pcm_data = decoded.samples.tobytes()

        # Build the WAV file: 44-byte header + PCM data.
        wav = _build_wav(pcm_data, sample_rate)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        duration_s = len(pcm_data) / (sample_rate * 2)  # 2 bytes per sample
        log.info(
            "[tts] synthesised %.1fs of audio in %d ms (%d bytes WAV)",
            duration_s,
            elapsed_ms,
            len(wav),
        )
        return wav

    except Exception:
        log.exception("[tts] synthesis failed")
        return None


def _build_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM in a standard WAV header."""
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm)
    file_size = 36 + data_size  # 44 - 8 (RIFF header) + data

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        file_size,
        b"WAVE",
        b"fmt ",
        16,  # chunk size
        1,  # PCM format
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm
