"""End-to-end voice pipeline test using pre-recorded speech.

    cd backend
    powershell -ExecutionPolicy Bypass -File scripts\make_test_speech.ps1   # once
    .\.venv\Scripts\python.exe scripts\voicecheck.py

Posts 16 kHz mono WAVs — the same format the INMP441 capture produces — through
POST /api/voice/transcribe and checks each one reaches the right intent AND that
the action really happened. This is how the voice path stays testable when the
microphone is unwired, unreliable, or you simply cannot speak out loud.

Requires the backend to be running.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

DEVICE = "deskmate-01"


def host_from_secrets() -> str:
    """Use the same backend the firmware was flashed with."""
    import re

    secrets = ROOT.parent / "include" / "secrets.h"
    if secrets.exists():
        text = secrets.read_text(encoding="utf-8", errors="replace")
        host = re.search(r'#define\s+BACKEND_HOST\s+"([^"]+)"', text)
        port = re.search(r"#define\s+BACKEND_PORT\s+(\d+)", text)
        if host:
            return f"http://{host.group(1)}:{port.group(1) if port else '8000'}"
    return "http://127.0.0.1:8000"


fails: list[str] = []


def check(label: str, ok: bool, extra: object = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f"  <- {extra}"))
    if not ok:
        fails.append(label)


# (fixture, expected intent, human label)
CASES = [
    ("_speech_timer.wav", "timer.start", "timer"),
    ("_speech_wx.wav", "weather.current", "weather"),
    ("_speech_relay.wav", "relay.on", "relay"),
    ("_speech_chat.wav", "chat", "open question"),
]


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else host_from_secrets()
    print(f"backend: {base}\n")

    if not FIXTURES.exists() or not any(FIXTURES.glob("_speech_*.wav")):
        print("No fixtures found. Generate them first:")
        print(r"  powershell -ExecutionPolicy Bypass -File scripts\make_test_speech.ps1")
        return 1

    c = httpx.Client(base_url=base, timeout=90, params={"device_id": DEVICE})

    print("=== POST /api/voice/transcribe ===")
    for name, expected_intent, label in CASES:
        path = FIXTURES / name
        if not path.exists():
            check(f"{name} exists", False, "re-run make_test_speech.ps1")
            continue

        raw = path.read_bytes()
        r = c.post(
            "/api/voice/transcribe",
            params={"device_id": DEVICE, "speak": "false"},
            files={"file": (path.name, raw, "audio/wav")},
        )
        if r.status_code != 200:
            check(f"{label}: 200", False, f"{r.status_code} {r.text[:250]}")
            continue

        b = r.json()
        print(f"\n  {label}: {len(raw)//1024} kB / {b['audio_seconds']:.2f}s audio")
        print(f"    transcript: '{b['transcript']}'")
        print(f"    intent={b['intent']}  action={b['action_taken']}  provider={b['provider']}")
        print(f"    reply: {b['reply'][:110]}")
        print(f"    whisper {b['transcribe_ms']} ms, total {b['total_ms']} ms")

        check(f"{label}: transcribed something", bool(b["transcript"].strip()))
        check(f"{label}: transcript is trimmed",
              b["transcript"] == b["transcript"].strip(), repr(b["transcript"]))
        check(f"{label}: intent == {expected_intent}",
              b["intent"] == expected_intent, f"got {b['intent']}")
        check(f"{label}: got a reply", bool(b["reply"].strip()))
        check(f"{label}: duration reported", b["audio_seconds"] is not None)

    # A reply is not proof. Confirm the side effects.
    print("\n=== did the actions actually happen? ===")
    t = c.get("/api/timer/status").json()
    check("the spoken timer is running", bool(t) and t["state"] == "running",
          t.get("state") if t else "no timer")
    if t:
        check("spoken '10 minutes' -> 600s", t["duration_seconds"] == 600, t["duration_seconds"])
    c.post("/api/timer/stop")

    d = c.get("/api/device/status").json()
    check("the spoken relay command switched it on", d["relay_on"] is True, d["relay_on"])
    c.post("/api/device/relay", json={"on": False})

    cmds = c.get("/api/voice/commands", params={"device_id": DEVICE, "limit": 10}).json()
    check("commands logged with source=voice", any(x["source"] == "voice" for x in cmds))

    print("\n=== failure handling ===")
    r = c.post("/api/voice/transcribe", params={"device_id": DEVICE},
               files={"file": ("empty.wav", b"", "audio/wav")})
    check("empty upload -> 502 with an explanation", r.status_code == 502, r.status_code)

    r = c.post("/api/voice/transcribe", params={"device_id": DEVICE},
               files={"file": ("junk.wav", b"not audio" * 200, "audio/wav")})
    check("garbage upload -> error, not a crash", r.status_code >= 400, r.status_code)

    c.close()
    print()
    if fails:
        print(f"{len(fails)} FAILURE(S): " + ", ".join(fails))
        return 1
    print("VOICE PIPELINE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
