#pragma once
/** Mirrors RunState in backend/app/models.py. */

#include <Arduino.h>

enum class RunState : uint8_t {
  Idle = 0,
  Running,
  Paused,
  Finished,
  Cancelled,
};

inline const char *runStateName(RunState state) {
  switch (state) {
    case RunState::Running: return "running";
    case RunState::Paused: return "paused";
    case RunState::Finished: return "finished";
    case RunState::Cancelled: return "cancelled";
    default: return "idle";
  }
}

inline RunState runStateFromName(const char *name) {
  if (name == nullptr) return RunState::Idle;
  if (strcmp(name, "running") == 0) return RunState::Running;
  if (strcmp(name, "paused") == 0) return RunState::Paused;
  if (strcmp(name, "finished") == 0) return RunState::Finished;
  if (strcmp(name, "cancelled") == 0) return RunState::Cancelled;
  return RunState::Idle;
}
