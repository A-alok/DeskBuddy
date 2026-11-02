#pragma once
/**
 * Push-to-talk: the sequence from a gesture to an action taken.
 *
 *   Arming -> Listening -> Sending -> (notice)
 *
 * Arming exists for one reason: the confirm chime plays through a speaker roughly
 * 4 cm from the microphone. Recording through it puts a 1.4 kHz beep at the front
 * of every clip, which Whisper occasionally transcribes as a word. So the capture
 * waits for the chime to finish — about 35 ms, invisible to the user, and it keeps
 * the audible cue.
 *
 * This is a mode rather than a screen. It is not in the tap-through cycle, because
 * a listening state you can navigate away from mid-recording is a state that needs
 * answers to questions nobody wants to ask.
 */

#include <Arduino.h>
#include <U8g2lib.h>

namespace voice {

enum class State : uint8_t {
  Idle,
  Arming,     // waiting for the confirm chime to stop so it is not recorded
  Listening,  // capturing, waveform on screen
  Sending,    // uploading and waiting on the backend; the loop is blocked here
};

void begin();

/**
 * Start listening. Returns false when voice is unavailable — no microphone, no
 * Wi-Fi, or a capture already running — so the caller can give different feedback
 * instead of appearing to do nothing.
 */
bool start();

/** Abandon the recording. Any touch during Listening does this. */
void cancel();

/** Synthesize and play speech through the speaker via TTS. If isQuiz is true, auto-listens for answer after speaking. */
void speak(const char *text, bool isQuiz = false);

/** Call every loop. Drives capture and performs the upload when it completes. */
void update();

State state();

/** True while voice owns the display. */
bool active();

/** Draw the current phase. Only meaningful while active(). */
void draw(U8G2 &g);

/** Why the last start() was refused, for the message shown to the user. */
const char *lastError();

}  // namespace voice
