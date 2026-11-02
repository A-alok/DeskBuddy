#include "stopwatch_service.h"

#include "bus.h"
#include "clock_time.h"
#include "config.h"

namespace stopwatchService {

static RunState currentState = RunState::Idle;
static uint64_t accumulated = 0;   // ms banked from earlier segments
static uint64_t segmentStart = 0;  // monotonic, valid while Running
static uint64_t laps[MAX_LAPS];
static uint8_t laps_used = 0;

void begin() {
  currentState = RunState::Idle;
  accumulated = 0;
  segmentStart = 0;
  laps_used = 0;
}

uint64_t elapsedMs() {
  if (currentState != RunState::Running) return accumulated;
  uint64_t now = clocktime::monotonicMs();
  return accumulated + (now > segmentStart ? now - segmentStart : 0);
}

void start() {
  if (currentState == RunState::Running) return;
  segmentStart = clocktime::monotonicMs();
  currentState = RunState::Running;
  bus::emit(bus::Event::StopwatchStarted);
}

void stop() {
  if (currentState != RunState::Running) return;
  accumulated = elapsedMs();
  segmentStart = 0;
  currentState = RunState::Paused;
  bus::emit(bus::Event::StopwatchStopped);
}

void lap() {
  if (currentState != RunState::Running) return;
  if (laps_used >= MAX_LAPS) {
    // Ring the buffer: keep the most recent MAX_LAPS splits.
    for (uint8_t i = 1; i < MAX_LAPS; ++i) laps[i - 1] = laps[i];
    laps_used = MAX_LAPS - 1;
  }
  laps[laps_used++] = elapsedMs();
  bus::emit(bus::Event::StopwatchLapped);
}

void reset() {
  bool wasClean = currentState == RunState::Idle && accumulated == 0 && laps_used == 0;
  currentState = RunState::Idle;
  accumulated = 0;
  segmentStart = 0;
  laps_used = 0;
  if (!wasClean) bus::emit(bus::Event::StopwatchReset);
}

void toggle() {
  if (currentState == RunState::Running) {
    stop();
  } else {
    start();
  }
}

RunState state() { return currentState; }
uint8_t lapCount() { return laps_used; }

uint64_t lapAt(uint8_t index) { return index < laps_used ? laps[index] : 0; }

uint64_t lapSplit(uint8_t index) {
  if (index >= laps_used) return 0;
  return index == 0 ? laps[0] : laps[index] - laps[index - 1];
}

void applyRemote(RunState newState, uint64_t remoteAccumulatedMs,
                 uint64_t startedAtEpochMs) {
  bus::RemoteScope guard;

  accumulated = remoteAccumulatedMs;
  if (newState == RunState::Running) {
    uint64_t mono = clocktime::epochToMonotonicMs(startedAtEpochMs);
    segmentStart = mono != 0 ? mono : clocktime::monotonicMs();
    currentState = RunState::Running;
  } else {
    segmentStart = 0;
    currentState = newState;
    if (newState == RunState::Idle) laps_used = 0;
  }
}

}  // namespace stopwatchService
