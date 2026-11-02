#pragma once
/**
 * Screen animations: the blinking face the device rests on, and the waveform that
 * shows while it is listening.
 *
 * The eyes are ported from intellar/oled_eye_display — MIT, Copyright (c) 2024
 * Intellar, https://github.com/intellar/oled_eye_display. Licence text is kept at
 * vendor/oled_eye_display/LICENSE alongside a snapshot of the original sketch.
 * src/animations.cpp explains what was taken and what had to be rewritten to fit
 * a non-blocking loop.
 *
 * Two rules both animations follow:
 *
 * 1. **Driven by elapsed time, not frame count.** The render loop runs at
 *    DISPLAY_FPS but a slow I2C transaction or a blocking HTTP call can stretch a
 *    frame. Animating off `monotonicMs()` means a hitch drops frames instead of
 *    slowing the motion down, so the eye always opens in the same wall-clock time.
 *
 * 2. **Never block.** Each draw call renders whatever the current instant looks
 *    like and returns. There is no `delay()` inside an animation, because the
 *    same loop still has to service the WebSocket and fire timers.
 *
 * The waveform reads from a small ring buffer of audio levels. Before the
 * microphone is capturing it synthesises plausible motion, and once real levels
 * arrive via pushAudioLevel() it draws those instead — so the visual is honest
 * about whether it is showing real sound.
 */

#include <Arduino.h>
#include <U8g2lib.h>

namespace animations {

// --- the idle face --------------------------------------------------------- //
//
// The face is a resting state, not a transition. The eyes open from the sleeping
// slit, then stay up and blink at irregular intervals for as long as nobody
// touches the pad. A touch dismisses it and opens the menu.
//
// This is what the device looks like when it has nothing to say, which is most of
// the time. It is also why the panel does not sit on a static clock face burning
// the same pixels in: the blink moves them, and display.cpp still dims and blanks
// on the usual schedule underneath.

/** Show the face, starting with the eyes opening. Called at boot and on wake. */
void startFace();

/** True while the face owns the screen. */
bool faceActive();

/**
 * Draw the current frame into `g`.
 *
 * Returns false when this frame is identical to the last one drawn, which is the
 * common case: between blinks nothing moves. The caller uses that to skip
 * sendBuffer() and leave the panel holding what it already shows — an idle face
 * should not cost a 1 KB I2C transaction 25 times a second.
 */
bool drawFace(U8G2 &g);

/** Put the face away. The touch that opens the menu, or an alarm that outranks it. */
void dismissFace();

// --- the listening face ---------------------------------------------------- //

/**
 * Feed a real audio level, 0..1, from the microphone capture loop.
 *
 * Smoothed internally with a fast attack and slow release, so callers can push raw
 * per-chunk peaks without the face twitching. Call at roughly 30-60 Hz.
 */
void pushAudioLevel(float level);

/**
 * Arm a listening session: clear the level envelope and restart the blink clock.
 *
 * The blink clock matters. It is shared with the idle face, so without a reset the
 * first listening frame can inherit an already-overdue blink and open with the eyes
 * shut — which looks like the device fell asleep exactly when you started talking.
 */
void beginListening();

/** True if pushAudioLevel() has been called recently enough to trust. */
bool hasLiveAudio();

/**
 * Full-screen listening face: the same eyes, squinting, with brows that lift and
 * ears that fill as you speak.
 *
 * `secondsLeft` draws a bare shrinking rule along the bottom edge; pass a negative
 * number to omit it.
 */
void drawListening(U8G2 &g, float secondsLeft = -1.0f);

/** A three-dot "working on it" indicator, for the wait after recording. */
void drawThinking(U8G2 &g, const char *caption);

}  // namespace animations
