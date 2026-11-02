#include "bus.h"

namespace bus {

static const uint32_t CAPACITY = 16;

static Event ring[CAPACITY];
// A monotonically increasing write sequence rather than a wrapping index. Each
// reader keeps its own sequence, so neither can starve the other, and a reader
// that falls more than CAPACITY behind simply skips the events it missed.
static uint32_t writeSeq = 0;
static uint32_t uiSeq = 0;
static uint32_t netSeq = 0;
static uint8_t remoteDepth = 0;

void emit(Event event) {
  if (event == Event::None) return;
  // Events applied from the backend must not be echoed back to it.
  if (remoteDepth > 0) return;

  ring[writeSeq % CAPACITY] = event;
  ++writeSeq;
}

static bool readNext(uint32_t &cursor, Event &out) {
  if (cursor >= writeSeq) return false;

  // Overrun: the writer lapped this reader. Jump to the oldest entry still held
  // rather than returning stale slots.
  if (writeSeq - cursor > CAPACITY) {
    cursor = writeSeq - CAPACITY;
  }

  out = ring[cursor % CAPACITY];
  ++cursor;
  return true;
}

bool nextForUi(Event &out) { return readNext(uiSeq, out); }
bool nextForNet(Event &out) { return readNext(netSeq, out); }

bool applyingRemote() { return remoteDepth > 0; }

RemoteScope::RemoteScope() { ++remoteDepth; }
RemoteScope::~RemoteScope() {
  if (remoteDepth > 0) --remoteDepth;
}

const char *name(Event event) {
  switch (event) {
    case Event::TimerStarted: return "timer.started";
    case Event::TimerPaused: return "timer.paused";
    case Event::TimerResumed: return "timer.resumed";
    case Event::TimerCancelled: return "timer.cancelled";
    case Event::TimerFinished: return "timer.finished";
    case Event::StopwatchStarted: return "stopwatch.started";
    case Event::StopwatchStopped: return "stopwatch.stopped";
    case Event::StopwatchLapped: return "stopwatch.lapped";
    case Event::StopwatchReset: return "stopwatch.reset";
    case Event::PomodoroStarted: return "pomodoro.started";
    case Event::PomodoroPaused: return "pomodoro.paused";
    case Event::PomodoroResumed: return "pomodoro.resumed";
    case Event::PomodoroStopped: return "pomodoro.stopped";
    case Event::PomodoroSkipped: return "pomodoro.skipped";
    case Event::PomodoroPhaseChanged: return "pomodoro.phase_changed";
    case Event::RelaySet: return "relay.set";
    case Event::ScreenChanged: return "screen.changed";
    case Event::Touch: return "touch";
    case Event::AlarmTriggered: return "alarm.triggered";
    default: return "none";
  }
}

}  // namespace bus
