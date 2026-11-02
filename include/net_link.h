#pragma once
/**
 * Wi-Fi + backend sync. Everything network-facing lives here.
 *
 * This whole module is additive. Every call is safe to make with the radio down,
 * nothing else in the firmware waits on it, and if you delete it the device
 * still keeps time, runs timers, rings alarms and switches the relay. That is
 * the product requirement, expressed as a dependency direction.
 *
 * Protocol contract: backend/app/events.py and backend/app/schemas.py.
 */

#include <Arduino.h>

namespace netLink {

void begin();

/** Call every loop. Pumps the socket, heartbeats, and drains the local bus. */
void update();

// --- status (for the UI) -------------------------------------------------- //
bool wifiConnected();
bool socketConnected();
/** True once the backend has acknowledged us at least once. */
bool everConnected();
int32_t rssi();
const char *ssid();
const char *ipAddress();
const char *backendHost();
uint16_t backendPort();
/** Milliseconds since the last frame we received from the backend. */
uint32_t sinceLastInboundMs();

// --- control -------------------------------------------------------------- //
void forceReconnect();
/** Pull full state from GET /api/snapshot and adopt it. */
void requestSnapshot();
/** Apply new Wi-Fi credentials: saves to NVS and reconnects. */
void applyWifiCredentials(const char *ssid, const char *password);

// --- voice ---------------------------------------------------------------- //

/** What POST /api/voice/transcribe gave back. Strings are always terminated. */
struct VoiceResult {
  bool ok;
  int httpStatus;         // 0 when the request never got off the device
  char transcript[96];    // what Whisper heard
  char reply[512];        // what the backend wants said back
  char intent[24];        // e.g. "set_timer", or "" when it went to the LLM
  char action[64];        // human-readable description of what was done
  uint32_t elapsedMs;     // round trip as measured here, not by the server
};

/**
 * Upload a recorded clip and run it through the backend's voice pipeline.
 *
 * **This blocks**, for as long as Whisper plus the intent handler takes — measured
 * at 430-1850 ms. It is the second blocking call in the firmware, after the
 * snapshot GET, and it is blocking for the same reason: the alternative is an
 * async state machine around HTTPClient for a request the user is actively waiting
 * on. Draw the "thinking" frame and push it to the panel *before* calling this,
 * because nothing will redraw until it returns.
 *
 * `body` must be a complete multipart/form-data payload, which is what
 * mic::requestBody() hands back.
 */
VoiceResult postVoice(const uint8_t *body, size_t length, const char *boundary);

// --- TTS (text-to-speech) ------------------------------------------------- //

/** What POST /api/voice/speak gave back. */
struct SpeechResult {
  bool ok;
  int16_t *pcm;        // PSRAM buffer, caller must free with free()
  size_t sampleCount;  // number of 16-bit samples
  uint32_t elapsedMs;
};

/**
 * Download synthesised speech from the backend and return it as raw PCM.
 *
 * **This blocks** — typically 1–3 seconds for a short sentence. Call it only
 * after the notice is already on screen, same pattern as postVoice().
 *
 * The returned pcm buffer is allocated with ps_malloc and must be freed by the
 * caller once playback is complete (i.e. when chime::isPlaying() goes false).
 */
SpeechResult fetchSpeech(const char *text);

}  // namespace netLink
