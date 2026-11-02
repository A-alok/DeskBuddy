# oled_eye_display — vendored reference

Upstream: <https://github.com/intellar/oled_eye_display>
Write-up: <https://www.intellar.ca/blog/animated-eye-oled>
Licence: MIT, Copyright (c) 2024 Intellar — see `LICENSE` in this folder.

## Why this is here

AI DeskMate's wake animation is a port of this project's `wakeup()` pose. The
files here are an unmodified snapshot of the upstream sketch, kept so the port in
`src/animations.cpp` can be checked against what it was derived from. **Nothing in
this folder is compiled** — PlatformIO only builds `src/` and `lib/`.

Snapshot taken from `main`, 25 Sep 2026:

| File                   | Role upstream                                           |
| ---------------------- | ------------------------------------------------------- |
| `control_display.ino`  | All nine animations, plus the serial command loop        |
| `display_wrapper.h`    | Thin U8g2 / Adafruit_SSD1306 abstraction                 |
| `config.h`             | Library selection and screen dimensions                  |
| `LICENSE`              | MIT licence text                                         |

`config.h` here shares a filename with the firmware's own `include/config.h`.
That is harmless because this folder is not on any include path, but it is worth
knowing before adding `vendor/` to `build_flags`.

## What the port kept, and what it changed

Kept, because it is the reason the animation works on a one-bit panel:

- Two 40x40 rounded rectangles with a 10 px gap, not an iris-and-pupil eye. It
  reads as a character instead of an anatomical diagram.
- `REF_CORNER_RADIUS` 10, and the mapping that shrinks the radius as the eye
  closes so a nearly shut eye is a flat bar rather than a lozenge.
- `calculate_safe_radius`, which keeps the radius inside U8g2's `drawRBox`
  contract. Violating it draws a corrupt box rather than failing.
- The linear 2 px height ramp from the sleeping slit to fully open.

Changed:

- Upstream `wakeup()` is a blocking `for` loop that draws inline and lets the I2C
  write set the pace. DeskMate's loop also services a WebSocket, fires timer
  deadlines and clocks out chime samples, so it cannot sit inside an animation.
  The port derives eye height from `clocktime::monotonicMs()` on each call and
  returns immediately.
- Upstream instantiates its own `U8G2` object in `display_wrapper.h`. The port
  draws into the panel that `display::gfx()` already owns; a second instance on
  the same bus would fight the first.
- Upstream targets an SSD1306 at address 0x78; this device is an SH1106 at 0x3C.
  Only `display.cpp` cares, and it already handled it.
- The other eight animations (blink, happy, saccade, the big-eye moves, sleep)
  are not ported. They are worth revisiting for an idle-face screen.
