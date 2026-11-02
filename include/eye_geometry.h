#pragma once
/**
 * Geometry for the wake eyes, ported from intellar/oled_eye_display
 * (MIT, Copyright (c) 2024 Intellar — vendor/oled_eye_display/LICENSE).
 *
 * Split out from animations.cpp on purpose: nothing in here touches Arduino or
 * U8g2, so `test/host/test_eye_geometry.cpp` compiles it with g++ and checks
 * every frame of the animation on a PC. The failures worth catching are all
 * arithmetic — a box that runs off the panel, or a corner radius that breaks
 * U8g2's drawRBox contract and silently renders garbage — and finding those by
 * flashing and squinting at a 1.3" panel is a bad trade.
 *
 * animations.cpp holds the part that genuinely needs hardware: turning these
 * numbers into pixels.
 */

#include <stdint.h>

namespace eyegeom {

// --- panel ----------------------------------------------------------------- //
constexpr int16_t PANEL_WIDTH = 128;
constexpr int16_t PANEL_HEIGHT = 64;

// --- intellar's reference dimensions, unchanged ---------------------------- //
// 40 + 10 + 40 = 90 px wide, centred on a 128 px panel with 19 px either side.
constexpr int16_t REF_EYE_HEIGHT = 40;
constexpr int16_t REF_EYE_WIDTH = 40;
constexpr int16_t REF_SPACE_BETWEEN_EYE = 10;
constexpr int16_t REF_CORNER_RADIUS = 10;
/** The height a sleeping eye sits at — a 2 px bar, their sleep() pose. */
constexpr int16_t SLEEP_EYE_HEIGHT = 2;

// --- blink extremes, also intellar's ---------------------------------------- //
// Their blink() runs three steps of `height -= 12` and `width += 3`, so the lid
// bottoms out at 40 - 36 = 4 px tall and 40 + 9 = 49 px wide. The widening is the
// part that makes it read as a lid rather than a shutter: a real eyelid squeezes
// the eye outward as it closes.
constexpr int16_t BLINK_MIN_HEIGHT = 4;
constexpr int16_t BLINK_MAX_WIDTH = 49;

// --- the listening face ----------------------------------------------------- //
//
// Same eyes, same x centres, so the device visibly stays the same character when
// it starts listening. Three things change:
//
//  - The eyes squint to 30 px and sit 4 px lower, which frees the top of the panel
//    for brows. Squinted-plus-brows is what reads as "concentrating"; wide-open
//    eyes with brows just look surprised.
//  - Brows appear above them, and lift with how loud the room is.
//  - Ears appear in the margins either side of the eyes.
//
// The margins are what make this fit at all. Eyes 40 px wide at these centres
// occupy x=19..109, leaving 19 px on the left and 18 on the right — just enough
// for a 16 px ear with clearance. That is asserted in the host test rather than
// eyeballed, because an ear overlapping an eye is the obvious failure here.
constexpr int16_t LISTEN_EYE_HEIGHT = 30;
constexpr int16_t LISTEN_CENTRE_Y = 36;

/** Concentric arcs per ear, innermost first. */
constexpr int16_t EAR_ARC_COUNT = 3;
constexpr int16_t EAR_ARC_RADII[EAR_ARC_COUNT] = {6, 11, 16};
// Centred on the panel edges, so only the inward-facing half is ever drawn. An ear
// centred inside the panel would need its outer arc clipped, and U8g2 clips by
// discarding whole pixels rather than the shape, which looks like corruption.
constexpr int16_t LEFT_EAR_X = 0;
constexpr int16_t RIGHT_EAR_X = PANEL_WIDTH - 1;

/** Baseline for the brows, before any lift from audio level. */
constexpr int16_t BROW_BASE_Y = 13;
/** How far the brows rise at full volume. */
constexpr int16_t BROW_MAX_LIFT = 3;
/** Half-width of a brow. Kept inside the eye width so it reads as one face. */
constexpr int16_t BROW_HALF_WIDTH = 14;

constexpr int16_t centreY() { return PANEL_HEIGHT / 2; }
constexpr int16_t leftCentreX() {
  return PANEL_WIDTH / 2 - REF_EYE_WIDTH / 2 - REF_SPACE_BETWEEN_EYE / 2;
}
constexpr int16_t rightCentreX() {
  return PANEL_WIDTH / 2 + REF_EYE_WIDTH / 2 + REF_SPACE_BETWEEN_EYE / 2;
}

/** A rectangle ready to hand to U8g2, top-left anchored the way it wants. */
struct Box {
  int16_t x;
  int16_t y;
  int16_t w;
  int16_t h;
  int16_t r;
  /** False when the radius collapsed to 0 and this must go to drawBox(). */
  bool rounded;
};

/** Arduino's map(), reimplemented so this header stays host-compilable. */
inline int32_t mapRange(int32_t value, int32_t inMin, int32_t inMax,
                        int32_t outMin, int32_t outMax) {
  if (inMax == inMin) return outMin;
  return (value - inMin) * (outMax - outMin) / (inMax - inMin) + outMin;
}

/**
 * intellar's calculate_safe_radius, kept as-is.
 *
 * U8g2's drawRBox() requires the radius to be strictly less than half the
 * smaller dimension. Violate it and the box renders corrupt rather than being
 * refused, which is why this clamp is load-bearing and not defensive padding.
 */
inline int16_t safeRadius(int16_t r, int16_t w, int16_t h) {
  if (w < 2 * (r + 1)) r = static_cast<int16_t>((w / 2) - 1);
  if (h < 2 * (r + 1)) r = static_cast<int16_t>((h / 2) - 1);
  return r < 0 ? 0 : r;
}

/**
 * Eye height at progress `t` (0 = asleep, 1 = fully open).
 *
 * Linear, matching intellar's `for (h = 2; h <= 40; h += 2)`. Their pacing is
 * what the animation is recognised for; a cubic ease-out made the lid look like
 * it was being pulled open rather than snapping awake.
 */
inline int16_t openHeight(float t) {
  if (t < 0.0f) t = 0.0f;
  if (t > 1.0f) t = 1.0f;
  int16_t h = static_cast<int16_t>(SLEEP_EYE_HEIGHT +
                                   t * (REF_EYE_HEIGHT - SLEEP_EYE_HEIGHT));
  if (h < SLEEP_EYE_HEIGHT) h = SLEEP_EYE_HEIGHT;
  if (h > REF_EYE_HEIGHT) h = REF_EYE_HEIGHT;
  return h;
}

/**
 * Corner radius for a given height, their mapping exactly: a wide-open eye gets
 * the full 10 px round, a closing one flattens toward square. Without this a
 * half-shut eye is a lozenge instead of a lid.
 */
inline int16_t radiusForHeight(int16_t h) {
  int16_t r = static_cast<int16_t>(
      mapRange(h, SLEEP_EYE_HEIGHT, REF_EYE_HEIGHT, 1, REF_CORNER_RADIUS));
  if (r > h / 2) r = static_cast<int16_t>(h / 2);
  return r;
}

/**
 * Blink progress 0..1 -> how far the lid is down, 0..1..0.
 *
 * A symmetric triangle, so the lid comes back up as fast as it went down. Real
 * blinks are slightly faster closing than opening, but at 180 ms over a 40 px eye
 * the asymmetry is under one frame and not worth the arithmetic.
 */
inline float blinkCurve(float p) {
  if (p < 0.0f) p = 0.0f;
  if (p > 1.0f) p = 1.0f;
  const float doubled = 2.0f * p - 1.0f;
  return 1.0f - (doubled < 0.0f ? -doubled : doubled);
}

/** Eye height partway through a blink. Never fully closes — intellar stop at 4. */
inline int16_t blinkHeight(float p) {
  const float v = blinkCurve(p);
  int16_t h = static_cast<int16_t>(
      REF_EYE_HEIGHT - v * (REF_EYE_HEIGHT - BLINK_MIN_HEIGHT));
  if (h < BLINK_MIN_HEIGHT) h = BLINK_MIN_HEIGHT;
  if (h > REF_EYE_HEIGHT) h = REF_EYE_HEIGHT;
  return h;
}

/** Eye width partway through a blink — it bulges outward as the lid comes down. */
inline int16_t blinkWidth(float p) {
  const float v = blinkCurve(p);
  int16_t w = static_cast<int16_t>(
      REF_EYE_WIDTH + v * (BLINK_MAX_WIDTH - REF_EYE_WIDTH));
  if (w < REF_EYE_WIDTH) w = REF_EYE_WIDTH;
  if (w > BLINK_MAX_WIDTH) w = BLINK_MAX_WIDTH;
  return w;
}

/** Centre-anchored eye -> top-left anchored box, with the radius resolved. */
inline Box boxFor(int16_t cx, int16_t cy, int16_t w, int16_t h, int16_t radius) {
  Box box{};
  box.w = w;
  box.h = h;
  box.x = static_cast<int16_t>(cx - w / 2);
  box.y = static_cast<int16_t>(cy - h / 2);
  box.r = safeRadius(radius, w, h);
  // drawRBox with r == 0 is outside U8g2's contract, so the degenerate case has
  // to go to drawBox. intellar call drawRBox regardless; on a slit one pixel row
  // tall that is not worth the risk.
  box.rounded = box.r >= 1;
  return box;
}

/**
 * The pair of eyes at a given size. Both share a height and width, as upstream
 * does, and the centres never move — width grows symmetrically about them.
 */
inline void eyesAtY(int16_t h, int16_t w, int16_t cy, Box &left, Box &right) {
  const int16_t r = radiusForHeight(h);
  left = boxFor(leftCentreX(), cy, w, h, r);
  right = boxFor(rightCentreX(), cy, w, h, r);
}

inline void eyes(int16_t h, int16_t w, Box &left, Box &right) {
  eyesAtY(h, w, centreY(), left, right);
}

/** Opening from the sleeping slit: `t` 0 = shut, 1 = fully open. */
inline void eyesOpening(float t, Box &left, Box &right) {
  eyes(openHeight(t), REF_EYE_WIDTH, left, right);
}

/** Mid-blink: `p` 0 = open, 0.5 = lid at its lowest, 1 = open again. */
inline void eyesBlinking(float p, Box &left, Box &right) {
  eyes(blinkHeight(p), blinkWidth(p), left, right);
}

/**
 * The listening pose. `p` is blink progress, or a negative number for eyes open.
 *
 * Squinted and sitting low, dropping to the same 4 px slit as a normal blink so the
 * two animations share a vocabulary. The width bulge is reused as well, which is
 * what stops a blink at this smaller height from looking like the eyes simply
 * vanishing.
 */
inline void eyesListening(float p, Box &left, Box &right) {
  int16_t h = LISTEN_EYE_HEIGHT;
  int16_t w = REF_EYE_WIDTH;
  if (p >= 0.0f) {
    const float v = blinkCurve(p);
    h = static_cast<int16_t>(LISTEN_EYE_HEIGHT -
                             v * (LISTEN_EYE_HEIGHT - BLINK_MIN_HEIGHT));
    if (h < BLINK_MIN_HEIGHT) h = BLINK_MIN_HEIGHT;
    w = blinkWidth(p);
  }
  eyesAtY(h, w, LISTEN_CENTRE_Y, left, right);
}

/** Brow baseline for a given loudness, 0..1. Louder room, higher brows. */
inline int16_t browY(float level) {
  if (level < 0.0f) level = 0.0f;
  if (level > 1.0f) level = 1.0f;
  return static_cast<int16_t>(BROW_BASE_Y - level * BROW_MAX_LIFT);
}

/**
 * Should ear arc `index` be lit?
 *
 * Two independent reasons, OR'd together, and both are needed:
 *
 *  - `ripple` is a travelling index that walks outward on a timer. It guarantees
 *    the ears are always moving, so a silent room still looks like an active
 *    recording rather than a frozen screen.
 *  - Loudness lights arcs from the inside out, so speaking fills the ears.
 *
 * Without the ripple, silence looks broken. Without the level, the ears ignore the
 * thing they are supposed to be reacting to.
 */
inline bool earArcLit(int16_t index, int16_t ripple, float level) {
  if (index == ripple) return true;
  return level >= static_cast<float>(index + 1) * 0.28f;
}

}  // namespace eyegeom
