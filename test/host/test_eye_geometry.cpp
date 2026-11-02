/**
 * Host test for include/eye_geometry.h — the wake animation's arithmetic.
 * Runs on your PC, no board needed:
 *
 *   g++ -std=c++17 -Wall -Wextra -I include test/host/test_eye_geometry.cpp -o eye_test
 *   ./eye_test
 *
 * PlatformIO ignores test/ during `pio run`, so this does not affect the
 * firmware build.
 *
 * Why bother: every failure mode of this animation is arithmetic. A box that
 * runs off the panel, or a corner radius that breaks U8g2's drawRBox contract,
 * shows up on hardware as garbage pixels with no error — and diagnosing that by
 * flashing and squinting at a 1.3" panel is slow. Cheaper to assert it here.
 *
 * Pass --render to print the frames as ASCII and actually look at the motion.
 */

#include <cmath>
#include <cstdio>
#include <cstring>

#include "eye_geometry.h"

using eyegeom::Box;

static int failures = 0;
static int checks = 0;

static void expectTrue(const char *label, bool condition) {
  ++checks;
  if (condition) {
    printf("[PASS] %s\n", label);
  } else {
    printf("[FAIL] %s\n", label);
    ++failures;
  }
}

static void expectEqInt(const char *label, long actual, long expected) {
  ++checks;
  if (actual == expected) {
    printf("[PASS] %s\n", label);
  } else {
    printf("[FAIL] %s  expected %ld, got %ld\n", label, expected, actual);
    ++failures;
  }
}

// --------------------------------------------------------------------------- //
// Checks applied to every frame
// --------------------------------------------------------------------------- //

/** Returns an error string, or nullptr when the box is drawable. */
static const char *validate(const Box &b) {
  if (b.w <= 0 || b.h <= 0) return "non-positive size";
  if (b.x < 0 || b.y < 0) return "negative origin";
  if (b.x + b.w > eyegeom::PANEL_WIDTH) return "runs off the right edge";
  if (b.y + b.h > eyegeom::PANEL_HEIGHT) return "runs off the bottom edge";
  if (b.r < 0) return "negative radius";
  if (b.rounded) {
    // U8g2's drawRBox requires 2*(r+1) <= both dimensions. This is the check
    // that matters: breaking it renders corrupt, it does not fail loudly.
    if (2 * (b.r + 1) > b.w) return "radius too large for width";
    if (2 * (b.r + 1) > b.h) return "radius too large for height";
  } else if (b.r != 0) {
    return "unrounded box carries a non-zero radius";
  }
  return nullptr;
}

/** How a pose is produced, so one sweep can cover both animations. */
using PoseFn = void (*)(float, Box &, Box &);

/**
 * Walk a pose function across its whole input range and check every frame.
 *
 * 512 steps is far finer than the handful of frames the device actually draws, so
 * no reachable input is skipped — including the ones an unlucky frame interval
 * would land on.
 */
static void sweep(const char *what, PoseFn pose, bool expectMonotonic) {
  const int steps = 512;
  bool allValid = true;
  bool symmetric = true;
  bool monotonic = true;
  int16_t previousHeight = -1;
  char detail[192] = "";
  char label[96];

  for (int i = 0; i <= steps; ++i) {
    const float t = static_cast<float>(i) / static_cast<float>(steps);
    Box left{};
    Box right{};
    pose(t, left, right);

    const char *leftError = validate(left);
    const char *rightError = validate(right);
    if (leftError != nullptr || rightError != nullptr) {
      if (allValid) {
        snprintf(detail, sizeof(detail),
                 "t=%.4f left(%d,%d %dx%d r%d)=%s right(%d,%d %dx%d r%d)=%s", t,
                 left.x, left.y, left.w, left.h, left.r,
                 leftError ? leftError : "ok", right.x, right.y, right.w,
                 right.h, right.r, rightError ? rightError : "ok");
      }
      allValid = false;
    }

    // The two eyes must mirror about the panel centre, or the face looks broken.
    if (left.h != right.h || left.w != right.w || left.y != right.y ||
        left.r != right.r ||
        (left.x + left.w / 2) + (right.x + right.w / 2) != eyegeom::PANEL_WIDTH) {
      symmetric = false;
    }

    if (previousHeight >= 0 && left.h < previousHeight) monotonic = false;
    previousHeight = left.h;
  }

  snprintf(label, sizeof(label), "%s: every frame is drawable", what);
  expectTrue(label, allValid);
  if (detail[0] != '\0') printf("       first bad frame: %s\n", detail);

  snprintf(label, sizeof(label), "%s: eyes stay mirrored about the centre", what);
  expectTrue(label, symmetric);

  if (expectMonotonic) {
    snprintf(label, sizeof(label), "%s: height never decreases", what);
    expectTrue(label, monotonic);
  }
}

// --------------------------------------------------------------------------- //
// Endpoints and upstream parity
// --------------------------------------------------------------------------- //

static void endpoints() {
  Box left{};
  Box right{};

  eyegeom::eyesOpening(0.0f, left, right);
  expectEqInt("asleep: height is the 2 px slit", left.h, eyegeom::SLEEP_EYE_HEIGHT);
  expectEqInt("asleep: width already full", left.w, eyegeom::REF_EYE_WIDTH);
  expectTrue("asleep: slit is too thin to round", !left.rounded);
  expectEqInt("asleep: slit is vertically centred", left.y,
              eyegeom::PANEL_HEIGHT / 2 - eyegeom::SLEEP_EYE_HEIGHT / 2);

  eyegeom::eyesOpening(1.0f, left, right);
  expectEqInt("open: height is the reference 40", left.h, eyegeom::REF_EYE_HEIGHT);
  expectEqInt("open: full corner radius", left.r, eyegeom::REF_CORNER_RADIUS);
  expectTrue("open: drawn rounded", left.rounded);
  // 128/2 - 40/2 - 10/2 = 39 centre, so the box starts at 19.
  expectEqInt("open: left box starts at x=19", left.x, 19);
  expectEqInt("open: right box ends at x=109", right.x + right.w, 109);
  expectEqInt("open: 10 px gap between the eyes", right.x - (left.x + left.w),
              eyegeom::REF_SPACE_BETWEEN_EYE);
  expectEqInt("open: vertically centred", left.y, 12);

  // Out-of-range t must clamp rather than extrapolate off the panel.
  eyegeom::eyesOpening(-5.0f, left, right);
  expectEqInt("t below 0 clamps shut", left.h, eyegeom::SLEEP_EYE_HEIGHT);
  eyegeom::eyesOpening(9.0f, left, right);
  expectEqInt("t above 1 clamps open", left.h, eyegeom::REF_EYE_HEIGHT);
}

static void blinkPose() {
  Box left{};
  Box right{};

  // A blink has to start and end exactly where the idle face sits, or it shows as
  // a jump into and out of the animation.
  Box idleLeft{};
  Box idleRight{};
  eyegeom::eyesOpening(1.0f, idleLeft, idleRight);

  eyegeom::eyesBlinking(0.0f, left, right);
  expectTrue("blink starts from the open pose",
             left.h == idleLeft.h && left.w == idleLeft.w && left.x == idleLeft.x &&
                 left.y == idleLeft.y && left.r == idleLeft.r);

  eyegeom::eyesBlinking(1.0f, left, right);
  expectTrue("blink ends on the open pose",
             left.h == idleLeft.h && left.w == idleLeft.w && left.x == idleLeft.x &&
                 left.y == idleLeft.y && left.r == idleLeft.r);

  eyegeom::eyesBlinking(0.5f, left, right);
  expectEqInt("blink bottoms out at 4 px tall", left.h, eyegeom::BLINK_MIN_HEIGHT);
  expectEqInt("blink bulges to 49 px wide", left.w, eyegeom::BLINK_MAX_WIDTH);
  expectTrue("blink never fully closes", left.h > 0);
  // The widest pose is where the eyes come closest to each other and to the panel
  // edges. If anything in this animation runs out of bounds, it is here.
  expectEqInt("widest pose still starts on-panel", left.x, 15);
  expectEqInt("widest pose still ends on-panel", right.x + right.w, 114);
  expectTrue("widest pose keeps the eyes separate", right.x > left.x + left.w);

  // Symmetry of the curve: equal distances either side of the midpoint match.
  Box earlyL{}, earlyR{}, lateL{}, lateR{};
  eyegeom::eyesBlinking(0.25f, earlyL, earlyR);
  eyegeom::eyesBlinking(0.75f, lateL, lateR);
  expectTrue("blink closes and opens symmetrically",
             earlyL.h == lateL.h && earlyL.w == lateL.w);
}

static void listeningFace() {
  Box left{};
  Box right{};

  eyegeom::eyesListening(-1.0f, left, right);
  expectEqInt("listening: eyes squint to 30", left.h, eyegeom::LISTEN_EYE_HEIGHT);
  expectEqInt("listening: width unchanged from the idle face", left.w,
              eyegeom::REF_EYE_WIDTH);
  expectEqInt("listening: x centres match the idle face", left.x, 19);
  expectEqInt("listening: eyes sit lower to clear the brows", left.y,
              eyegeom::LISTEN_CENTRE_Y - eyegeom::LISTEN_EYE_HEIGHT / 2);
  expectTrue("listening: drawable", validate(left) == nullptr);

  // --- ears must not collide with anything --------------------------------- //
  int16_t widestArc = 0;
  for (int16_t i = 0; i < eyegeom::EAR_ARC_COUNT; ++i) {
    if (eyegeom::EAR_ARC_RADII[i] > widestArc) widestArc = eyegeom::EAR_ARC_RADII[i];
  }
  // This is the check that earns its keep. The eyes and the ears are positioned
  // independently, so a tweak to either silently overlaps them, and on a 1-bit
  // panel an overlap is not subtly wrong — the shapes merge into a blob.
  expectTrue("left ear clears the left eye",
             eyegeom::LEFT_EAR_X + widestArc < left.x);
  expectTrue("right ear clears the right eye",
             eyegeom::RIGHT_EAR_X - widestArc > right.x + right.w);
  expectTrue("ears stay on the panel vertically",
             eyegeom::LISTEN_CENTRE_Y - widestArc >= 0 &&
                 eyegeom::LISTEN_CENTRE_Y + widestArc < eyegeom::PANEL_HEIGHT);
  expectTrue("ear arcs are ordered innermost first",
             eyegeom::EAR_ARC_RADII[0] < eyegeom::EAR_ARC_RADII[1] &&
                 eyegeom::EAR_ARC_RADII[1] < eyegeom::EAR_ARC_RADII[2]);

  // --- brows --------------------------------------------------------------- //
  const int16_t quietBrow = eyegeom::browY(0.0f);
  const int16_t loudBrow = eyegeom::browY(1.0f);
  expectEqInt("brow rests at the base line", quietBrow, eyegeom::BROW_BASE_Y);
  expectEqInt("brow lifts by the full amount at full volume", loudBrow,
              eyegeom::BROW_BASE_Y - eyegeom::BROW_MAX_LIFT);
  expectTrue("brows lift, never drop", loudBrow < quietBrow);
  // The brow is drawn two rows thick and its outer ends sit 3 px lower than its
  // baseline, so the lowest ink it puts down is baseline + 4.
  expectTrue("quiet brow still clears the eye top", quietBrow + 4 < left.y);
  expectTrue("brow stays on the panel", loudBrow >= 0);
  expectTrue("brow is narrower than the eye it sits over",
             eyegeom::BROW_HALF_WIDTH * 2 <= eyegeom::REF_EYE_WIDTH);

  // --- ear arc lighting ---------------------------------------------------- //
  // Silence must still animate, or the screen looks frozen mid-recording.
  bool silenceEverLights = false;
  for (int16_t ripple = 0; ripple <= eyegeom::EAR_ARC_COUNT; ++ripple) {
    for (int16_t i = 0; i < eyegeom::EAR_ARC_COUNT; ++i) {
      if (eyegeom::earArcLit(i, ripple, 0.0f)) silenceEverLights = true;
    }
  }
  expectTrue("silence still moves the ears", silenceEverLights);

  // The rest beat: at ripple == EAR_ARC_COUNT nothing is lit by the ripple alone.
  bool restBeatIsEmpty = true;
  for (int16_t i = 0; i < eyegeom::EAR_ARC_COUNT; ++i) {
    if (eyegeom::earArcLit(i, eyegeom::EAR_ARC_COUNT, 0.0f)) restBeatIsEmpty = false;
  }
  expectTrue("the ripple has a rest beat", restBeatIsEmpty);

  // Loud must fill every arc regardless of where the ripple is.
  bool loudFillsAll = true;
  for (int16_t i = 0; i < eyegeom::EAR_ARC_COUNT; ++i) {
    if (!eyegeom::earArcLit(i, eyegeom::EAR_ARC_COUNT, 1.0f)) loudFillsAll = false;
  }
  expectTrue("full volume lights every arc", loudFillsAll);

  // And it must fill from the inside out, not in some other order.
  expectTrue("quiet speech lights only the inner arc",
             eyegeom::earArcLit(0, eyegeom::EAR_ARC_COUNT, 0.30f) &&
                 !eyegeom::earArcLit(2, eyegeom::EAR_ARC_COUNT, 0.30f));
}

static void upstreamParity() {
  // intellar's wakeup() maps height -> radius with map(h, 2, 40, 1, 10) and then
  // clamps to h/2. Spot-check the clamp actually dominates at small heights,
  // which is the whole reason a closing eye flattens.
  expectEqInt("radius at h=2 clamped to 1", eyegeom::radiusForHeight(2), 1);
  expectEqInt("radius at h=4 clamped to h/2", eyegeom::radiusForHeight(4), 1);
  expectEqInt("radius at h=40 is the full 10", eyegeom::radiusForHeight(40), 10);

  // safeRadius must survive a radius larger than the box it is applied to.
  expectEqInt("safeRadius shrinks to fit height", eyegeom::safeRadius(10, 40, 6), 2);
  expectEqInt("safeRadius never goes negative", eyegeom::safeRadius(10, 2, 2), 0);

  // mapRange must not divide by zero on a degenerate input range.
  expectEqInt("mapRange handles an empty input range",
              eyegeom::mapRange(5, 3, 3, 7, 99), 7);
}

// --------------------------------------------------------------------------- //
// Optional ASCII render
// --------------------------------------------------------------------------- //

/** Software drawRBox, only accurate enough to eyeball the shape. */
void fillBox(char *fb, const Box &b) {
  for (int16_t y = b.y; y < b.y + b.h; ++y) {
    for (int16_t x = b.x; x < b.x + b.w; ++x) {
      if (b.rounded) {
        // Knock out the four corners outside the radius.
        const int16_t dx = (x < b.x + b.r) ? (b.x + b.r - x)
                         : (x > b.x + b.w - 1 - b.r) ? (x - (b.x + b.w - 1 - b.r))
                                                     : 0;
        const int16_t dy = (y < b.y + b.r) ? (b.y + b.r - y)
                         : (y > b.y + b.h - 1 - b.r) ? (y - (b.y + b.h - 1 - b.r))
                                                     : 0;
        if (dx * dx + dy * dy > b.r * b.r) continue;
      }
      if (x < 0 || y < 0 || x >= eyegeom::PANEL_WIDTH ||
          y >= eyegeom::PANEL_HEIGHT) {
        continue;
      }
      fb[y * eyegeom::PANEL_WIDTH + x] = '#';
    }
  }
}

// --------------------------------------------------------------------------- //
// Minimal software renderer for the listening face
//
// Mirrors what src/animations.cpp asks U8g2 to draw. Approximate — it exists so the
// composition can be judged before flashing, not to be pixel-exact with U8g2.
// --------------------------------------------------------------------------- //

static void plot(char *fb, int x, int y) {
  if (x < 0 || y < 0 || x >= eyegeom::PANEL_WIDTH || y >= eyegeom::PANEL_HEIGHT) return;
  fb[y * eyegeom::PANEL_WIDTH + x] = '#';
}

static void drawLineAscii(char *fb, int x0, int y0, int x1, int y1) {
  const int dx = x1 - x0 < 0 ? x0 - x1 : x1 - x0;
  const int dy = y1 - y0 < 0 ? y0 - y1 : y1 - y0;
  const int sx = x0 < x1 ? 1 : -1;
  const int sy = y0 < y1 ? 1 : -1;
  int err = dx - dy;
  while (true) {
    plot(fb, x0, y0);
    if (x0 == x1 && y0 == y1) break;
    const int e2 = 2 * err;
    if (e2 > -dy) { err -= dy; x0 += sx; }
    if (e2 < dx) { err += dx; y0 += sy; }
  }
}

/** Outline of a circle, keeping only the half on one side of `cx`. */
static void drawHalfCircleAscii(char *fb, int cx, int cy, int r, bool keepRight) {
  for (int a = 0; a <= 360; ++a) {
    const double rad = a * 3.14159265358979 / 180.0;
    const int x = cx + static_cast<int>(r * cos(rad) + (cos(rad) < 0 ? -0.5 : 0.5));
    const int y = cy + static_cast<int>(r * sin(rad) + (sin(rad) < 0 ? -0.5 : 0.5));
    if (keepRight ? (x >= cx) : (x <= cx)) plot(fb, x, y);
  }
}

static void drawHalfDiscAscii(char *fb, int cx, int cy, int r, bool keepRight) {
  for (int y = cy - r; y <= cy + r; ++y) {
    for (int x = cx - r; x <= cx + r; ++x) {
      const int dx = x - cx;
      const int dy = y - cy;
      if (dx * dx + dy * dy > r * r) continue;
      if (keepRight ? (x >= cx) : (x <= cx)) plot(fb, x, y);
    }
  }
}

static void drawBrowAscii(char *fb, int cx, int y) {
  const int outer = eyegeom::BROW_HALF_WIDTH;
  const int inner = 5;
  for (int row = 0; row < 2; ++row) {
    const int yy = y + row;
    drawLineAscii(fb, cx - outer, yy + 3, cx - inner, yy);
    drawLineAscii(fb, cx - inner, yy, cx + inner, yy);
    drawLineAscii(fb, cx + inner, yy, cx + outer, yy + 3);
  }
}

static void drawEarAscii(char *fb, int x, bool facingRight, int ripple, float level) {
  drawHalfDiscAscii(fb, x, eyegeom::LISTEN_CENTRE_Y, 3, facingRight);
  for (int16_t i = 0; i < eyegeom::EAR_ARC_COUNT; ++i) {
    if (!eyegeom::earArcLit(i, static_cast<int16_t>(ripple), level)) continue;
    drawHalfCircleAscii(fb, x, eyegeom::LISTEN_CENTRE_Y, eyegeom::EAR_ARC_RADII[i],
                        facingRight);
  }
}

static void printPanel(const char *fb, const char *caption) {
  printf("\n--- %s ---\n", caption);
  // Two rows per line: the panel is 2:1, so this keeps the aspect honest in a
  // terminal where a character cell is taller than it is wide.
  for (int16_t y = 0; y < eyegeom::PANEL_HEIGHT; y += 2) {
    for (int16_t x = 0; x < eyegeom::PANEL_WIDTH; ++x) {
      const bool a = fb[y * eyegeom::PANEL_WIDTH + x] == '#';
      const bool b = (y + 1 < eyegeom::PANEL_HEIGHT) &&
                     fb[(y + 1) * eyegeom::PANEL_WIDTH + x] == '#';
      putchar((a || b) ? '#' : '.');
    }
    putchar('\n');
  }
}

void fillBox(char *fb, const Box &b);

static void renderListening(float level, int ripple, float blink, const char *caption) {
  char fb[eyegeom::PANEL_WIDTH * eyegeom::PANEL_HEIGHT];
  memset(fb, '.', sizeof(fb));

  Box left{};
  Box right{};
  eyegeom::eyesListening(blink, left, right);
  fillBox(fb, left);
  fillBox(fb, right);

  const int brow = eyegeom::browY(level);
  drawBrowAscii(fb, eyegeom::leftCentreX(), brow);
  drawBrowAscii(fb, eyegeom::rightCentreX(), brow);

  drawEarAscii(fb, eyegeom::LEFT_EAR_X, true, ripple, level);
  drawEarAscii(fb, eyegeom::RIGHT_EAR_X, false, ripple, level);

  printPanel(fb, caption);
}

static void renderSequence(const char *what, PoseFn pose, int frames) {
  for (int f = 0; f <= frames; ++f) {
    const float t = static_cast<float>(f) / static_cast<float>(frames);
    Box left{};
    Box right{};
    pose(t, left, right);

    char fb[eyegeom::PANEL_WIDTH * eyegeom::PANEL_HEIGHT];
    memset(fb, '.', sizeof(fb));
    fillBox(fb, left);
    fillBox(fb, right);

    printf("\n--- %s frame %d/%d  t=%.2f  %dx%d r=%d ---\n", what, f, frames, t,
           left.w, left.h, left.r);
    // Two rows per line: the panel is 2:1, so this keeps the aspect honest in a
    // terminal where a character cell is taller than it is wide.
    for (int16_t y = 0; y < eyegeom::PANEL_HEIGHT; y += 2) {
      for (int16_t x = 0; x < eyegeom::PANEL_WIDTH; ++x) {
        const bool a = fb[y * eyegeom::PANEL_WIDTH + x] == '#';
        const bool b = (y + 1 < eyegeom::PANEL_HEIGHT) &&
                       fb[(y + 1) * eyegeom::PANEL_WIDTH + x] == '#';
        putchar((a || b) ? '#' : '.');
      }
      putchar('\n');
    }
  }
}

int main(int argc, char **argv) {
  printf("=== eye_geometry host test ===\n");
  endpoints();
  blinkPose();
  listeningFace();
  upstreamParity();
  // Opening only ever grows; a blink shrinks and recovers, so monotonicity is
  // asserted for one and not the other.
  sweep("opening", eyegeom::eyesOpening, true);
  sweep("blink", eyegeom::eyesBlinking, false);
  sweep("listening blink", eyegeom::eyesListening, false);

  bool wantRender = false;
  for (int i = 1; i < argc; ++i) {
    if (strcmp(argv[i], "--render") == 0) wantRender = true;
  }
  if (wantRender) {
    // ~11 frames for the 420 ms open, ~5 for the 180 ms blink, at 25 fps.
    renderSequence("opening", eyegeom::eyesOpening, 11);
    renderSequence("blink", eyegeom::eyesBlinking, 5);
  }

  bool wantListening = false;
  for (int i = 1; i < argc; ++i) {
    if (strcmp(argv[i], "--listening") == 0) wantListening = true;
  }
  if (wantListening) {
    renderListening(0.0f, 0, -1.0f, "silent, ripple on the inner arc");
    renderListening(0.0f, 1, -1.0f, "silent, ripple on the middle arc");
    renderListening(0.0f, 2, -1.0f, "silent, ripple on the outer arc");
    renderListening(0.0f, 3, -1.0f, "silent, rest beat");
    renderListening(0.35f, 3, -1.0f, "quiet speech");
    renderListening(1.0f, 3, -1.0f, "loud, brows up, ears full");
    renderListening(1.0f, 1, 0.5f, "loud, mid-blink");
  }

  printf("\n%d checks, %d failure%s\n", checks, failures,
         failures == 1 ? "" : "s");
  return failures == 0 ? 0 : 1;
}
