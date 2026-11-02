#include "timer_service.h"

#include "bus.h"
#include "clock_time.h"
#include "config.h"

namespace timerService {

static RunState currentState = RunState::Idle;
static uint32_t duration = TIMER_DEFAULT_MINUTES * 60;
static uint64_t deadlineMs = 0;   // monotonic, valid while Running
static uint32_t pausedRemaining = 0;
static char currentLabel[33] = "Timer";

static void setLabel(const char *text) {
  if (text == nullptr || *text == '\0') text = "Timer";
  strlcpy(currentLabel, text, sizeof(currentLabel));
}

void begin() {
  currentState = RunState::Idle;
  duration = TIMER_DEFAULT_MINUTES * 60;
}

void start(uint32_t durationSeconds, const char *label) {
  if (durationSeconds == 0) return;
  duration = durationSeconds;
  setLabel(label);
  deadlineMs = clocktime::monotonicMs() + static_cast<uint64_t>(durationSeconds) * 1000ULL;
  pausedRemaining = 0;
  currentState = RunState::Running;
  bus::emit(bus::Event::TimerStarted);
}

void pause() {
  if (currentState != RunState::Running) return;
  pausedRemaining = remainingSeconds();
  deadlineMs = 0;
  currentState = RunState::Paused;
  bus::emit(bus::Event::TimerPaused);
}

void resume() {
  if (currentState != RunState::Paused) return;
  if (pausedRemaining == 0) {
    currentState = RunState::Finished;
    bus::emit(bus::Event::TimerFinished);
    return;
  }
  deadlineMs = clocktime::monotonicMs() + static_cast<uint64_t>(pausedRemaining) * 1000ULL;
  pausedRemaining = 0;
  currentState = RunState::Running;
  bus::emit(bus::Event::TimerResumed);
}

void cancel() {
  if (currentState == RunState::Idle || currentState == RunState::Cancelled) return;
  deadlineMs = 0;
  pausedRemaining = 0;
  currentState = RunState::Cancelled;
  bus::emit(bus::Event::TimerCancelled);
}

void adjust(int32_t deltaSeconds) {
  if (deltaSeconds == 0) return;

  if (currentState == RunState::Running) {
    int64_t remaining = static_cast<int64_t>(remainingSeconds()) + deltaSeconds;
    if (remaining < 1) remaining = 1;
    deadlineMs = clocktime::monotonicMs() + static_cast<uint64_t>(remaining) * 1000ULL;
  } else if (currentState == RunState::Paused) {
    int64_t remaining = static_cast<int64_t>(pausedRemaining) + deltaSeconds;
    pausedRemaining = remaining < 0 ? 0 : static_cast<uint32_t>(remaining);
  } else {
    // Idle: adjust the duration that a tap would start.
    int64_t next = static_cast<int64_t>(duration) + deltaSeconds;
    if (next < 60) next = 60;
    if (next > 99L * 3600L) next = 99L * 3600L;
    duration = static_cast<uint32_t>(next);
    return;
  }

  int64_t nextDuration = static_cast<int64_t>(duration) + deltaSeconds;
  duration = nextDuration < 1 ? 1 : static_cast<uint32_t>(nextDuration);
  bus::emit(bus::Event::TimerStarted);  // carries the new deadline
}

void toggle() {
  switch (currentState) {
    case RunState::Running: pause(); break;
    case RunState::Paused: resume(); break;
    default: start(duration, currentLabel); break;
  }
}

void update() {
  if (currentState != RunState::Running) return;
  if (clocktime::monotonicMs() < deadlineMs) return;

  deadlineMs = 0;
  pausedRemaining = 0;
  currentState = RunState::Finished;
  bus::emit(bus::Event::TimerFinished);
}

RunState state() { return currentState; }
uint32_t durationSeconds() { return duration; }
const char *label() { return currentLabel; }
uint64_t deadlineMonotonicMs() { return deadlineMs; }

uint32_t remainingSeconds() {
  switch (currentState) {
    case RunState::Running: {
      uint64_t now = clocktime::monotonicMs();
      if (now >= deadlineMs) return 0;
      // Round up so the display shows "10:00" the instant a 10:00 timer starts
      // instead of flashing 09:59.
      return static_cast<uint32_t>((deadlineMs - now + 999ULL) / 1000ULL);
    }
    case RunState::Paused: return pausedRemaining;
    case RunState::Idle: return duration;
    default: return 0;
  }
}

void applyRemote(RunState newState, uint32_t remoteDuration, uint64_t endsAtEpochMs,
                 uint32_t remainingSecondsIfPaused, const char *newLabel) {
  bus::RemoteScope guard;

  setLabel(newLabel);
  if (remoteDuration > 0) duration = remoteDuration;

  switch (newState) {
    case RunState::Running: {
      uint64_t mono = clocktime::epochToMonotonicMs(endsAtEpochMs);
      if (mono == 0) {
        // Clock not synced yet, so an absolute instant is meaningless to us.
        // Fall back to the reported remaining time — less precise but usable.
        uint32_t fallback = remainingSecondsIfPaused > 0 ? remainingSecondsIfPaused : duration;
        mono = clocktime::monotonicMs() + static_cast<uint64_t>(fallback) * 1000ULL;
      }
      deadlineMs = mono;
      pausedRemaining = 0;
      currentState = RunState::Running;
      break;
    }
    case RunState::Paused:
      deadlineMs = 0;
      pausedRemaining = remainingSecondsIfPaused;
      currentState = RunState::Paused;
      break;
    default:
      deadlineMs = 0;
      pausedRemaining = 0;
      currentState = newState;
      break;
  }
}

}  // namespace timerService
