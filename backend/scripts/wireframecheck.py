"""Check the firmware's hand-rolled multipart body against the real backend.

src/mic.cpp does not use an HTTP library to build its upload. It lays the whole
request body out in one PSRAM buffer — multipart preamble, 44-byte WAV header, PCM,
multipart epilogue — so the DMA can write audio straight to its final address with
no copies. That is the right call for a 160 KB clip on a microcontroller, but it
means the framing is ours to get wrong.

Two independent things can break a voice command: the microphone, and the bytes
wrapped around it. This isolates the second. It rebuilds byte-for-byte what the
firmware emits, wraps a known-good WAV in it, and POSTs it as a raw body so
FastAPI's multipart parser sees exactly what the ESP32 sends. If this passes and
the device still fails, the problem is the audio, not the envelope.

    python scripts/wireframecheck.py
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
FIRMWARE_MIC = ROOT.parent.parent / "src" / "mic.cpp"
FIRMWARE_CONFIG = ROOT.parent.parent / "include" / "config.h"

DEVICE = "deskmate-01"

checks = 0
failures = 0


def check(label: str, ok: bool, detail: object = "") -> None:
    global checks, failures
    checks += 1
    if ok:
        print(f"[PASS] {label}")
    else:
        print(f"[FAIL] {label}  {detail}")
        failures += 1


def read_firmware_constant(pattern: str, path: Path) -> str | None:
    """Pull a literal out of the firmware so this cannot drift from the source."""
    text = path.read_text(encoding="utf-8", errors="replace")
    found = re.search(pattern, text)
    return found.group(1) if found else None


def extract_pcm(raw: bytes) -> bytes | None:
    """Walk the RIFF chunks and return the `data` payload.

    Not a fixed slice at offset 44. The firmware writes a canonical 44-byte header,
    but these fixtures come from Windows SAPI, which inserts extra chunks before
    `data` — so assuming 44 would feed chunk metadata to Whisper as if it were
    audio and quietly corrupt the first fraction of a second.
    """
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        return None
    offset = 12
    while offset + 8 <= len(raw):
        chunk_id = raw[offset : offset + 4]
        size = struct.unpack("<I", raw[offset + 4 : offset + 8])[0]
        payload = raw[offset + 8 : offset + 8 + size]
        if chunk_id == b"data":
            return payload
        # Chunks are word-aligned: an odd size is followed by a pad byte.
        offset += 8 + size + (size & 1)
    return None


def build_wav_header(data_bytes: int, sample_rate: int) -> bytes:
    """Mirror of writeWavHeader() in src/mic.cpp."""
    channels = 1
    bits = 16
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_bytes)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", 16)
        + struct.pack("<H", 1)
        + struct.pack("<H", channels)
        + struct.pack("<I", sample_rate)
        + struct.pack("<I", byte_rate)
        + struct.pack("<H", block_align)
        + struct.pack("<H", bits)
        + b"data"
        + struct.pack("<I", data_bytes)
    )


def build_body(boundary: str, pcm: bytes, sample_rate: int) -> bytes:
    """Mirror of the buffer layout in src/mic.cpp."""
    preamble = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
        "Content-Type: audio/wav\r\n"
        "\r\n"
    ).encode()
    epilogue = f"\r\n--{boundary}--\r\n".encode()
    return preamble + build_wav_header(len(pcm), sample_rate) + pcm + epilogue


def main() -> int:
    base = "http://127.0.0.1:8000"
    if len(sys.argv) > 1:
        base = sys.argv[1].rstrip("/")

    print("=== firmware multipart framing ===")

    boundary = read_firmware_constant(r'BOUNDARY\[\]\s*=\s*"([^"]+)"', FIRMWARE_MIC)
    check("read the boundary out of src/mic.cpp", boundary is not None, boundary)
    if boundary is None:
        return 1
    print(f"       boundary: {boundary}")

    rate_text = read_firmware_constant(
        r"#define\s+MIC_SAMPLE_RATE\s+(\d+)", FIRMWARE_CONFIG
    )
    check("read MIC_SAMPLE_RATE out of include/config.h", rate_text is not None, rate_text)
    if rate_text is None:
        return 1
    sample_rate = int(rate_text)
    check("sample rate is the 16 kHz the endpoint documents", sample_rate == 16000, sample_rate)

    # A real fixture, stripped back to raw PCM so this rebuilds the header the way
    # the firmware does rather than reusing the one in the file.
    fixture = FIXTURES / "_speech_timer.wav"
    if not fixture.exists():
        check(f"fixture {fixture.name} exists", False, "run scripts/make_test_speech.ps1")
        return 1
    raw = fixture.read_bytes()
    check("fixture is a RIFF/WAVE file", raw[:4] == b"RIFF" and raw[8:12] == b"WAVE",
          raw[:12])
    pcm = extract_pcm(raw)
    check("found a data chunk in the fixture", pcm is not None and len(pcm) > 0,
          "no data chunk")
    if not pcm:
        return 1

    body = build_body(boundary, pcm, sample_rate)
    header = build_wav_header(len(pcm), sample_rate)

    # Structural checks on the header before anything touches the network.
    check("header is 44 bytes", len(header) == 44, len(header))
    check("RIFF size field is total minus 8",
          struct.unpack("<I", header[4:8])[0] == len(pcm) + 36,
          struct.unpack("<I", header[4:8])[0])
    check("data size field matches the PCM length",
          struct.unpack("<I", header[40:44])[0] == len(pcm),
          struct.unpack("<I", header[40:44])[0])
    check("byte rate is rate * 2 for 16-bit mono",
          struct.unpack("<I", header[28:32])[0] == sample_rate * 2,
          struct.unpack("<I", header[28:32])[0])
    check("body ends with the closing boundary",
          body.endswith(f"\r\n--{boundary}--\r\n".encode()), body[-40:])
    check("no stray NUL in the body", b"\x00" not in body[: body.index(b"RIFF")],
          "preamble must be pure ASCII")

    # The real test: does FastAPI's parser accept it?
    print("\n=== POST as a raw body, exactly as the ESP32 sends it ===")
    try:
        client = httpx.Client(base_url=base, timeout=90)
        response = client.post(
            "/api/voice/transcribe",
            params={"device_id": DEVICE, "speak": "false"},
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    except httpx.HTTPError as exc:
        check("backend reachable", False, exc)
        return 1

    check("multipart parsed and transcribed (HTTP 200)", response.status_code == 200,
          f"{response.status_code} {response.text[:200]}")
    if response.status_code != 200:
        # A 422 here means the framing is wrong; anything else means the framing was
        # fine and the failure is downstream.
        if response.status_code == 422:
            print("       422 = FastAPI rejected the multipart envelope itself")
        return 1

    data = response.json()
    transcript = data.get("transcript", "")
    print(f"       transcript: {transcript!r}")
    print(f"       intent: {data.get('intent')}  action: {data.get('action_taken')}")
    check("a transcript came back", len(transcript.strip()) > 0, transcript)
    check("the file arrived whole",
          data.get("audio_bytes") == len(pcm) + 44,
          f"server saw {data.get('audio_bytes')}, we sent {len(pcm) + 44}")
    check("the transcript is the fixture's actual sentence",
          "timer" in transcript.lower(), transcript)

    print(f"\n{checks} checks, {failures} failure{'' if failures == 1 else 's'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
