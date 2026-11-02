#include "mic.h"

#include <driver/i2s.h>
#include <math.h>

#include "animations.h"
#include "clock_time.h"
#include "config.h"

namespace mic {

static const i2s_port_t PORT = I2S_NUM_0;

// DMA sizing. 6 buffers of 256 frames is 1536 frames, ~96 ms at 16 kHz. The UI
// redraws at ANIMATION_FPS while listening and a full-frame I2C write costs
// ~23 ms, so this leaves nearly 4x headroom before a slow frame could overrun.
static const int DMA_BUFFERS = 6;
static const int DMA_FRAMES = 256;

// One drain per update(). Matches a DMA buffer, so a single i2s_read normally
// empties exactly what became ready.
static const size_t READ_FRAMES = 256;

// --------------------------------------------------------------------------- //
// Buffer layout
//
// One PSRAM allocation holds the entire HTTP request body, laid out so the audio
// lands directly where it will be sent from:
//
//   [multipart preamble][44-byte WAV header][PCM ...][multipart epilogue]
//
// The preamble is a fixed length, so the DMA can write PCM straight to its final
// address. The alternative — capture into one buffer, then build a request body
// around it — would mean a second 160 KB allocation and a 160 KB memcpy for no
// benefit.
// --------------------------------------------------------------------------- //

static const char BOUNDARY[] = "DeskMateVoiceBoundary8f2c1d";

static const char PREAMBLE_FMT[] =
    "--%s\r\n"
    "Content-Disposition: form-data; name=\"file\"; filename=\"speech.wav\"\r\n"
    "Content-Type: audio/wav\r\n"
    "\r\n";

static const size_t WAV_HEADER_BYTES = 44;
static const size_t MAX_PCM_BYTES =
    static_cast<size_t>(MIC_SAMPLE_RATE * VOICE_RECORD_SECONDS) * sizeof(int16_t);

static uint8_t *body = nullptr;
static size_t preambleBytes = 0;
static size_t epilogueBytes = 0;
static size_t capacityBytes = 0;

static size_t pcmWritten = 0;
static bool running = false;
static bool driverReady = false;
static uint64_t captureStartMs = 0;

// Silence auto-stop state.
//
// The detector works on a SMOOTHED chunk RMS, not a raw per-chunk peak. A raw
// peak is spiky: the INMP441's noise floor throws occasional samples well above
// any fixed threshold, so a peak-based test keeps re-arming on noise and never
// sees silence — which is exactly why the clip ran the full ceiling.
//
// It is also ADAPTIVE. During the first part of the recording, before the user
// speaks, it measures the room's quiet level (noiseFloor). "Voice" is then any
// chunk whose smoothed level is a clear multiple of that floor. This makes it
// work in a quiet room and a noisy one without hand-tuning a fixed threshold.
static bool speechStarted = false;
static uint64_t lastVoiceMs = 0;

// Start-up discard. The INMP441 outputs a large settling swing for ~80-100 ms
// after its clock starts, and the DC blocker needs a moment to lock on. Measured
// on a real clip: the first 250 ms read rms 17270 (clipping) against ~2800 for
// the actual speech that followed. That burst was being recorded AND counted as
// "speech started", so the clip ended ~1.2 s later on the silence timer, mid-
// sentence. Samples before warmupUntilMs only train the DC blocker.
static uint64_t warmupUntilMs = 0;
static bool dcSeeded = false;
// Speech must stay above the threshold this long before it counts as started,
// so a single click or the chime tail cannot start the silence countdown.
static uint64_t voicedRunStartMs = 0;
static float smoothedLevel = 0.0f;   // low-pass of per-chunk RMS, in 16-bit counts
static float noiseFloor = 0.0f;      // learned quiet baseline, in 16-bit counts
static bool floorLearned = false;

// DC blocker state. The INMP441 has a standing offset of a few hundred counts;
// left in, it biases the level meter and wastes headroom. A one-pole high pass at
// a few Hz removes it without touching speech.
static float dcEstimate = 0.0f;

// 64-bit deliberately. A 16-bit sample squares to ~1.07e9, and 80,000 of those
// sum to 8.6e13 — four orders of magnitude past what a uint32 holds. Scaling each
// term down to fit 32 bits would work but throws away precision for no reason.
static uint64_t sumSquares = 0;
static uint32_t sumSquaresCount = 0;
static uint16_t peakValue = 0;
static uint16_t rmsValue = 0;

// Built once in begin(). Copied in, not printed in, so nothing writes a stray NUL
// past the end of the body.
static char epilogue[64];

// --------------------------------------------------------------------------- //
// WAV header
// --------------------------------------------------------------------------- //

static void putLe32(uint8_t *p, uint32_t value) {
  p[0] = static_cast<uint8_t>(value & 0xFF);
  p[1] = static_cast<uint8_t>((value >> 8) & 0xFF);
  p[2] = static_cast<uint8_t>((value >> 16) & 0xFF);
  p[3] = static_cast<uint8_t>((value >> 24) & 0xFF);
}

static void putLe16(uint8_t *p, uint16_t value) {
  p[0] = static_cast<uint8_t>(value & 0xFF);
  p[1] = static_cast<uint8_t>((value >> 8) & 0xFF);
}

/**
 * Canonical 44-byte PCM WAV header.
 *
 * Written after the recording ends, because two of its fields are byte counts
 * that are not known until then. Getting those wrong is the classic way to make a
 * file that plays locally but which a stricter decoder rejects.
 */
static void writeWavHeader(uint8_t *p, size_t dataBytes) {
  const uint16_t channels = 1;
  const uint16_t bitsPerSample = 16;
  const uint32_t byteRate =
      MIC_SAMPLE_RATE * channels * (bitsPerSample / 8);

  memcpy(p + 0, "RIFF", 4);
  putLe32(p + 4, static_cast<uint32_t>(36 + dataBytes));  // whole file minus 8
  memcpy(p + 8, "WAVE", 4);

  memcpy(p + 12, "fmt ", 4);
  putLe32(p + 16, 16);  // PCM fmt chunk size
  putLe16(p + 20, 1);   // format 1 = uncompressed PCM
  putLe16(p + 22, channels);
  putLe32(p + 24, MIC_SAMPLE_RATE);
  putLe32(p + 28, byteRate);
  putLe16(p + 32, static_cast<uint16_t>(channels * bitsPerSample / 8));  // block align
  putLe16(p + 34, bitsPerSample);

  memcpy(p + 36, "data", 4);
  putLe32(p + 40, static_cast<uint32_t>(dataBytes));
}

// --------------------------------------------------------------------------- //
// Lifecycle
// --------------------------------------------------------------------------- //

bool begin() {
  char preamble[192];
  const int written = snprintf(preamble, sizeof(preamble), PREAMBLE_FMT, BOUNDARY);
  if (written <= 0 || static_cast<size_t>(written) >= sizeof(preamble)) {
    Serial.println("[mic] preamble did not fit — refusing to start");
    return false;
  }
  preambleBytes = static_cast<size_t>(written);

  const int epiWritten =
      snprintf(epilogue, sizeof(epilogue), "\r\n--%s--\r\n", BOUNDARY);
  if (epiWritten <= 0 || static_cast<size_t>(epiWritten) >= sizeof(epilogue)) {
    Serial.println("[mic] epilogue did not fit — refusing to start");
    return false;
  }
  epilogueBytes = static_cast<size_t>(epiWritten);

  capacityBytes = preambleBytes + WAV_HEADER_BYTES + MAX_PCM_BYTES + epilogueBytes;

  // PSRAM explicitly, not malloc. 160 KB out of ~320 KB of internal RAM would
  // leave nothing for the TLS buffers and the JSON document this later needs.
  body = static_cast<uint8_t *>(ps_malloc(capacityBytes));
  if (body == nullptr) {
    Serial.printf("[mic] could not allocate %u bytes in PSRAM — voice disabled\n",
                  static_cast<unsigned>(capacityBytes));
    return false;
  }
  memcpy(body, preamble, preambleBytes);
  // The epilogue moves with the end of the audio, so it is written at capture
  // end rather than here.

  i2s_config_t cfg = {};
  cfg.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = MIC_SAMPLE_RATE;
  cfg.bits_per_sample = static_cast<i2s_bits_per_sample_t>(MIC_BITS_PER_SAMPLE);
#if MIC_USE_RIGHT_SLOT
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT;
#else
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
#endif
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = DMA_BUFFERS;
  cfg.dma_buf_len = DMA_FRAMES;
  cfg.use_apll = false;
  cfg.tx_desc_auto_clear = false;
  cfg.fixed_mclk = 0;

  esp_err_t err = i2s_driver_install(PORT, &cfg, 0, nullptr);
  if (err != ESP_OK) {
    Serial.printf("[mic] i2s_driver_install failed: %d\n", err);
    free(body);
    body = nullptr;
    return false;
  }

  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = PIN_MIC_BCLK;
  pins.ws_io_num = PIN_MIC_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PIN_MIC_DOUT;

  err = i2s_set_pin(PORT, &pins);
  if (err != ESP_OK) {
    Serial.printf("[mic] i2s_set_pin failed: %d\n", err);
    i2s_driver_uninstall(PORT);
    free(body);
    body = nullptr;
    return false;
  }

  // Idle with the peripheral stopped. The INMP441 draws its full current whenever
  // the bit clock is running, and this device is on a desk doing nothing most of
  // the time.
  i2s_stop(PORT);

  driverReady = true;
  Serial.printf("[mic] I2S RX ready on GPIO %d/%d/%d, %d Hz, %s slot, %u KB in PSRAM\n",
                PIN_MIC_BCLK, PIN_MIC_WS, PIN_MIC_DOUT, MIC_SAMPLE_RATE,
                MIC_USE_RIGHT_SLOT ? "right" : "left",
                static_cast<unsigned>(capacityBytes / 1024));
  return true;
}

bool ready() { return driverReady && body != nullptr; }

bool startCapture() {
  if (!ready() || running) return false;

  pcmWritten = 0;
  dcEstimate = 0.0f;
  sumSquares = 0;
  sumSquaresCount = 0;
  peakValue = 0;
  rmsValue = 0;
  speechStarted = false;
  lastVoiceMs = 0;
  dcSeeded = false;
  voicedRunStartMs = 0;
  smoothedLevel = 0.0f;
  noiseFloor = 0.0f;
  floorLearned = false;
  // The animation session is armed by voice::start(), not here — this module only
  // feeds levels, it does not own when the face changes.

  i2s_start(PORT);
  // Discard whatever the DMA had from last time; those frames predate this
  // recording and would land at the front of the clip as a click.
  i2s_zero_dma_buffer(PORT);

  running = true;
  captureStartMs = clocktime::monotonicMs();
  warmupUntilMs = captureStartMs + MIC_WARMUP_MS;
  return true;
}

void cancel() {
  if (!running) return;
  running = false;
  pcmWritten = 0;
  if (driverReady) i2s_stop(PORT);
}

bool capturing() { return running; }

float secondsRemaining() {
  if (!running) return 0.0f;
  const uint64_t elapsed = clocktime::monotonicMs() - captureStartMs;
  const float total = VOICE_RECORD_SECONDS;
  const float left = total - static_cast<float>(elapsed) / 1000.0f;
  return left < 0.0f ? 0.0f : left;
}

// --------------------------------------------------------------------------- //
// Capture
// --------------------------------------------------------------------------- //

static void finish() {
  running = false;
  i2s_stop(PORT);

  uint8_t *wav = body + preambleBytes;
  writeWavHeader(wav, pcmWritten);
  // memcpy, not snprintf: snprintf would plant a NUL one byte past the epilogue,
  // and at a full-length recording that byte is one past the allocation.
  memcpy(wav + WAV_HEADER_BYTES + pcmWritten, epilogue, epilogueBytes);

  if (sumSquaresCount > 0) {
    rmsValue = static_cast<uint16_t>(sqrtf(
        static_cast<float>(sumSquares) / static_cast<float>(sumSquaresCount)));
  }

  Serial.printf("[mic] captured %u bytes (%.2fs), peak %u, rms %u\n",
                static_cast<unsigned>(pcmWritten),
                static_cast<float>(pcmWritten) / 2.0f / MIC_SAMPLE_RATE, peakValue,
                rmsValue);
  if (rmsValue < 200) {
    // Near-silence is almost always the slot quirk, not a quiet room. Say so
    // here rather than letting it surface as an empty transcript.
    Serial.printf("[mic] that is near silence — try flipping MIC_USE_RIGHT_SLOT "
                  "(currently %d) in include/config.h\n",
                  MIC_USE_RIGHT_SLOT);
  }
}

void update() {
  if (!running) return;

  // Deadline first: the clip length has to be wall-clock accurate even if the
  // DMA under-delivers, or a 5-second bar would finish next to a 4-second clip.
  const bool expired =
      clocktime::monotonicMs() - captureStartMs >=
      static_cast<uint64_t>(VOICE_RECORD_SECONDS * 1000.0f);

  static int32_t raw[READ_FRAMES];
  size_t bytesRead = 0;
  // Zero timeout: take what is ready and come back. Never wait on the mic.
  const esp_err_t err = i2s_read(PORT, raw, sizeof(raw), &bytesRead, 0);

  if (err == ESP_OK && bytesRead > 0 && clocktime::monotonicMs() < warmupUntilMs) {
    // Warm-up: do not record, only lock the DC blocker onto the mic's offset.
    // Seed it from the first sample, then track fast, so recording starts with
    // the offset already removed instead of drifting out over a second.
    const size_t frames = bytesRead / sizeof(int32_t);
    for (size_t i = 0; i < frames; ++i) {
      const float s = static_cast<float>(raw[i] >> MIC_GAIN_SHIFT);
      if (!dcSeeded) {
        dcEstimate = s;
        dcSeeded = true;
      } else {
        dcEstimate = dcEstimate * 0.98f + s * 0.02f;
      }
    }
  } else if (err == ESP_OK && bytesRead > 0) {
    const size_t frames = bytesRead / sizeof(int32_t);
    int16_t *out = reinterpret_cast<int16_t *>(body + preambleBytes +
                                              WAV_HEADER_BYTES + pcmWritten);
    const size_t roomFrames = (MAX_PCM_BYTES - pcmWritten) / sizeof(int16_t);
    const size_t take = frames < roomFrames ? frames : roomFrames;

    uint32_t chunkPeak = 0;
    uint64_t chunkSumSq = 0;  // per-chunk, for this chunk's RMS
    for (size_t i = 0; i < take; ++i) {
      // Left-justified 24-bit in a 32-bit slot. The shift both aligns and
      // applies gain; see MIC_GAIN_SHIFT for why it is not simply 16.
      int32_t sample = raw[i] >> MIC_GAIN_SHIFT;

      // One-pole DC blocker. 0.999 puts the corner near 2.5 Hz at 16 kHz, well
      // below anything in speech.
      dcEstimate = dcEstimate * 0.999f + static_cast<float>(sample) * 0.001f;
      sample -= static_cast<int32_t>(dcEstimate);

      // Clamp, never wrap. A wrapped sample flips sign and reads as a click loud
      // enough to derail the transcript.
      if (sample > 32767) sample = 32767;
      if (sample < -32768) sample = -32768;

      out[i] = static_cast<int16_t>(sample);

      const uint32_t magnitude =
          static_cast<uint32_t>(sample < 0 ? -sample : sample);
      if (magnitude > chunkPeak) chunkPeak = magnitude;
      const uint64_t sq = static_cast<uint64_t>(magnitude) * magnitude;
      sumSquares += sq;
      chunkSumSq += sq;
      ++sumSquaresCount;
    }

    pcmWritten += take * sizeof(int16_t);
    if (chunkPeak > peakValue) peakValue = static_cast<uint16_t>(chunkPeak);

    if (take > 0) {
      // Per-chunk RMS, in raw 16-bit counts. RMS tracks loudness far more stably
      // than peak — a single noise spike barely moves it.
      const float chunkRms = sqrtf(static_cast<float>(chunkSumSq) / static_cast<float>(take));

      // Smooth it so one chunk cannot flip the decision. Fast attack (so speech
      // registers at once), slower release (so a brief gap mid-word does not look
      // like the end).
      const float alpha = (chunkRms > smoothedLevel) ? 0.6f : 0.2f;
      smoothedLevel = smoothedLevel * (1.0f - alpha) + chunkRms * alpha;

      // Feed the waveform (normalised 0..1).
      animations::pushAudioLevel(chunkRms / MIC_LEVEL_FULL_SCALE);

      const uint64_t nowMs = clocktime::monotonicMs();
      const uint64_t sinceStart = nowMs - captureStartMs;

      // Noise floor = a minimum-follower over the whole capture. It drops quickly
      // into every gap between words and creeps up only slowly, so it settles on
      // the room's quiet level even when the user starts talking immediately.
      //
      // The earlier version learned the floor from the first 400 ms with a max-
      // hold. Users talk straight away, so it learned their VOICE as the floor,
      // set a threshold above anything the mic can output, never saw speech, and
      // ended the clip on the onset timeout mid-sentence.
      if (!floorLearned) {
        noiseFloor = smoothedLevel;
        floorLearned = true;
      } else if (smoothedLevel < noiseFloor) {
        noiseFloor = noiseFloor * 0.7f + smoothedLevel * 0.3f;  // fast fall
      } else {
        noiseFloor *= 1.002f;                                   // slow rise
      }
      if (noiseFloor < 60.0f) noiseFloor = 60.0f;

      // Voice = clearly above the floor AND above an absolute minimum, capped so
      // the threshold can always be reached (16-bit audio tops out at 32767).
      float voiceThreshold = noiseFloor * VOICE_FLOOR_MULTIPLE;
      if (voiceThreshold < VOICE_MIN_SPEECH_RMS) voiceThreshold = VOICE_MIN_SPEECH_RMS;
      if (voiceThreshold > 20000.0f) voiceThreshold = 20000.0f;
      if (smoothedLevel >= voiceThreshold) {
        lastVoiceMs = nowMs;
        // Speech only "starts" after staying above the threshold for a short
        // run — a click, a bump on the desk or the chime tail is shorter.
        if (voicedRunStartMs == 0) voicedRunStartMs = nowMs;
        if (nowMs - voicedRunStartMs >= VOICE_ONSET_HOLD_MS) speechStarted = true;
      } else {
        voicedRunStartMs = 0;
      }

#if MIC_LEVEL_DEBUG
      static uint64_t lastLevelPrint = 0;
      if (nowMs - lastLevelPrint >= 200) {
        lastLevelPrint = nowMs;
        const uint32_t quietFor = speechStarted ? static_cast<uint32_t>(nowMs - lastVoiceMs) : 0;
        Serial.printf("[mic] t=%.1fs rms=%.0f smooth=%.0f floor=%.0f thr=%.0f spoke=%d quietFor=%ums\n",
                      static_cast<float>(sinceStart) / 1000.0f, chunkRms, smoothedLevel,
                      noiseFloor, voiceThreshold, speechStarted ? 1 : 0,
                      static_cast<unsigned>(quietFor));
      }
#endif
    }
  }

  // --- stop decision -----------------------------------------------------
  const uint64_t now = clocktime::monotonicMs();
  const uint64_t elapsed = now - captureStartMs;
  bool silenceStop = false;

  if (elapsed >= VOICE_MIN_RECORD_MS) {
    if (speechStarted) {
      // The user spoke, then went quiet for the hang window — natural sentence
      // end. This is the common path.
      if (now - lastVoiceMs >= VOICE_SILENCE_HANG_MS) silenceStop = true;
    } else if (elapsed >= VOICE_SPEECH_ONSET_MS) {
      // Nothing was ever said. A mis-tap or an empty room — do not sit recording
      // silence up to the full ceiling.
      silenceStop = true;
    }
  }

  if (expired || silenceStop || pcmWritten >= MAX_PCM_BYTES) finish();
}

// --------------------------------------------------------------------------- //
// Results
// --------------------------------------------------------------------------- //

const uint8_t *requestBody() {
  if (body == nullptr || pcmWritten == 0) return nullptr;
  return body;
}

size_t requestBodyLength() {
  if (body == nullptr || pcmWritten == 0) return 0;
  return preambleBytes + WAV_HEADER_BYTES + pcmWritten + epilogueBytes;
}

const char *boundary() { return BOUNDARY; }
size_t pcmBytes() { return pcmWritten; }

uint16_t lastPeak() { return peakValue; }
uint16_t lastRms() { return rmsValue; }

}  // namespace mic
