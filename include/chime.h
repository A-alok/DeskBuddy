#pragma once
/**
 * Tone generator on the MAX98357 (I2S peripheral 1, transmit).
 *
 * Non-blocking by construction: update() tops up the I2S DMA buffer with
 * whatever it will accept right now and returns. A blocking beep would freeze
 * the display and stall the WebSocket for the length of the sound, which is
 * exactly when you want the UI to be responsive.
 *
 * Notes are shaped with a short attack and decay. Without it, starting and
 * stopping a square wave at full amplitude produces an audible click through a
 * class-D amp.
 */

#include <Arduino.h>

namespace chime {

void begin();

/** Call every loop. Cheap when nothing is playing. */
void update();

void playConfirm();
void playTimerDone();
void playPomodoroFocus();
void playPomodoroBreak();
void playError();

/** Repeats until stop() is called. Used while an alarm is unacknowledged. */
void playAlarmLoop();

void stop();
bool isPlaying();

/**
 * Stream a block of 16-bit mono PCM at AUDIO_SAMPLE_RATE through the speaker.
 *
 * The buffer must live until isPlaying() returns false — it is read chunk by
 * chunk inside update(), not copied. For TTS this means PSRAM, same as the
 * mic capture buffer.
 *
 * Mono is duplicated to stereo internally (the I2S bus is always stereo).
 * Volume scaling from setVolume() applies.
 */
void playPcm(const int16_t *mono, size_t sampleCount);

/** 0..10. Persisted in NVS. */
void setVolume(uint8_t level);
uint8_t volume();

}  // namespace chime
