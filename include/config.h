#pragma once
/**
 * AI DeskMate — compile-time configuration.
 *
 * Pin assignments match the confirmed wiring in
 * docs/AI-DeskMate-Project-Reference.md (validated through Test 6).
 * Change nothing here without changing the doc too.
 */

#include <Arduino.h>

// ===========================================================================
//  TIMEZONE  — set this first, it is the thing you will notice immediately
// ===========================================================================
// POSIX TZ string. Note the sign is INVERTED from what you expect:
// UTC+5:30 is written "-5:30".
//   India         "IST-5:30"
//   Central Europe"CET-1CEST,M3.5.0,M10.5.0/3"
//   UK            "GMT0BST,M3.5.0/1,M10.5.0"
//   US Eastern    "EST5EDT,M3.2.0,M11.1.0"
//   US Pacific    "PST8PDT,M3.2.0,M11.1.0"
//   UTC           "UTC0"
// India Standard Time, UTC+5:30, no daylight saving.
// Read from this machine's own setting (Get-TimeZone -> "India Standard Time").
#define DESKMATE_TZ "IST-5:30"

#define NTP_SERVER_1 "pool.ntp.org"
#define NTP_SERVER_2 "time.google.com"

// ===========================================================================
//  PINS — confirmed working
// ===========================================================================

// --- OLED: SH1106 128x64 over I2C, address 0x3C -------------------------- //
#define PIN_I2C_SDA 8
#define PIN_I2C_SCL 9
#define I2C_CLOCK_HZ 400000UL

// --- INMP441 microphone: I2S peripheral 0, receive ----------------------- //
// Wired and tested. The firmware below does not open this bus yet: capture is
// Stage 8, and the backend has no speech-to-text endpoint to send audio to.
#define PIN_MIC_BCLK 4
#define PIN_MIC_WS 5
#define PIN_MIC_DOUT 6

// --- MAX98357A amplifier: I2S peripheral 1, transmit --------------------- //
#define PIN_AMP_BCLK 15
#define PIN_AMP_LRC 16
#define PIN_AMP_DIN 7

// Set to 1 if the amp's SD pin is wired to a GPIO so firmware can mute the
// output stage between sounds (kills idle hiss, saves a little current).
// Set to 0 if SD is tied straight to 3V3.
//
// Confirmed 16 Oct 2026: SD is hardwired to 3V3 on this build (always-on), so
// the firmware must NOT drive an SD pin — doing so was leaving the output stage
// in the wrong state. 0 = leave the amp permanently enabled.
#define AMP_HAS_SD_PIN 0
#define PIN_AMP_SD 10

// --- TTP223 capacitive touch -------------------------------------------- //
#define PIN_TOUCH 14
// Polarity is auto-detected at boot by sampling the idle level. Keep your
// finger off the pad for the first half second after power-on.

// --- Relay module -------------------------------------------------------- //
#define PIN_RELAY 13
// Most opto-isolated 5V modules energise on a LOW input. Set to 0 if yours
// energises on HIGH. Getting this backwards means the relay is closed
// whenever the device is idle, which you will hear.
#define RELAY_ACTIVE_LOW 1

// --- Battery sense (Stage 16, not yet wired) ---------------------------- //
// ADC1 only — ADC2 is unusable while Wi-Fi is running.
#define BATTERY_SENSE_ENABLED 0
#define PIN_BATTERY_SENSE 1
// Divider ratio: with 100k/100k, Vbat = Vadc * 2.0
#define BATTERY_DIVIDER_RATIO 2.0f
#define BATTERY_EMPTY_MV 3200
#define BATTERY_FULL_MV 4150

// ===========================================================================
//  TOUCH GESTURES
// ===========================================================================
#define TOUCH_DEBOUNCE_MS 40
#define TOUCH_DOUBLE_TAP_WINDOW_MS 320
#define TOUCH_HOLD_MS 900

// Traces raw pin transitions and prints the level every few seconds. Set to 0
// once touch is trusted — it is noisy on purpose.
// Touch confirmed working 25 Sep 2026, so this is off; the per-gesture line in
// main.cpp is the useful one now.
#define TOUCH_DEBUG 0

// ===========================================================================
//  DIAGNOSTIC MODE
// ===========================================================================
// 1 = boot into the hardware self-test in src/diagnostics.cpp instead of the
//     normal UI: memory report, OLED test patterns, relay clicks, chime, then a
//     live raw-touch display. Networking is skipped.
// 0 = normal operation.
// Use this to find out *which* peripheral is at fault, rather than guessing.
#define DIAGNOSTIC_MODE 0
// One button, three gestures:
//   tap        -> primary action on the current screen (start / pause / toggle)
//   double tap -> next screen
//   hold       -> secondary action (cancel / reset / skip)

// ===========================================================================
//  DISPLAY
// ===========================================================================
#define DISPLAY_FPS 10
// Blank the panel after this long with no interaction. OLEDs burn in.
#define DISPLAY_DIM_AFTER_MS 120000UL
#define RETURN_TO_HOME_AFTER_MS 300000UL
#define DISPLAY_OFF_AFTER_MS 300000UL
// Transient notices (timer finished, alarm ringing) hold the screen this long.
#define NOTICE_DURATION_MS 25000UL

// ===========================================================================
//  ANIMATIONS
// ===========================================================================
// Eyelid ramp: how long the eyes take to go from the sleeping slit to fully
// open. intellar's original wakeup() steps the height 2 px at a time from 2 to
// 40 with no delay, so its duration is however long 20 I2C frames take — about
// 460 ms on this panel. 420 ms reproduces that pace on a time-driven clock.
#define WAKE_OPEN_MS 420UL

// Once open, the face stays up and blinks until a touch dismisses it into the
// menu. It is the device's resting state, not a transition.
//
// One blink, lid down and back up. intellar's blink() is six frames paced by the
// I2C write, roughly 140 ms; 180 ms is the same gesture with a little more weight
// so it does not look like a glitch on a panel this small.
#define BLINK_DURATION_MS 180UL
// Gap between blinks, picked at random inside this range. A fixed interval makes
// the face look like a metronome — the irregularity is what sells it as alive.
#define BLINK_MIN_GAP_MS 2200UL
#define BLINK_MAX_GAP_MS 5200UL
// Static screens redraw at DISPLAY_FPS because nothing on them moves faster than
// once a second. An animation at 10 fps reads as a stutter, so the loop switches
// to this rate while one is running. 25 fps is what the panel can actually
// sustain: a 1 KB full-frame buffer over 400 kHz I2C costs roughly 23 ms.
#define ANIMATION_FPS 25
// How fast the ear arcs walk outward while listening, in ms per step. The listening
// face lives in include/eye_geometry.h; only its tempo is a tunable.
#define EAR_RIPPLE_STEP_MS 120

// ===========================================================================
//  VOICE / MICROPHONE
// ===========================================================================
// Maximum recording length for a push-to-talk capture — a hard ceiling, not the
// usual stopping point. The recording normally ends earlier, as soon as the user
// stops talking (see the silence settings below). This is the backstop for
// someone who never stops. Also the denominator for the remaining-time bar.
//
// Set to 20 s so normal speech never reaches it — the clip ends when YOU stop
// talking, not on a fixed count. A ceiling still has to exist: the audio lives
// in one pre-allocated PSRAM buffer (20 s ~= 625 KB), and it is the safety net
// that stops a recording running forever if silence detection ever misfires.
// Raise toward 30 s if you want even longer dictation; the S3's 8 MB PSRAM has
// the room.
#define VOICE_RECORD_SECONDS 20.0f

// --- Voice auto-stop on silence ----------------------------------------- //
// The capture ends on its own once the speaker goes quiet, so a short command
// does not pad out to the full ceiling and a long sentence is not cut off at 5s.
//
// Silence detection is ADAPTIVE, not a fixed threshold. At the start of each
// recording the mic measures the room's quiet level (the "noise floor") for
// VOICE_FLOOR_LEARN_MS, then treats anything VOICE_FLOOR_MULTIPLE times louder
// than that floor as speech. This is why it works in both a quiet and a noisy
// room without hand-tuning — the earlier fixed 0.06 threshold tripped on the
// INMP441's own noise floor and so never saw silence, running the full ceiling.
//
// The floor is tracked continuously (it follows the quiet gaps between words),
// so it works even when the user starts speaking the instant the mic opens.
//
// Speech must be this many times louder than the floor to count. Raise it if a
// noisy room keeps the recording open; lower it toward 2x if quiet speech is
// treated as silence.
#define VOICE_FLOOR_MULTIPLE 3.0f
// Absolute minimum smoothed RMS (16-bit counts, after gain) that can count as
// speech, so a very quiet room cannot make the threshold trivially low.
#define VOICE_MIN_SPEECH_RMS 600.0f
// Sound must stay above the speech threshold this long to count as the user
// starting to talk. Rejects clicks and desk bumps; short enough not to miss a
// one-word command.
#define VOICE_ONSET_HOLD_MS 120UL
// Audio discarded right after the mic clock starts. The INMP441 settles for
// ~80-100 ms with a large swing; a real clip showed rms 17270 (clipping) in its
// first 250 ms against ~2800 for the speech after it. That burst was recorded
// and treated as the start of speech, ending the clip early, mid-sentence.
#define MIC_WARMUP_MS 150UL
// Stop after this many continuous milliseconds of silence — but only once the
// user has actually started speaking. ~900 ms is a natural end-of-sentence pause
// without feeling like it hangs waiting.
#define VOICE_SILENCE_HANG_MS 1200UL
// Shortest possible clip. Protects against the confirm-chime tail or a cough
// ending the recording in the first fraction of a second.
#define VOICE_MIN_RECORD_MS 700UL
// Grace period at the start to begin speaking. If nothing above the silence
// threshold is heard within this window, the capture ends anyway so a mis-tap
// does not record the full ceiling of silence.
#define VOICE_SPEECH_ONSET_MS 12000UL
// 1 = print the live mic level ~5x/sec during a capture so the silence threshold
// can be tuned to the room. Set back to 0 once VOICE_SILENCE_LEVEL is dialled in.
#define MIC_LEVEL_DEBUG 1

// 16 kHz mono 16-bit is exactly what POST /api/voice/transcribe documents, and
// what Whisper wants. Sending more would cost upload time and buy nothing:
// Whisper resamples to 16 kHz internally.
#define MIC_SAMPLE_RATE 16000

// The INMP441 is a 24-bit part that transmits left-justified in a 32-bit slot, so
// the bus has to be read 32 bits wide even though we store 16.
#define MIC_BITS_PER_SAMPLE 32

// Which I2S slot the mic actually lands in.
//   0 = left slot   (INMP441 with L/R tied to GND)
//   1 = right slot
// This is worth a config flag rather than a constant. The INMP441 datasheet says
// L/R low means it drives the left slot, but the ESP32's I2S peripheral has a
// long-documented phase quirk where ONLY_LEFT reads the right slot instead, and
// which one you get depends on the silicon revision. Picking wrong gives perfect
// silence with no error anywhere. The boot log prints RMS so you can tell.
#define MIC_USE_RIGHT_SLOT 0

// Right-shift applied to the raw 32-bit word to reach 16-bit. Each +1 halves the
// gain; each -1 doubles it.
//
// 16 would be unity: bits 31..16 of a left-justified 24-bit sample. The INMP441
// is a quiet part, so some gain is needed.
//
// Tuned 16 Oct 2026: at 11 (32x) real speech recorded peak=32768 (hard clipping)
// and rms~17000 (~52% of full scale). That distortion made Whisper mis-hear the
// command, and because the amplified noise floor never fell below the silence
// threshold, the clip also ran the full 12 s. 13 (8x) drops it two steps: peaks
// land under the ceiling and quiet gaps actually read as quiet. If speech now
// comes back too soft (rms < ~2000), step down to 12; if it still clips
// (peak = 32768), step up to 14.
// Re-tuned: at 13 speech still averaged rms 15000-30000 with peak 32768, i.e.
// clipping constantly. 15 is another 4x down.
#define MIC_GAIN_SHIFT 15

// Full-scale reference for the on-screen waveform and the silence detector, in
// 16-bit counts after gain. Lowered alongside the gain change above so a normal
// speaking level still fills a useful fraction of the bar and the silence
// threshold stays meaningful. Visual + silence detection only; the audio sent
// upstream is untouched.
#define MIC_LEVEL_FULL_SCALE 8000.0f

// ===========================================================================
//  POMODORO DEFAULTS
// ===========================================================================
#define POMODORO_FOCUS_MIN 25
#define POMODORO_SHORT_BREAK_MIN 5
#define POMODORO_LONG_BREAK_MIN 15
#define POMODORO_CYCLES_PER_LONG 4

// ===========================================================================
//  TIMER / ALARM
// ===========================================================================
#define TIMER_DEFAULT_MINUTES 10
#define MAX_ALARMS 8
#define MAX_LAPS 16

// ===========================================================================
//  NETWORK
// ===========================================================================
#define WIFI_CONNECT_TIMEOUT_MS 20000UL
#define WIFI_RETRY_INTERVAL_MS 15000UL
// The backend marks a device offline after 30s of silence.
#define HEARTBEAT_INTERVAL_MS 10000UL
#define WS_RECONNECT_INTERVAL_MS 4000UL
#define SNAPSHOT_TIMEOUT_MS 8000UL

#define FIRMWARE_VERSION "0.1.0"

// ===========================================================================
//  SOUND
// ===========================================================================
#define AUDIO_SAMPLE_RATE 22050
// 0 silences everything without removing the code paths.
#define CHIME_ENABLED 1
