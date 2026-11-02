"""Small CLI for poking the running backend while testing the device.

    python scripts\devtool.py status
    python scripts\devtool.py alarms --seed
    python scripts\devtool.py timer 10          # minutes
    python scripts\devtool.py timer 5 --seconds
    python scripts\devtool.py relay on
    python scripts\devtool.py pomodoro start
    python scripts\devtool.py chat "why use absolute timestamps?"
    python scripts\devtool.py watch 60          # stream events as the device acts

Exists because PowerShell quoting mangles multi-line Invoke-WebRequest calls, and
because these are the commands you actually need over and over during bring-up.

The backend address is read from `include/secrets.h` — the same BACKEND_HOST the
firmware was flashed with, so this tool and the device can never disagree about
where the backend is. Override with --host.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

DEVICE = os.environ.get("DEVICE_ID", "deskmate-01")

SECRETS_H = ROOT.parent / "include" / "secrets.h"


def host_from_secrets() -> str | None:
    """Read BACKEND_HOST/PORT out of the firmware's secrets.h.

    Using the firmware's own value means this tool automatically follows the
    device after a network change, instead of being a second place to update.
    """
    if not SECRETS_H.exists():
        return None
    import re

    text = SECRETS_H.read_text(encoding="utf-8", errors="replace")
    host = re.search(r'#define\s+BACKEND_HOST\s+"([^"]+)"', text)
    port = re.search(r"#define\s+BACKEND_PORT\s+(\d+)", text)
    if not host:
        return None
    return f"http://{host.group(1)}:{port.group(1) if port else '8000'}"


def client(host: str) -> httpx.Client:
    return httpx.Client(base_url=host, timeout=45, params={"device_id": DEVICE})


def show(label: str, data: object) -> None:
    print(f"\n{label}")
    print(json.dumps(data, indent=2, default=str)[:2000])


def cmd_status(c: httpx.Client, _args) -> None:
    d = c.get("/api/device/status").json()
    print(
        f"online={d['online']}  ws={d['websocket_connected']}  ip={d['ip_address']}\n"
        f"ssid={d['wifi_ssid']}  rssi={d['wifi_rssi']}  fw={d['firmware_version']}\n"
        f"heap={(d['free_heap_bytes'] or 0)//1024} KB  uptime={d['uptime_seconds']}s\n"
        f"screen={d['current_screen']}  relay={'ON' if d['relay_on'] else 'off'}"
    )
    h = c.get("/health").json()
    print(
        f"\nbackend: db={h['database']['status']}  ai={h['ai']['mode']}  "
        f"devices={h['connections']['devices']}  dashboards={h['connections']['dashboards']}"
    )


def cmd_alarms(c: httpx.Client, args) -> None:
    # Clear before seeding, or --clear --seed deletes what it just made.
    if args.clear:
        for a in c.get("/api/alarms").json():
            c.delete(f"/api/alarms/{a['id']}")
            print(f"deleted {a['time_of_day']} '{a['label']}'")

    if args.seed:
        # Two alarms: one repeating on weekdays, one single-shot. Enough to test
        # the Alarms screen's cursor and its enable/disable toggle.
        for label, when, days in (
            ("Wake", "07:30", [0, 1, 2, 3, 4]),
            ("Evening", "21:15", []),
        ):
            r = c.post(
                "/api/alarms",
                json={"label": label, "time_of_day": when, "days_of_week": days},
            )
            if r.status_code == 201:
                a = r.json()
                print(f"created {a['time_of_day']} '{a['label']}' next={a['next_trigger_at']}")
            else:
                print(f"failed ({r.status_code}): {r.text[:200]}")

    alarms = c.get("/api/alarms").json()
    print(f"\n{len(alarms)} alarm(s) on the backend:")
    for a in alarms:
        state = "on " if a["enabled"] else "off"
        print(f"  {a['time_of_day']}  {state}  days={a['days_of_week']}  '{a['label']}'")


def cmd_timer(c: httpx.Client, args) -> None:
    body = {"seconds": args.amount} if args.seconds else {"minutes": args.amount}
    body["label"] = args.label
    r = c.post("/api/timer/start", json=body)
    t = r.json()
    print(f"timer {t['state']}  {t['remaining_seconds']}s  ends_at={t['ends_at']}")


def cmd_stop(c: httpx.Client, _args) -> None:
    r = c.post("/api/timer/stop")
    print(f"timer -> {r.json().get('state') if r.status_code == 200 else r.text[:200]}")


def cmd_relay(c: httpx.Client, args) -> None:
    d = c.post("/api/device/relay", json={"on": args.state == "on"}).json()
    print(f"relay -> {'ON' if d['relay_on'] else 'off'}")


def cmd_pomodoro(c: httpx.Client, args) -> None:
    paths = {
        "start": "/api/pomodoro/start",
        "pause": "/api/pomodoro/pause",
        "resume": "/api/pomodoro/resume",
        "stop": "/api/pomodoro/stop",
        "skip": "/api/pomodoro/skip",
    }
    body = {} if args.action != "start" else {"focus_minutes": args.minutes}
    r = c.post(paths[args.action], json=body)
    if r.status_code != 200:
        print(f"failed ({r.status_code}): {r.text[:200]}")
        return
    p = r.json()
    print(f"pomodoro {p['phase']}/{p['state']}  {p['remaining_seconds']}s  cycles={p['completed_focus_cycles']}")


def cmd_chat(c: httpx.Client, args) -> None:
    r = c.post("/api/chat", json={"message": args.message, "speak": args.speak}).json()
    print(f"provider={r['provider']}  intent={r['intent']}  action={r['action_taken']}")
    print(f"reply: {r['reply']}")


def cmd_tz(c: httpx.Client, args) -> None:
    """Set the device timezone offset the backend uses for alarm scheduling.

    This MUST match DESKMATE_TZ in the firmware's config.h. Alarms are wall-clock
    ("07:30"), and the backend and the device each resolve that to an absolute
    instant independently. If the offsets disagree, the same alarm fires at two
    different times — which looks like a scheduling bug and is a config mismatch.
    IST is 330.
    """
    r = c.put("/api/settings", json={"values": {"tz_offset_minutes": args.minutes}})
    values = r.json()["values"]
    print(f"tz_offset_minutes = {values['tz_offset_minutes']}")
    print("Existing alarms keep their old next_trigger_at — re-create them, or")
    print("PATCH each one, to recompute against the new offset.")


def cmd_settings(c: httpx.Client, _args) -> None:
    for key, value in sorted(c.get("/api/settings").json()["values"].items()):
        print(f"  {key:<22} {value}")


def cmd_snapshot(c: httpx.Client, _args) -> None:
    s = c.get("/api/snapshot").json()
    show("snapshot", {k: s[k] for k in ("server_time", "device", "timer", "stopwatch", "pomodoro")})


def cmd_events(c: httpx.Client, args) -> None:
    rows = c.get("/api/device/events", params={"device_id": DEVICE, "limit": args.limit}).json()
    print(f"last {len(rows)} events:")
    for row in rows:
        print(f"  {row['created_at'][11:19]}  {row['type']:<26} from {row['origin']}")


async def watch(host: str, seconds: int) -> None:
    """Stream the WebSocket so device-originated events show up live."""
    import websockets

    url = host.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{url}/ws?role=dashboard&device_id={DEVICE}"
    print(f"watching {url} for {seconds}s — act on the device now\n")

    async with websockets.connect(url) as ws:
        try:
            async with asyncio.timeout(seconds):
                while True:
                    frame = json.loads(await ws.recv())
                    kind = frame.get("type", "?")
                    if kind in {"pong", "device.status"}:
                        continue
                    payload = frame.get("payload") or {}
                    detail = ""
                    for key in ("state", "phase", "on", "screen", "gesture", "label", "title", "text"):
                        if key in payload:
                            detail += f" {key}={payload[key]}"
                    print(f"{frame.get('ts','')[11:19]}  {kind:<26} from {frame.get('origin','?'):<9}{detail}")
        except (TimeoutError, asyncio.TimeoutError):
            print("\nwatch window ended")


def cmd_watch(_c: httpx.Client, args) -> None:
    asyncio.run(watch(args.host, args.seconds))


def main() -> int:
    from app.config import settings

    default_host = host_from_secrets() or f"http://127.0.0.1:{settings.port}"

    parser = argparse.ArgumentParser(description="Poke the DeskMate backend")
    parser.add_argument(
        "--host", default=default_host,
        help=f"backend base URL (default from include/secrets.h: {default_host})",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(fn=cmd_status)

    p = sub.add_parser("alarms")
    p.add_argument("--seed", action="store_true", help="create two test alarms")
    p.add_argument("--clear", action="store_true", help="delete all alarms first")
    p.set_defaults(fn=cmd_alarms)

    p = sub.add_parser("timer")
    p.add_argument("amount", type=int)
    p.add_argument("--seconds", action="store_true", help="treat amount as seconds")
    p.add_argument("--label", default="Test")
    p.set_defaults(fn=cmd_timer)

    sub.add_parser("stop").set_defaults(fn=cmd_stop)

    p = sub.add_parser("relay")
    p.add_argument("state", choices=["on", "off"])
    p.set_defaults(fn=cmd_relay)

    p = sub.add_parser("pomodoro")
    p.add_argument("action", choices=["start", "pause", "resume", "stop", "skip"])
    p.add_argument("--minutes", type=int, default=25)
    p.set_defaults(fn=cmd_pomodoro)

    p = sub.add_parser("chat")
    p.add_argument("message")
    p.add_argument("--speak", action="store_true")
    p.set_defaults(fn=cmd_chat)

    p = sub.add_parser("tz", help="set tz_offset_minutes (IST = 330)")
    p.add_argument("minutes", type=int)
    p.set_defaults(fn=cmd_tz)

    sub.add_parser("settings").set_defaults(fn=cmd_settings)

    sub.add_parser("snapshot").set_defaults(fn=cmd_snapshot)

    p = sub.add_parser("events")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_events)

    p = sub.add_parser("watch")
    p.add_argument("seconds", type=int, nargs="?", default=60)
    p.set_defaults(fn=cmd_watch)

    args = parser.parse_args()

    try:
        with client(args.host) as c:
            args.fn(c, args)
    except httpx.HTTPError as exc:
        print(f"cannot reach {args.host}: {exc}")
        print("Is uvicorn running, and is --host correct for this network?")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
