"""Capture serial output from the board.

`pio device monitor` attaches after the board has already booted, so the setup()
diagnostics scroll past before you can see them. By default this toggles DTR/RTS
to force a clean reset with the monitor already listening.

    python tools/boot_log.py COM5 20              reset, then capture 20s
    python tools/boot_log.py COM5 20 --no-reset   just watch, leave it running

--no-reset matters for anything interactive. Verifying that a touch does the right
thing is impossible if attaching the monitor reboots the device and throws away the
state you were trying to observe.
"""
import sys
import time

import serial

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}

PORT = args[0] if len(args) > 0 else "COM5"
SECONDS = float(args[1]) if len(args) > 1 else 12.0
RESET = "--no-reset" not in flags

ser = serial.Serial(PORT, 115200, timeout=0.2)

if RESET:
    # ESP32 reset via the USB-UART bridge: RTS drives EN (reset), DTR drives GPIO0
    # (boot mode). DTR low keeps GPIO0 high so it boots the application, not the
    # ROM bootloader.
    ser.dtr = False
    ser.rts = True
    time.sleep(0.12)
    ser.rts = False
else:
    # Park both lines so opening the port does not pulse EN. Some bridges assert
    # RTS on open, which would reset the very device we are trying not to disturb.
    ser.dtr = False
    ser.rts = False

deadline = time.time() + SECONDS
buffer = b""
while time.time() < deadline:
    chunk = ser.read(4096)
    if chunk:
        buffer += chunk
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
        sys.stdout.flush()

ser.close()
mode = "after reset" if RESET else "without resetting"
print(f"\n\n--- captured {len(buffer)} bytes from {PORT} {mode} ---")
