#pragma once
/**
 * Pomodoro cycle: focus -> short break -> ... -> long break every N blocks.
 * Same absolute-deadline approach as the timer. Durations persist in NVS.
 */

#include <Arduino.h>

#include "run_state.h"

enum class PomodoroPhase : uint8_t {
  Idle = 0,
  Focus,
  ShortBreak,
  LongBreak,
};

inline const char *pomodoroPhaseName(PomodoroPhase phase) {
  switch (phase) {
    case PomodoroPhase::Focus: return "focus";
    case PomodoroPhase::ShortBreak: return "short_break";
    case PomodoroPhase::LongBreak: return "long_break";
    default: return "idle";
  }
}

inline PomodoroPhase pomodoroPhaseFromName(const char *name) {
  if (name == nullptr) return PomodoroPhase::Idle;
  if (strcmp(name, "focus") == 0) return PomodoroPhase::Focus;
  if (strcmp(name, "short_break") == 0) return PomodoroPhase::ShortBreak;
  if (strcmp(name, "long_break") == 0) return PomodoroPhase::LongBreak;
  return PomodoroPhase::Idle;
}

namespace pomodoroService {

void begin();
void update();

void start();
void pause();
void resume();
void stop();
/** End the current phase early and move to the next one. */
void skip();
void toggle();
void resetCycles();

RunState state();
PomodoroPhase phase();
uint32_t remainingSeconds();
uint32_t phaseTotalSeconds();
uint8_t completedFocusCycles();

uint8_t focusMinutes();
uint8_t shortBreakMinutes();
uint8_t longBreakMinutes();
uint8_t cyclesPerLongBreak();
void setDurations(uint8_t focus, uint8_t shortBreak, uint8_t longBreak,
                  uint8_t cyclesPerLong);

void applyRemote(PomodoroPhase newPhase, RunState newState, uint64_t endsAtEpochMs,
                 uint32_t remainingIfPaused, uint8_t completedCycles, uint8_t focus,
                 uint8_t shortBreak, uint8_t longBreak, uint8_t cyclesPerLong);

}  // namespace pomodoroService
