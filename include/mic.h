#pragma once
/**
 * INMP441 capture on I2S peripheral 0.
 *
 * Records a fixed-length clip into PSRAM and hands back a buffer that is already
 * a complete multipart/form-data body — WAV header and all — so the upload is one
 * write with no copies. At 16 kHz mono that is 160 KB for five seconds, which is
 * why it lives in PSRAM and not the 320 KB of internal RAM.
 *
 * Two things this module deliberately does not do:
 *
 *  - **Block.** update() drains whatever the DMA has ready and returns. The same
 *    loop still has to run timer deadlines and service the WebSocket, and a
 *    recording is five seconds long. Reading with a zero timeout means a slow
 *    frame drops audio rather than stalling the device.
 *
 *  - **Touch the network.** It produces a buffer; something else posts it. Keeps
 *    the dependency direction the rest of the firmware follows, and means capture
 *    is testable with the radio down.
 *
 * The chime uses I2S peripheral 1 for output, so the two never contend.
 */

#include <Arduino.h>

namespace mic {

/**
 * Install the I2S RX driver and allocate the PSRAM buffer.
 *
 * Returns false when there is no PSRAM or the driver refuses. That is not fatal:
 * voice simply stays unavailable and every other feature carries on, the same way
 * a missing OLED is handled.
 */
bool begin();

/** False when begin() failed. Check before offering voice in the UI. */
bool ready();

/** Start a fresh recording. False if not ready, or one is already running. */
bool startCapture();

/** Drain the DMA into the buffer. Call every loop while capturing(). */
void update();

/** True while audio is still being collected. */
bool capturing();

/** Seconds left in the current recording, 0 when not capturing. */
float secondsRemaining();

/** Throw away the recording in progress. */
void cancel();

// --- the finished clip ----------------------------------------------------- //

/**
 * A complete multipart/form-data request body for POST /api/voice/transcribe,
 * valid once capturing() goes false. Returns nullptr if nothing was recorded.
 */
const uint8_t *requestBody();

/** Length of requestBody() in bytes. */
size_t requestBodyLength();

/** The multipart boundary, for the Content-Type header. */
const char *boundary();

/** Recorded audio length in bytes of PCM, excluding all headers. */
size_t pcmBytes();

/** Peak absolute sample of the last recording, after gain. 0..32767. */
uint16_t lastPeak();

/** RMS of the last recording, after gain. The honest "did it hear anything". */
uint16_t lastRms();

}  // namespace mic
