#include "chime.h"

#include <Preferences.h>
#include <math.h>

#include "config.h"

#if CHIME_ENABLED
#include <driver/i2s.h>
#endif

namespace chime {

struct Note {
  uint16_t freqHz;  // 0 = rest
  uint16_t ms;
};

static const uint8_t MAX_NOTES = 8;
static Note sequence[MAX_NOTES];
static uint8_t noteCount = 0;
static uint8_t noteIndex = 0;
static bool playing = false;
static bool looping = false;
static uint32_t samplesIntoNote = 0;
static float phase = 0.0f;
static uint8_t volumeLevel = 6;
static bool driverReady = false;

// --- PCM buffer playback (for TTS) ---
static const int16_t *pcmBuffer = nullptr;
static size_t pcmTotalSamples = 0;
static size_t pcmPosition = 0;
static bool pcmPlaying = false;

static Preferences prefs;

static const i2s_port_t PORT = I2S_NUM_1;
static const uint16_t CHUNK_SAMPLES = 128;
static const uint16_t FADE_SAMPLES = AUDIO_SAMPLE_RATE / 200;  // 5 ms

static void enableAmp(bool on) {
#if AMP_HAS_SD_PIN
  // SD_MODE above ~1.4 V enables the amplifier. Pulling it low between sounds
  // shuts the output stage down, which removes the idle hiss you otherwise get
  // through a small speaker.
  digitalWrite(PIN_AMP_SD, on ? HIGH : LOW);
#else
  (void)on;
#endif
}

static uint32_t noteSampleCount(uint8_t index) {
  if (index >= noteCount) return 0;
  return static_cast<uint32_t>(sequence[index].ms) * AUDIO_SAMPLE_RATE / 1000UL;
}

static void startSequence(const Note *notes, uint8_t count, bool loop) {
#if !CHIME_ENABLED
  (void)notes;
  (void)count;
  (void)loop;
  return;
#else
  if (!driverReady || count == 0 || volumeLevel == 0) return;

  noteCount = count > MAX_NOTES ? MAX_NOTES : count;
  for (uint8_t i = 0; i < noteCount; ++i) sequence[i] = notes[i];
  noteIndex = 0;
  samplesIntoNote = 0;
  phase = 0.0f;
  looping = loop;
  playing = true;
  enableAmp(true);
  i2s_zero_dma_buffer(PORT);
#endif
}

void begin() {
  if (prefs.begin("deskmate", true)) {
    volumeLevel = prefs.getUChar("volume", 6);
    prefs.end();
  }
  if (volumeLevel > 10) volumeLevel = 6;

#if AMP_HAS_SD_PIN
  digitalWrite(PIN_AMP_SD, LOW);
  pinMode(PIN_AMP_SD, OUTPUT);
  digitalWrite(PIN_AMP_SD, LOW);
#endif

#if CHIME_ENABLED
  i2s_config_t cfg = {};
  cfg.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX);
  cfg.sample_rate = AUDIO_SAMPLE_RATE;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = 0;
  cfg.dma_buf_count = 6;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;
  cfg.tx_desc_auto_clear = true;
  cfg.fixed_mclk = 0;

  esp_err_t err = i2s_driver_install(PORT, &cfg, 0, nullptr);
  if (err != ESP_OK) {
    Serial.printf("[chime] i2s_driver_install failed: %d\n", err);
    return;
  }

  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = PIN_AMP_BCLK;
  pins.ws_io_num = PIN_AMP_LRC;
  pins.data_out_num = PIN_AMP_DIN;
  pins.data_in_num = I2S_PIN_NO_CHANGE;

  err = i2s_set_pin(PORT, &pins);
  if (err != ESP_OK) {
    Serial.printf("[chime] i2s_set_pin failed: %d\n", err);
    i2s_driver_uninstall(PORT);
    return;
  }

  i2s_zero_dma_buffer(PORT);
  driverReady = true;
  Serial.println("[chime] I2S TX ready");
#endif
}

void update() {
#if CHIME_ENABLED
  if (!driverReady) return;

  // --- PCM buffer playback (TTS audio) ---
  if (pcmPlaying && pcmBuffer) {
    static int16_t buffer[CHUNK_SAMPLES * 2];
    // TTS speech needs more gain than generated chime tones. Chimes sit at
    // ~37% of full scale (12000/32767); TTS audio is normalised conservatively
    // by Edge TTS and then further attenuated by the volume knob. A 3x boost
    // makes speech clearly audible on a 0.5W speaker at 3.3V. Peaks clip
    // harmlessly — the clamping below catches them.
    static constexpr float TTS_BOOST = 3.0f;
    const float gain = (static_cast<float>(volumeLevel) / 10.0f) * TTS_BOOST;

    // Feed as much as the DMA will accept. One chunk per loop is enough for
    // short chime tones but starves a 22050 Hz continuous stream — the DMA
    // drains in ~70 ms while a 10 fps loop only adds 5.8 ms of data per pass.
    // Looping here keeps the DMA full without blocking the main loop: the
    // zero-timeout i2s_write returns immediately when the buffers are full.
    while (pcmPosition < pcmTotalSamples) {
      uint16_t produced = 0;
      while (produced < CHUNK_SAMPLES && pcmPosition + produced < pcmTotalSamples) {
        size_t idx = pcmPosition + produced;
        float sample = static_cast<float>(pcmBuffer[idx]) * gain;
        // Clamp to prevent wrap-around distortion on loud passages.
        if (sample > 32767.0f) sample = 32767.0f;
        else if (sample < -32768.0f) sample = -32768.0f;
        int16_t value = static_cast<int16_t>(sample);
        buffer[produced * 2]     = value;
        buffer[produced * 2 + 1] = value;
        ++produced;
      }

      if (produced == 0) break;

      size_t written = 0;
      i2s_write(PORT, buffer, produced * 2 * sizeof(int16_t), &written, 0);

      // Advance by however many samples actually went into the DMA.
      size_t samplesWritten = written / (2 * sizeof(int16_t));
      pcmPosition += samplesWritten;

      if (samplesWritten < produced) {
        // DMA is full — come back next loop iteration.
        break;
      }
    }

    if (pcmPosition >= pcmTotalSamples) {
      pcmPlaying = false;
      pcmBuffer = nullptr;
      if (!playing) enableAmp(false);
      Serial.println("[chime] TTS playback finished");
    }
    return;  // PCM has priority over chimes while active
  }

  // --- Generated tone playback (chimes) ---
  if (!playing) return;

  static int16_t buffer[CHUNK_SAMPLES * 2];  // interleaved stereo
  const float gain = static_cast<float>(volumeLevel) / 10.0f;

  // One chunk per loop iteration. The DMA buffer holds ~70 ms at this size, so
  // a 10 fps UI loop keeps it comfortably fed without ever blocking on it.
  uint16_t produced = 0;
  while (produced < CHUNK_SAMPLES) {
    if (noteIndex >= noteCount) {
      if (looping) {
        noteIndex = 0;
        samplesIntoNote = 0;
      } else {
        break;
      }
    }

    const Note &note = sequence[noteIndex];
    const uint32_t total = noteSampleCount(noteIndex);
    if (samplesIntoNote >= total) {
      ++noteIndex;
      samplesIntoNote = 0;
      phase = 0.0f;
      continue;
    }

    float sample = 0.0f;
    if (note.freqHz > 0) {
      sample = sinf(phase);
      phase += 2.0f * static_cast<float>(M_PI) * note.freqHz / AUDIO_SAMPLE_RATE;
      if (phase > 2.0f * static_cast<float>(M_PI)) {
        phase -= 2.0f * static_cast<float>(M_PI);
      }

      // Attack / decay envelope to suppress the click at note edges.
      float envelope = 1.0f;
      if (samplesIntoNote < FADE_SAMPLES) {
        envelope = static_cast<float>(samplesIntoNote) / FADE_SAMPLES;
      } else if (total > FADE_SAMPLES && samplesIntoNote > total - FADE_SAMPLES) {
        envelope = static_cast<float>(total - samplesIntoNote) / FADE_SAMPLES;
      }
      sample *= envelope;
    }

    int16_t value = static_cast<int16_t>(sample * gain * 12000.0f);
    buffer[produced * 2] = value;
    buffer[produced * 2 + 1] = value;
    ++produced;
    ++samplesIntoNote;
  }

  if (produced > 0) {
    size_t written = 0;
    // Zero timeout: take whatever space exists and come back next loop. Never
    // wait on the audio path.
    i2s_write(PORT, buffer, produced * 2 * sizeof(int16_t), &written, 0);
  }

  if (noteIndex >= noteCount && !looping) {
    playing = false;
    if (!pcmPlaying) enableAmp(false);
  }
#endif
}

void stop() {
  playing = false;
  looping = false;
  noteIndex = 0;
  noteCount = 0;
  pcmPlaying = false;
  pcmBuffer = nullptr;
  pcmPosition = 0;
  enableAmp(false);
#if CHIME_ENABLED
  if (driverReady) i2s_zero_dma_buffer(PORT);
#endif
}

bool isPlaying() { return playing || pcmPlaying; }

void playPcm(const int16_t *mono, size_t sampleCount) {
#if !CHIME_ENABLED
  (void)mono;
  (void)sampleCount;
  return;
#else
  if (!driverReady || mono == nullptr || sampleCount == 0 || volumeLevel == 0) return;

  // Stop any chime that is currently playing so they don't interleave.
  playing = false;
  looping = false;

  pcmBuffer = mono;
  pcmTotalSamples = sampleCount;
  pcmPosition = 0;
  pcmPlaying = true;
  enableAmp(true);
  i2s_zero_dma_buffer(PORT);

  float durationSec = static_cast<float>(sampleCount) / AUDIO_SAMPLE_RATE;
  Serial.printf("[chime] TTS playback started: %u samples (%.1f s)\n",
                static_cast<unsigned>(sampleCount), durationSec);
#endif
}

void setVolume(uint8_t level) {
  volumeLevel = level > 10 ? 10 : level;
  if (prefs.begin("deskmate", false)) {
    prefs.putUChar("volume", volumeLevel);
    prefs.end();
  }
}

uint8_t volume() { return volumeLevel; }

// --------------------------------------------------------------------------- //
// Sound designs
// --------------------------------------------------------------------------- //

void playConfirm() {
  static const Note notes[] = {{1400, 35}};
  startSequence(notes, 1, false);
}

void playTimerDone() {
  static const Note notes[] = {{880, 160}, {0, 90},  {880, 160},
                               {0, 90},    {1170, 320}};
  startSequence(notes, 5, false);
}

void playPomodoroFocus() {
  static const Note notes[] = {{660, 130}, {0, 40}, {990, 240}};
  startSequence(notes, 3, false);
}

void playPomodoroBreak() {
  static const Note notes[] = {{990, 130}, {0, 40}, {660, 240}};
  startSequence(notes, 3, false);
}

void playError() {
  static const Note notes[] = {{300, 200}, {0, 60}, {240, 260}};
  startSequence(notes, 3, false);
}

void playAlarmLoop() {
  static const Note notes[] = {{1046, 200}, {0, 120}, {1318, 200}, {0, 480}};
  startSequence(notes, 4, true);
}

}  // namespace chime
