#include "voice.h"

#include "animations.h"
#include "chime.h"
#include "clock_time.h"
#include "config.h"
#include "display.h"
#include "mic.h"
#include "net_link.h"
#include "screens.h"

namespace voice {

static State current = State::Idle;
static char errorText[48] = "";

// Safety net on Arming. If the chime driver ever failed to install, isPlaying()
// stays false and this never fires — but if it got stuck true, a recording that
// never starts is a worse failure than one that captures a beep.
static const uint32_t ARM_TIMEOUT_MS = 400;
static uint64_t armStartMs = 0;

// TTS audio buffer — lives in PSRAM, freed when playback completes.
static uint8_t *ttsWavAlloc = nullptr;  // the original ps_malloc pointer
static bool autoListenPending = false;
static uint64_t listenAfterMs = 0;
static bool inQuizSession = false;

void begin() { current = State::Idle; }

State state() { return current; }
bool active() { return current != State::Idle; }
const char *lastError() { return errorText; }

static void freeTtsBuffer() {
  if (ttsWavAlloc) {
    free(ttsWavAlloc);
    ttsWavAlloc = nullptr;
  }
}

bool start() {
  if (current != State::Idle) return false;

  if (!mic::ready()) {
    strlcpy(errorText, "no microphone", sizeof(errorText));
    return false;
  }
  if (!netLink::wifiConnected()) {
    // Worth refusing up front rather than recording five seconds of audio and
    // then discovering there is nowhere to send it. Speech recognition is the one
    // feature here that genuinely cannot work offline.
    strlcpy(errorText, "needs Wi-Fi", sizeof(errorText));
    return false;
  }

  errorText[0] = '\0';
  freeTtsBuffer();  // clean up any previous TTS buffer
  animations::beginListening();
  current = State::Arming;
  armStartMs = clocktime::monotonicMs();
  display::noteActivity();
  return true;
}

void cancel() {
  if (current == State::Idle) return;
  mic::cancel();
  current = State::Idle;
  inQuizSession = false;
  autoListenPending = false;
  display::noteActivity();
}

void speak(const char *text, bool isQuiz) {
  if (text == nullptr || text[0] == '\0') return;
  freeTtsBuffer();

  // Fetch TTS audio first (this is a BLOCKING HTTP call that takes seconds).
  // We must NOT set autoListenPending until AFTER the fetch completes,
  // otherwise the timing will be wrong and update() will try to start
  // listening before the audio even begins playing.
  const netLink::SpeechResult speech = netLink::fetchSpeech(text);
  if (speech.ok && speech.pcm && speech.sampleCount > 0) {
    ttsWavAlloc = reinterpret_cast<uint8_t *>(speech.pcm) - 44;
    chime::playPcm(speech.pcm, speech.sampleCount);
    Serial.printf("[quiz] TTS playing %u samples (%.1f s), isQuiz=%d\n",
                  static_cast<unsigned>(speech.sampleCount),
                  static_cast<float>(speech.sampleCount) / AUDIO_SAMPLE_RATE,
                  isQuiz ? 1 : 0);
  } else {
    // TTS failed — fallback to confirm chime
    chime::playConfirm();
    Serial.printf("[quiz] TTS failed, played confirm chime, isQuiz=%d\n", isQuiz ? 1 : 0);
  }

  // NOW set the auto-listen state, AFTER playback has started.
  // This ensures listenAfterMs is set relative to the START of playback,
  // not before the blocking HTTP fetch.
  if (isQuiz) {
    inQuizSession = true;
    autoListenPending = true;
    listenAfterMs = clocktime::monotonicMs() + 500;
    Serial.printf("[quiz] auto-listen armed, will check after playback finishes\n");
  } else {
    inQuizSession = false;
    autoListenPending = false;
  }
}

/** Upload, then turn whatever came back into something on the panel + speaker. */
static void sendAndReport() {
  const netLink::VoiceResult result =
      netLink::postVoice(mic::requestBody(), mic::requestBodyLength(), mic::boundary());

  current = State::Idle;

  if (!result.ok) {
    chime::playError();
    screens::showNotice("VOICE FAILED", result.reply, 6000);
    return;
  }

  if (result.transcript[0] == '\0') {
    if (inQuizSession) {
      // In a quiz session, the student may be thinking or reading: keep listening for their answer!
      Serial.println("[quiz] silence during quiz — re-arming listener");
      screens::showNotice("QUIZ IN PROGRESS", "Listening for your answer...", 3000);
      autoListenPending = true;
      listenAfterMs = clocktime::monotonicMs() + 500;
      return;
    }
    // A successful round trip with nothing in it almost always means the mic heard
    // silence. Say that, rather than showing an empty box.
    chime::playError();
    screens::showNotice("HEARD NOTHING", "try speaking closer", 5000);
    return;
  }

  // Route to the appropriate screen based on intent so the user sees the page directly
  if (strncmp(result.intent, "timer.", 6) == 0) {
    screens::dismissNotice();
    screens::show(screens::Screen::Timer);
  } else if (strncmp(result.intent, "pomodoro.", 9) == 0) {
    screens::dismissNotice();
    screens::show(screens::Screen::Pomodoro);
  } else if (strncmp(result.intent, "alarm.", 6) == 0) {
    screens::dismissNotice();
    screens::show(screens::Screen::Alarms);
  } else if (strncmp(result.intent, "stopwatch.", 10) == 0) {
    screens::dismissNotice();
    screens::show(screens::Screen::Stopwatch);
  } else if (strncmp(result.intent, "relay.", 6) == 0) {
    screens::dismissNotice();
    screens::show(screens::Screen::Relay);
  } else {
    // Show transcript and reply notice for general chat or other queries
    screens::showNotice(result.transcript, result.reply, NOTICE_DURATION_MS);
  }

  const bool isQuiz = (strcmp(result.intent, "notes.quiz") == 0);
  Serial.printf("[quiz] intent=%s isQuiz=%d replyLen=%u\n",
                result.intent, isQuiz ? 1 : 0, static_cast<unsigned>(strlen(result.reply)));

  if (result.reply[0] != '\0') {
    speak(result.reply, isQuiz);
  } else {
    chime::playConfirm();
    if (isQuiz) {
      inQuizSession = true;
      autoListenPending = true;
      listenAfterMs = clocktime::monotonicMs() + 500;
    } else {
      inQuizSession = false;
      autoListenPending = false;
    }
  }
}

void update() {
  // Free TTS buffer when playback is complete.
  if (ttsWavAlloc && !chime::isPlaying()) {
    freeTtsBuffer();
  }

  // Auto-listen for next quiz answer once speech finishes and silence settles.
  // The 500ms gap after playback lets the speaker settle before the mic opens,
  // preventing the speaker's output from feeding back into the recording.
  if (autoListenPending) {
    if (chime::isPlaying()) {
      // Audio is still playing — keep pushing the deadline forward.
      listenAfterMs = clocktime::monotonicMs() + 500;
    } else if (clocktime::monotonicMs() >= listenAfterMs) {
      // Playback finished and the 500ms cool-down has passed. Start recording.
      autoListenPending = false;
      Serial.println("[quiz] playback done + 500ms settled — starting mic capture");
      if (!start()) {
        // start() failed (no mic, no WiFi, etc.) — retry after a short delay
        // instead of silently giving up.
        Serial.printf("[quiz] start() failed: %s — retrying in 1s\n", errorText);
        autoListenPending = true;
        listenAfterMs = clocktime::monotonicMs() + 1000;
      }
    }
  }

  switch (current) {
    case State::Idle:
      return;

    case State::Arming: {
      const bool timedOut = clocktime::monotonicMs() - armStartMs >= ARM_TIMEOUT_MS;
      if (chime::isPlaying() && !timedOut) return;
      if (!mic::startCapture()) {
        strlcpy(errorText, "mic busy", sizeof(errorText));
        current = State::Idle;
        chime::playError();
        return;
      }
      current = State::Listening;
      return;
    }

    case State::Listening:
      mic::update();
      if (!mic::capturing()) {
        // Capture finished. The upload blocks the loop, so the panel has to be
        // showing the waiting state *before* it starts — otherwise it sits on the
        // last waveform frame for up to two seconds and looks frozen.
        current = State::Sending;
        if (display::present()) {
          U8G2 &g = display::gfx();
          g.clearBuffer();
          g.setDrawColor(1);
          animations::drawThinking(g, "THINKING");
          g.sendBuffer();
        }
        sendAndReport();
      }
      return;

    case State::Sending:
      // sendAndReport() runs to completion inside the Listening branch, so this is
      // unreachable in practice. Handled rather than defaulted so a future async
      // upload has an obvious place to live.
      return;
  }
}

void draw(U8G2 &g) {
  switch (current) {
    case State::Arming:
      // Full bar: the recording has not started, so nothing has elapsed yet.
      animations::drawListening(g, VOICE_RECORD_SECONDS);
      return;
    case State::Listening:
      animations::drawListening(g, mic::secondsRemaining());
      return;
    case State::Sending:
      animations::drawThinking(g, "THINKING");
      return;
    case State::Idle:
      return;
  }
}

}  // namespace voice

