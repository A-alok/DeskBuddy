#include "pomodoro_service.h"

#include <Preferences.h>

#include "bus.h"
#include "clock_time.h"
#include "config.h"

namespace pomodoroService {

static RunState currentState = RunState::Idle;
static PomodoroPhase currentPhase = PomodoroPhase::Idle;
static uint64_t deadlineMs = 0;
static uint32_t pausedRemaining = 0;
static uint8_t cyclesDone = 0;

static uint8_t cfgFocus = POMODORO_FOCUS_MIN;
static uint8_t cfgShort = POMODORO_SHORT_BREAK_MIN;
static uint8_t cfgLong = POMODORO_LONG_BREAK_MIN;
static uint8_t cfgPerLong = POMODORO_CYCLES_PER_LONG;

static Preferences prefs;

static void persist() {
  if (!prefs.begin("deskmate", false)) return;
  prefs.putUChar("pomo_focus", cfgFocus);
  prefs.putUChar("pomo_short", cfgShort);
  prefs.putUChar("pomo_long", cfgLong);
  prefs.putUChar("pomo_per", cfgPerLong);
  prefs.end();
}

static uint32_t secondsForPhase(PomodoroPhase phase) {
  switch (phase) {
    case PomodoroPhase::Focus: return static_cast<uint32_t>(cfgFocus) * 60UL;
    case PomodoroPhase::ShortBreak: return static_cast<uint32_t>(cfgShort) * 60UL;
    case PomodoroPhase::LongBreak: return static_cast<uint32_t>(cfgLong) * 60UL;
    default: return 0;
  }
}

static void enterPhase(PomodoroPhase phase) {
  currentPhase = phase;
  currentState = RunState::Running;
  pausedRemaining = 0;
  deadlineMs = clocktime::monotonicMs() +
               static_cast<uint64_t>(secondsForPhase(phase)) * 1000ULL;
}

void begin() {
  if (prefs.begin("deskmate", true)) {
    cfgFocus = prefs.getUChar("pomo_focus", POMODORO_FOCUS_MIN);
    cfgShort = prefs.getUChar("pomo_short", POMODORO_SHORT_BREAK_MIN);
    cfgLong = prefs.getUChar("pomo_long", POMODORO_LONG_BREAK_MIN);
    cfgPerLong = prefs.getUChar("pomo_per", POMODORO_CYCLES_PER_LONG);
    prefs.end();
  }
  if (cfgFocus == 0) cfgFocus = POMODORO_FOCUS_MIN;
  if (cfgShort == 0) cfgShort = POMODORO_SHORT_BREAK_MIN;
  if (cfgLong == 0) cfgLong = POMODORO_LONG_BREAK_MIN;
  if (cfgPerLong == 0) cfgPerLong = POMODORO_CYCLES_PER_LONG;
}

void start() {
  // cyclesDone is deliberately left alone: stopping and restarting mid-session
  // should not lose the blocks you already earned toward a long break.
  enterPhase(PomodoroPhase::Focus);
  bus::emit(bus::Event::PomodoroStarted);
}

void pause() {
  if (currentState != RunState::Running) return;
  pausedRemaining = remainingSeconds();
  deadlineMs = 0;
  currentState = RunState::Paused;
  bus::emit(bus::Event::PomodoroPaused);
}

void resume() {
  if (currentState != RunState::Paused) return;
  deadlineMs = clocktime::monotonicMs() +
               static_cast<uint64_t>(pausedRemaining == 0 ? 1 : pausedRemaining) * 1000ULL;
  pausedRemaining = 0;
  currentState = RunState::Running;
  bus::emit(bus::Event::PomodoroResumed);
}

void stop() {
  if (currentState == RunState::Idle && currentPhase == PomodoroPhase::Idle) return;
  currentPhase = PomodoroPhase::Idle;
  currentState = RunState::Idle;
  deadlineMs = 0;
  pausedRemaining = 0;
  bus::emit(bus::Event::PomodoroStopped);
}

void toggle() {
  switch (currentState) {
    case RunState::Running: pause(); break;
    case RunState::Paused: resume(); break;
    default: start(); break;
  }
}

void resetCycles() { cyclesDone = 0; }

/** Which phase follows the one that just ended. */
static PomodoroPhase advance(bool natural) {
  if (currentPhase == PomodoroPhase::Focus) {
    if (cyclesDone < 255) ++cyclesDone;
    bool longDue = cfgPerLong > 0 && (cyclesDone % cfgPerLong) == 0;
    enterPhase(longDue ? PomodoroPhase::LongBreak : PomodoroPhase::ShortBreak);
  } else {
    enterPhase(PomodoroPhase::Focus);
  }
  bus::emit(natural ? bus::Event::PomodoroPhaseChanged : bus::Event::PomodoroSkipped);
  return currentPhase;
}

void skip() {
  if (currentState == RunState::Idle) return;
  advance(false);
}

void update() {
  if (currentState != RunState::Running) return;
  if (clocktime::monotonicMs() < deadlineMs) return;
  advance(true);
}

RunState state() { return currentState; }
PomodoroPhase phase() { return currentPhase; }
uint8_t completedFocusCycles() { return cyclesDone; }
uint32_t phaseTotalSeconds() { return secondsForPhase(currentPhase); }

uint32_t remainingSeconds() {
  if (currentState == RunState::Running) {
    uint64_t now = clocktime::monotonicMs();
    if (now >= deadlineMs) return 0;
    return static_cast<uint32_t>((deadlineMs - now + 999ULL) / 1000ULL);
  }
  if (currentState == RunState::Paused) return pausedRemaining;
  return secondsForPhase(PomodoroPhase::Focus);
}

uint8_t focusMinutes() { return cfgFocus; }
uint8_t shortBreakMinutes() { return cfgShort; }
uint8_t longBreakMinutes() { return cfgLong; }
uint8_t cyclesPerLongBreak() { return cfgPerLong; }

void setDurations(uint8_t focus, uint8_t shortBreak, uint8_t longBreak,
                  uint8_t cyclesPerLong) {
  if (focus > 0) cfgFocus = focus;
  if (shortBreak > 0) cfgShort = shortBreak;
  if (longBreak > 0) cfgLong = longBreak;
  if (cyclesPerLong > 0) cfgPerLong = cyclesPerLong;
  persist();
}

void applyRemote(PomodoroPhase newPhase, RunState newState, uint64_t endsAtEpochMs,
                 uint32_t remainingIfPaused, uint8_t completedCycles, uint8_t focus,
                 uint8_t shortBreak, uint8_t longBreak, uint8_t cyclesPerLong) {
  bus::RemoteScope guard;

  bool configChanged = focus != cfgFocus || shortBreak != cfgShort ||
                       longBreak != cfgLong || cyclesPerLong != cfgPerLong;
  if (focus > 0) cfgFocus = focus;
  if (shortBreak > 0) cfgShort = shortBreak;
  if (longBreak > 0) cfgLong = longBreak;
  if (cyclesPerLong > 0) cfgPerLong = cyclesPerLong;
  if (configChanged) persist();

  cyclesDone = completedCycles;
  currentPhase = newPhase;

  switch (newState) {
    case RunState::Running: {
      uint64_t mono = clocktime::epochToMonotonicMs(endsAtEpochMs);
      if (mono == 0) {
        uint32_t fallback = remainingIfPaused > 0 ? remainingIfPaused
                                                 : secondsForPhase(newPhase);
        mono = clocktime::monotonicMs() + static_cast<uint64_t>(fallback) * 1000ULL;
      }
      deadlineMs = mono;
      pausedRemaining = 0;
      currentState = RunState::Running;
      break;
    }
    case RunState::Paused:
      deadlineMs = 0;
      pausedRemaining = remainingIfPaused;
      currentState = RunState::Paused;
      break;
    default:
      deadlineMs = 0;
      pausedRemaining = 0;
      currentState = newState;
      break;
  }
}

}  // namespace pomodoroService
