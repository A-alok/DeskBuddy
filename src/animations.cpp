#include "animations.h"

#include <math.h>

#include "clock_time.h"
#include "config.h"
#include "eye_geometry.h"

namespace animations {

// --------------------------------------------------------------------------- //
// The idle face
//
// Ported from intellar/oled_eye_display (MIT, Copyright (c) 2024 Intellar).
//   https://github.com/intellar/oled_eye_display
//   Write-up: https://www.intellar.ca/blog/animated-eye-oled
// Full licence text: vendor/oled_eye_display/LICENSE
//
// What is taken verbatim: the geometry, and the two poses. A pair of rounded
// rectangles rather than a sclera/iris/pupil eye — which is the whole reason it
// reads as a character on a 1-bit panel instead of a diagram of an eyeball. The
// reference dimensions, the 10 px gap, the trick of shrinking the corner radius as
// the lid closes so a nearly shut eye is a flat bar and not a lozenge, and the
// blink that squeezes the eye wider as it closes, are all theirs.
//
// What had to change: their wakeup() and blink() are blocking `for` loops that
// draw inline and rely on the I2C write itself for pacing. This firmware's loop
// also has to service the WebSocket, run timer deadlines and clock out chime
// samples, so it cannot sit inside an animation. Every pose is derived from
// elapsed time and each call returns immediately. Same motion, no stalled loop —
// and the eyes open in the same wall-clock time whether the device is idle or
// mid-reconnect.
//
// Their sketch also cycles animations on a demo timer. Here the face is a state
// the device rests in: open, then blink forever until a touch takes it away.
//
// The arithmetic itself lives in include/eye_geometry.h, which has no Arduino or
// U8g2 dependency and is covered by test/host/test_eye_geometry.cpp. What is left
// here is only the part that needs a real panel.
// --------------------------------------------------------------------------- //

enum class FacePhase : uint8_t {
  Off,      // the menu owns the screen
  Opening,  // lids coming up from the sleeping slit
  Idle,     // open, blinking, waiting to be dismissed
};

static FacePhase phase = FacePhase::Off;
static uint64_t openStartMs = 0;
static uint64_t nextBlinkMs = 0;
static uint64_t blinkStartMs = 0;
static bool blinking = false;

// Last pose actually drawn, so an unchanged frame can be skipped. -1 means
// "nothing drawn yet", which forces the first frame out.
static int16_t lastHeight = -1;
static int16_t lastWidth = -1;

static void scheduleBlink(uint64_t from) {
  const long span = static_cast<long>(BLINK_MAX_GAP_MS - BLINK_MIN_GAP_MS);
  nextBlinkMs = from + BLINK_MIN_GAP_MS + static_cast<uint64_t>(random(span + 1));
}

/**
 * Advance the blink clock and report where it is.
 *
 * Returns progress through the current blink as 0..1, or -1 when the eyes are
 * open. Shared by the idle face and the listening face: only one of them is ever
 * on screen, so one clock is enough, and it means the blink looks the same in both
 * rather than drifting into two slightly different animations.
 */
static float blinkProgress(uint64_t now) {
  if (!blinking) {
    if (now < nextBlinkMs) return -1.0f;
    blinking = true;
    blinkStartMs = now;
  }

  const uint64_t elapsed = now - blinkStartMs;
  if (elapsed >= BLINK_DURATION_MS) {
    blinking = false;
    // Next gap measured from the end of this blink, not the start, so a long blink
    // cannot eat into the following pause.
    scheduleBlink(now);
    return -1.0f;
  }
  return static_cast<float>(elapsed) / static_cast<float>(BLINK_DURATION_MS);
}

void startFace() {
  phase = FacePhase::Opening;
  openStartMs = clocktime::monotonicMs();
  blinking = false;
  // Force the next frame to be sent: the panel may be showing anything, or
  // nothing at all if it was blanked.
  lastHeight = -1;
  lastWidth = -1;
}

void dismissFace() { phase = FacePhase::Off; }

bool faceActive() { return phase != FacePhase::Off; }

static void drawEyeBox(U8G2 &g, const eyegeom::Box &box) {
  if (box.rounded) {
    g.drawRBox(box.x, box.y, box.w, box.h, box.r);
  } else {
    g.drawBox(box.x, box.y, box.w, box.h);
  }
}

bool drawFace(U8G2 &g) {
  if (phase == FacePhase::Off) return false;

  const uint64_t now = clocktime::monotonicMs();
  eyegeom::Box left{};
  eyegeom::Box right{};

  if (phase == FacePhase::Opening) {
    const uint64_t elapsed = now - openStartMs;
    if (elapsed < WAKE_OPEN_MS) {
      eyegeom::eyesOpening(
          static_cast<float>(elapsed) / static_cast<float>(WAKE_OPEN_MS), left,
          right);
    } else {
      // Lids are up. From here on the face just blinks.
      phase = FacePhase::Idle;
      scheduleBlink(now);
      eyegeom::eyesOpening(1.0f, left, right);
    }
  } else {
    const float p = blinkProgress(now);
    if (p >= 0.0f) {
      eyegeom::eyesBlinking(p, left, right);
    } else {
      eyegeom::eyesOpening(1.0f, left, right);
    }
  }

  // Height and width fully determine the frame — the radius derives from height
  // and the centres never move — so this comparison is exact, not a heuristic.
  if (left.h == lastHeight && left.w == lastWidth) return false;
  lastHeight = left.h;
  lastWidth = left.w;

  g.setDrawColor(1);
  drawEyeBox(g, left);
  drawEyeBox(g, right);
  return true;
}

// --------------------------------------------------------------------------- //
// The listening face
//
// Same character as the idle face, wearing ears. Eyes squint and drop, brows come
// in above them and lift with the room, and concentric arcs at both panel edges
// fill from the inside out as you speak.
//
// This replaced a scrolling bar waveform. The waveform was a more faithful picture
// of the audio, and that turned out to be the problem: it looked like an
// instrument, so the device stopped looking like it was paying attention to you and
// started looking like it was measuring you. Ears are less precise and read
// correctly from across a desk, which is the only distance that matters here.
// --------------------------------------------------------------------------- //

// Smoothed loudness, 0..1, driving the brows and the ears.
static float envelope = 0.0f;
static uint64_t lastLevelMs = 0;
static bool anyLevels = false;

void beginListening() {
  envelope = 0.0f;
  anyLevels = false;
  lastLevelMs = 0;
  // Start the gap from now, so the session opens with the eyes definitely open.
  scheduleBlink(clocktime::monotonicMs());
  blinking = false;
}

void pushAudioLevel(float level) {
  if (level < 0.0f) level = 0.0f;
  if (level > 1.0f) level = 1.0f;

  // Fast attack, slow release. Raw per-chunk peaks jitter hard enough to make the
  // brows buzz; this tracks a syllable starting almost immediately but decays over
  // a couple of hundred milliseconds, which is what makes the face look like it is
  // following speech rather than vibrating.
  const float coefficient = level > envelope ? 0.55f : 0.08f;
  envelope += (level - envelope) * coefficient;

  lastLevelMs = clocktime::monotonicMs();
  anyLevels = true;
}

bool hasLiveAudio() {
  // Half a second without a sample and we stop claiming this is real sound.
  return anyLevels && (clocktime::monotonicMs() - lastLevelMs) < 500;
}

/** Current smoothed loudness, 0..1. Decays to nothing once samples stop. */
static float currentLevel() {
  if (!hasLiveAudio()) return 0.0f;
  return envelope;
}

/** One ear: a filled canal on the panel edge, then whichever arcs are lit. */
static void drawEar(U8G2 &g, int16_t x, bool facingRight, int16_t ripple,
                    float level) {
  const uint8_t half = facingRight
                           ? (U8G2_DRAW_UPPER_RIGHT | U8G2_DRAW_LOWER_RIGHT)
                           : (U8G2_DRAW_UPPER_LEFT | U8G2_DRAW_LOWER_LEFT);

  g.drawDisc(x, eyegeom::LISTEN_CENTRE_Y, 3, half);

  for (int16_t i = 0; i < eyegeom::EAR_ARC_COUNT; ++i) {
    if (!eyegeom::earArcLit(i, ripple, level)) continue;
    g.drawCircle(x, eyegeom::LISTEN_CENTRE_Y, eyegeom::EAR_ARC_RADII[i], half);
  }
}

/** One brow: three segments, 2 px thick, forming a shallow arch over an eye. */
static void drawBrow(U8G2 &g, int16_t cx, int16_t y) {
  const int16_t outer = eyegeom::BROW_HALF_WIDTH;
  const int16_t inner = 5;
  // Drawn twice, one row apart. A single-pixel brow disappears next to a 40 px
  // block of solid eye.
  for (int16_t row = 0; row < 2; ++row) {
    const int16_t yy = static_cast<int16_t>(y + row);
    g.drawLine(cx - outer, yy + 3, cx - inner, yy);
    g.drawHLine(cx - inner, yy, inner * 2);
    g.drawLine(cx + inner, yy, cx + outer, yy + 3);
  }
}

void drawListening(U8G2 &g, float secondsLeft) {
  const uint64_t ms = clocktime::monotonicMs();
  const float level = currentLevel();

  g.setDrawColor(1);

  eyegeom::Box left{};
  eyegeom::Box right{};
  eyegeom::eyesListening(blinkProgress(ms), left, right);
  drawEyeBox(g, left);
  drawEyeBox(g, right);

  const int16_t brow = eyegeom::browY(level);
  drawBrow(g, eyegeom::leftCentreX(), brow);
  drawBrow(g, eyegeom::rightCentreX(), brow);

  // Walks 0,1,2 then rests. The rest beat is what makes the direction readable —
  // without it the three arcs just flicker and the motion has no outward sense.
  const int16_t ripple = static_cast<int16_t>((ms / EAR_RIPPLE_STEP_MS) %
                                              (eyegeom::EAR_ARC_COUNT + 1));
  drawEar(g, eyegeom::LEFT_EAR_X, true, ripple, level);
  drawEar(g, eyegeom::RIGHT_EAR_X, false, ripple, level);

  // Remaining time, as a bare shrinking rule on the bottom edge. No frame, no
  // digits: it only has to answer "how much longer", and anything heavier competes
  // with the face for attention.
  if (secondsLeft >= 0.0f) {
    float fraction = secondsLeft / VOICE_RECORD_SECONDS;
    if (fraction < 0.0f) fraction = 0.0f;
    if (fraction > 1.0f) fraction = 1.0f;
    const int16_t width = static_cast<int16_t>(120.0f * fraction);
    if (width > 0) g.drawBox(static_cast<int16_t>(4 + (120 - width) / 2), 61, width, 2);
  }
}

void drawThinking(U8G2 &g, const char *caption) {
  g.setDrawColor(1);
  g.setFont(u8g2_font_helvB10_tr);
  const char *title = caption != nullptr ? caption : "THINKING";
  const int16_t titleWidth = g.getStrWidth(title);
  g.setCursor((128 - titleWidth) / 2, 28);
  g.print(title);

  // Three dots rising in sequence. Period chosen to feel unhurried rather than
  // urgent — this appears while waiting on a network round trip.
  const uint64_t ms = clocktime::monotonicMs();
  const uint8_t active = static_cast<uint8_t>((ms / 260) % 3);
  for (uint8_t i = 0; i < 3; ++i) {
    const int16_t cx = 52 + i * 12;
    if (i == active) {
      g.drawDisc(cx, 44, 4, U8G2_DRAW_ALL);
    } else {
      g.drawCircle(cx, 46, 3, U8G2_DRAW_ALL);
    }
  }
}

}  // namespace animations
