#pragma once
/**
 * A tiny local event queue with two independent readers.
 *
 * Services are pure logic: they change their own state and drop a note in here.
 * Two consumers read it at their own pace and never block each other:
 *
 *   UI   -> plays the chime, takes over the screen
 *   NET  -> publishes to the backend
 *
 * Separate read cursors matter. A single shared queue would mean whichever
 * consumer ran first swallowed the event, so a timer finishing while the socket
 * was busy would ring but not publish, or publish but not ring.
 *
 * It also solves the echo problem: state applied from a backend event is wrapped
 * in a RemoteScope, which suppresses emission, so a dashboard "start timer" does
 * not bounce back to the dashboard as a device event.
 */

#include <Arduino.h>

namespace bus {

enum class Event : uint8_t {
  None = 0,
  TimerStarted,
  TimerPaused,
  TimerResumed,
  TimerCancelled,
  TimerFinished,
  StopwatchStarted,
  StopwatchStopped,
  StopwatchLapped,
  StopwatchReset,
  PomodoroStarted,
  PomodoroPaused,
  PomodoroResumed,
  PomodoroStopped,
  PomodoroSkipped,
  PomodoroPhaseChanged,
  RelaySet,
  ScreenChanged,
  Touch,
  AlarmTriggered,
};

/** Queue an event. No-op while a RemoteScope is held. */
void emit(Event event);

/** Read cursor for the UI (sounds, notices). Returns false when caught up. */
bool nextForUi(Event &out);

/** Read cursor for the network layer. Returns false when caught up. */
bool nextForNet(Event &out);

/** True while an inbound backend event is being applied. */
bool applyingRemote();

/**
 * RAII guard. Hold this around any state change that came from the backend so
 * it is not re-published.
 */
class RemoteScope {
 public:
  RemoteScope();
  ~RemoteScope();
  RemoteScope(const RemoteScope &) = delete;
  RemoteScope &operator=(const RemoteScope &) = delete;
};

const char *name(Event event);

}  // namespace bus
