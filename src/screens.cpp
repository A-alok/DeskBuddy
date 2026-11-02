#include "screens.h"

#include "alarm_service.h"
#include "animations.h"
#include "bus.h"
#include "chime.h"
#include "clock_time.h"
#include "config.h"
#include "display.h"
#include "net_link.h"
#include "pomodoro_service.h"
#include "relay.h"
#include "stopwatch_service.h"
#include "timer_service.h"
#include "task_service.h"
#include "reminder_service.h"
#include "weather_service.h"
#include "voice.h"

namespace screens {

static Screen active = Screen::Home;
static uint8_t alarmCursor = 0;
static uint8_t taskCursor = 0;
static uint8_t reminderCursor = 0;

static char noticeTitle[20] = "";
static char noticeBody[28] = "";
static uint64_t noticeUntilMs = 0;

// Timer durations a double-tap cycles through when the timer is idle. Setting an
// arbitrary duration with one button is not worth the interaction cost; the
// dashboard does that. These cover what you actually want at a desk.
static const uint16_t PRESET_MINUTES[] = {5, 10, 15, 25, 45};
static const uint8_t PRESET_COUNT = sizeof(PRESET_MINUTES) / sizeof(PRESET_MINUTES[0]);
static uint8_t presetIndex = 1;  // 10 minutes

// --------------------------------------------------------------------------- //
// Lifecycle
// --------------------------------------------------------------------------- //

void begin() {
  active = Screen::Home;
  alarmCursor = 0;
  taskCursor = 0;
  reminderCursor = 0;
}

Screen current() { return active; }

const char *currentName() {
  switch (active) {
    case Screen::Timer: return "timer";
    case Screen::Stopwatch: return "stopwatch";
    case Screen::Pomodoro: return "pomodoro";
    case Screen::Alarms: return "alarms";
    case Screen::Tasks: return "tasks";
    case Screen::Reminders: return "reminders";
    case Screen::Relay: return "relay";
    case Screen::Network: return "network";
    default: return "home";
  }
}

void show(Screen screen) {
  const bool changed = screen != active;
  active = screen;
  display::noteActivity();
  // Asking for a specific screen outranks the resting face — including when that
  // screen is already the active one, and including when noteActivity() has just
  // re-armed the face because the panel was blanked. Dismissing last is what makes
  // both of those cases land on the requested screen; without it, a screen pushed
  // from the dashboard to an idle device changes nothing visible and looks like a
  // dropped command.
  animations::dismissFace();
  if (changed) bus::emit(bus::Event::ScreenChanged);
}

void showByName(const char *name) {
  if (name == nullptr) return;
  bus::RemoteScope guard;  // a screen pushed from the dashboard is not our event
  if (strcmp(name, "timer") == 0) active = Screen::Timer;
  else if (strcmp(name, "stopwatch") == 0) active = Screen::Stopwatch;
  else if (strcmp(name, "pomodoro") == 0) active = Screen::Pomodoro;
  else if (strcmp(name, "alarms") == 0) active = Screen::Alarms;
  else if (strcmp(name, "tasks") == 0) active = Screen::Tasks;
  else if (strcmp(name, "reminders") == 0) active = Screen::Reminders;
  else if (strcmp(name, "relay") == 0) active = Screen::Relay;
  else if (strcmp(name, "network") == 0) active = Screen::Network;
  else active = Screen::Home;
  display::noteActivity();
  animations::dismissFace();  // same reasoning as show(): an explicit request wins
}

void next() {
  uint8_t index = static_cast<uint8_t>(active) + 1;
  // Relay is part of the regular cycle so the LED can be toggled from the
  // panel by touch alone (tap to it, double tap to switch the light). Network
  // stays out of the cycle: forcing a reconnect is a diagnostic action, not an
  // everyday one, and it is still reachable from the dashboard.
  if (index >= static_cast<uint8_t>(Screen::Network)) index = 0;
  show(static_cast<Screen>(index));
}

// --------------------------------------------------------------------------- //
// Notices
// --------------------------------------------------------------------------- //

void showNotice(const char *title, const char *body, uint32_t durationMs) {
  strlcpy(noticeTitle, title != nullptr ? title : "", sizeof(noticeTitle));
  strlcpy(noticeBody, body != nullptr ? body : "", sizeof(noticeBody));
  noticeUntilMs = clocktime::monotonicMs() + durationMs;
  display::noteActivity();
}

bool noticeActive() {
  if (noticeUntilMs == 0) return false;
  if (clocktime::monotonicMs() > noticeUntilMs) {
    noticeUntilMs = 0;
    return false;
  }
  return true;
}

void dismissNotice() { noticeUntilMs = 0; }

// --------------------------------------------------------------------------- //
// Gestures
// --------------------------------------------------------------------------- //

static void timerPrimary() {
  if (timerService::state() == RunState::Running ||
      timerService::state() == RunState::Paused) {
    timerService::toggle();
  } else {
    timerService::start(PRESET_MINUTES[presetIndex] * 60U, "Timer");
  }
}

// timerSecondary() used to live here: hold cancelled a running timer, or cycled
// the preset when idle. Hold is push-to-talk now, so both moved to the dashboard.
// Cancelling is also reachable by voice ("cancel the timer").

void handleGesture(touch::Gesture gesture) {
  if (gesture == touch::Gesture::None) return;

  // A blanked panel consumes the gesture that wakes it: acting on a screen the
  // user could not read is worse than making them tap twice. A dimmed panel is
  // still legible, so it acts normally. Waking also brings up the face, so the
  // next touch is the one that opens the menu.
  if (display::wake()) return;

  // The face is the resting state, and any gesture is the cue to leave it. This
  // is a mode change rather than an action, so the gesture is spent here: a
  // double tap that dismissed the face *and* started a timer would fire something
  // the user could not see the state of when they touched the pad.
  if (animations::faceActive()) {
    show(Screen::Home);  // dismisses the face and notes the activity on the way
    bus::emit(bus::Event::Touch);
    chime::playConfirm();
    return;
  }

  // Mid-recording, any gesture aborts. There is nothing else a touch could
  // usefully mean while the device is listening, and being able to stop it is more
  // important than any action the same gesture would otherwise trigger.
  if (voice::active()) {
    voice::cancel();
    chime::playError();
    return;
  }

  // A ringing alarm or a notice captures everything until dismissed.
  if (alarmService::isRinging()) {
    alarmService::acknowledge();
    chime::stop();
    dismissNotice();
    display::noteActivity();
    return;
  }
  if (noticeActive()) {
    dismissNotice();
    display::noteActivity();
    return;
  }

  display::noteActivity();
  bus::emit(bus::Event::Touch);

  if (gesture == touch::Gesture::Tap) {
    next();
    return;
  }

  const bool primary = gesture == touch::Gesture::DoubleTap;

  // --- push to talk ------------------------------------------------------- //
  // Double tap on Home, hold anywhere else. Two gestures for one action because
  // each screen has a different gesture going spare: Home has no secondary action
  // worth a hold, and every other screen needs its double tap for start/pause.
  //
  // The cost is real and worth naming: hold no longer cancels a timer, laps the
  // stopwatch, skips a pomodoro phase, toggles an alarm or resyncs the link. Those
  // are dashboard-only now.
  const bool wantsVoice = (active == Screen::Home) ? primary : !primary;
  if (wantsVoice) {
    if (voice::start()) {
      chime::playConfirm();
    } else {
      chime::playError();
      showNotice("NO VOICE", voice::lastError(), 3000);
    }
    return;
  }

  // Only a double tap on a non-Home screen reaches here: tap navigated, hold went
  // to voice, and Home's double tap went to voice too. So every case below is the
  // screen's primary action, and there is no secondary branch left to write.
  switch (active) {
    case Screen::Timer:
      timerPrimary();
      chime::playConfirm();
      break;

    case Screen::Stopwatch:
      stopwatchService::toggle();
      chime::playConfirm();
      break;

    case Screen::Pomodoro:
      pomodoroService::toggle();
      chime::playConfirm();
      break;

    case Screen::Alarms: {
      if (alarmService::count() == 0) break;
      alarmCursor = static_cast<uint8_t>((alarmCursor + 1) % MAX_ALARMS);
      // Skip empty slots so the cursor only lands on real alarms.
      for (uint8_t i = 0; i < MAX_ALARMS && !alarmService::at(alarmCursor).used; ++i) {
        alarmCursor = static_cast<uint8_t>((alarmCursor + 1) % MAX_ALARMS);
      }
      chime::playConfirm();
      break;
    }

    case Screen::Tasks: {
      if (taskService::count() == 0) break;
      taskCursor = static_cast<uint8_t>((taskCursor + 1) % taskService::MAX_TASKS);
      for (uint8_t i = 0; i < taskService::MAX_TASKS && !taskService::list()[taskCursor].used; ++i) {
        taskCursor = static_cast<uint8_t>((taskCursor + 1) % taskService::MAX_TASKS);
      }
      chime::playConfirm();
      break;
    }

    case Screen::Reminders: {
      if (reminderService::count() == 0) break;
      reminderCursor = static_cast<uint8_t>((reminderCursor + 1) % reminderService::MAX_REMINDERS);
      for (uint8_t i = 0; i < reminderService::MAX_REMINDERS && !reminderService::list()[reminderCursor].used; ++i) {
        reminderCursor = static_cast<uint8_t>((reminderCursor + 1) % reminderService::MAX_REMINDERS);
      }
      chime::playConfirm();
      break;
    }

    case Screen::Relay:
      relay::toggle();
      chime::playConfirm();
      break;

    case Screen::Network:
      netLink::forceReconnect();
      chime::playConfirm();
      break;

    case Screen::Home:
    default:
      // Unreachable: Home's double tap is voice, and its hold is unassigned.
      break;
  }
}

// --------------------------------------------------------------------------- //
// Drawing
// --------------------------------------------------------------------------- //

static void drawHoldFeedback() {
  float progress = touch::holdProgress();
  if (progress <= 0.02f) return;
  // Visible confirmation that a long press is registering.
  display::progressBar(34, 48, 60, 4, progress);
}

static void drawHome() {
  U8G2 &g = display::gfx();
  struct tm local {};
  bool haveClock = clocktime::localTime(local);

  g.setFont(u8g2_font_logisoso28_tn);
  if (haveClock) {
    char stamp[12];
    snprintf(stamp, sizeof(stamp), "%02d:%02d", local.tm_hour, local.tm_min);
    display::centerText(stamp, 36);
  } else {
    g.setFont(u8g2_font_helvB10_tr);
    display::centerText("--:--", 30);
    g.setFont(u8g2_font_4x6_tf);
    display::centerText("waiting for time sync", 42);
  }

  if (haveClock) {
    char date[64];
    static const char *MONTHS[] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};
    
    if (weatherService::isValid()) {
      snprintf(date, sizeof(date), "%02d %s %04d   %.1f C %s", local.tm_mday,
               MONTHS[local.tm_mon % 12], local.tm_year + 1900,
               weatherService::current().tempNow, weatherService::current().shortDesc);
    } else {
      snprintf(date, sizeof(date), "%02d %s %04d", local.tm_mday,
               MONTHS[local.tm_mon % 12], local.tm_year + 1900);
    }
    
    g.setFont(u8g2_font_4x6_tf);
    display::centerText(date, 46);
  }

  // One line of "what is going on right now", chosen by priority.
  g.setFont(u8g2_font_4x6_tf);
  char status[28] = "";
  if (timerService::state() == RunState::Running) {
    char remaining[12];
    display::formatClock(timerService::remainingSeconds(), remaining, sizeof(remaining));
    snprintf(status, sizeof(status), "timer %s", remaining);
  } else if (pomodoroService::state() == RunState::Running) {
    char remaining[12];
    display::formatClock(pomodoroService::remainingSeconds(), remaining, sizeof(remaining));
    snprintf(status, sizeof(status), "%s %s",
             pomodoroPhaseName(pomodoroService::phase()), remaining);
  } else if (stopwatchService::state() == RunState::Running) {
    snprintf(status, sizeof(status), "stopwatch running");
  } else {
    int8_t nextAlarm = alarmService::nextAlarmIndex();
    if (nextAlarm >= 0) {
      const Alarm &alarm = alarmService::at(static_cast<uint8_t>(nextAlarm));
      snprintf(status, sizeof(status), "alarm %02u:%02u", alarm.hour, alarm.minute);
    } else if (relay::isOn()) {
      snprintf(status, sizeof(status), "relay on");
    }
  }
  if (status[0] != '\0') display::centerText(status, 54);
}

static void drawTimer() {
  U8G2 &g = display::gfx();
  const RunState state = timerService::state();
  const uint32_t remaining = timerService::remainingSeconds();

  char buffer[12];
  display::formatClock(remaining, buffer, sizeof(buffer));
  g.setFont(u8g2_font_logisoso28_tn);
  display::centerText(buffer, 38);

  g.setFont(u8g2_font_4x6_tf);
  if (state == RunState::Running || state == RunState::Paused) {
    const uint32_t total = timerService::durationSeconds();
    float progress = total > 0 ? 1.0f - (static_cast<float>(remaining) / total) : 0.0f;
    display::progressBar(14, 43, 100, 4, progress);
    display::centerText(state == RunState::Running ? "RUNNING" : "PAUSED", 53);
  } else {
    char idle[28];
    snprintf(idle, sizeof(idle), "preset %u min", PRESET_MINUTES[presetIndex]);
    display::centerText(idle, 47);
    display::centerText(state == RunState::Finished ? "FINISHED" : "READY", 53);
  }
}

static void drawStopwatch() {
  U8G2 &g = display::gfx();
  char buffer[14];
  display::formatStopwatch(stopwatchService::elapsedMs(), buffer, sizeof(buffer));

  g.setFont(u8g2_font_logisoso24_tn);
  display::centerText(buffer, 34);

  g.setFont(u8g2_font_4x6_tf);
  uint8_t count = stopwatchService::lapCount();
  if (count > 0) {
    char lap[24];
    display::formatStopwatch(stopwatchService::lapSplit(count - 1), buffer, sizeof(buffer));
    snprintf(lap, sizeof(lap), "lap %u  %s", count, buffer);
    display::centerText(lap, 45);
  }
  display::centerText(stopwatchService::state() == RunState::Running ? "RUNNING" : "STOPPED", 53);
}

static void drawPomodoro() {
  U8G2 &g = display::gfx();
  const PomodoroPhase phase = pomodoroService::phase();
  const RunState state = pomodoroService::state();

  g.setFont(u8g2_font_4x6_tf);
  const char *phaseLabel = "READY";
  if (phase == PomodoroPhase::Focus) phaseLabel = "FOCUS";
  else if (phase == PomodoroPhase::ShortBreak) phaseLabel = "SHORT BREAK";
  else if (phase == PomodoroPhase::LongBreak) phaseLabel = "LONG BREAK";
  display::centerText(phaseLabel, 16);

  char buffer[12];
  display::formatClock(pomodoroService::remainingSeconds(), buffer, sizeof(buffer));
  g.setFont(u8g2_font_logisoso24_tn);
  display::centerText(buffer, 41);

  g.setFont(u8g2_font_4x6_tf);
  if (state != RunState::Idle) {
    const uint32_t total = pomodoroService::phaseTotalSeconds();
    float progress = total > 0
                         ? 1.0f - (static_cast<float>(pomodoroService::remainingSeconds()) / total)
                         : 0.0f;
    display::progressBar(14, 44, 100, 4, progress);
  }

  // Cycle pips toward the long break.
  const uint8_t perLong = pomodoroService::cyclesPerLongBreak();
  const uint8_t done = perLong > 0 ? pomodoroService::completedFocusCycles() % perLong : 0;
  int16_t x = 64 - (perLong * 6) / 2;
  for (uint8_t i = 0; i < perLong && i < 12; ++i) {
    if (i < done) {
      g.drawBox(x + i * 6, 50, 4, 4);
    } else {
      g.drawFrame(x + i * 6, 50, 4, 4);
    }
  }
}

static void drawAlarms() {
  U8G2 &g = display::gfx();
  const uint8_t total = alarmService::count();

  g.setFont(u8g2_font_4x6_tf);
  if (total == 0) {
    display::centerText("No alarms set", 30);
    display::centerText("add them from the dashboard", 40);
    return;
  }

  if (!alarmService::at(alarmCursor).used) {
    for (uint8_t i = 0; i < MAX_ALARMS; ++i) {
      if (alarmService::at(i).used) {
        alarmCursor = i;
        break;
      }
    }
  }

  const Alarm &alarm = alarmService::at(alarmCursor);
  char stamp[12];
  snprintf(stamp, sizeof(stamp), "%02u:%02u", alarm.hour, alarm.minute);
  g.setFont(u8g2_font_logisoso24_tn);
  display::centerText(stamp, 36);

  g.setFont(u8g2_font_4x6_tf);
  display::centerText(alarm.label, 45);

  char meta[32];
  if (alarm.daysMask == 0) {
    snprintf(meta, sizeof(meta), "%s  once", alarm.enabled ? "ON " : "OFF");
  } else {
    static const char *DAYS = "MTWTFSS";
    char days[8];
    for (uint8_t i = 0; i < 7; ++i) {
      days[i] = (alarm.daysMask & (1u << i)) ? DAYS[i] : '.';
    }
    days[7] = '\0';
    snprintf(meta, sizeof(meta), "%s  %s", alarm.enabled ? "ON " : "OFF", days);
  }
  display::centerText(meta, 53);

  // Position within the list.
  char position[16];
  snprintf(position, sizeof(position), "%u/%u", alarmCursor + 1, MAX_ALARMS);
  g.setCursor(0, 16);
  g.print(position);
}

static void drawTasks() {
  U8G2 &g = display::gfx();
  const uint8_t total = taskService::count();

  g.setFont(u8g2_font_4x6_tf);
  if (total == 0) {
    display::centerText("No tasks open", 30);
    display::centerText("add them from the dashboard", 40);
    return;
  }

  if (!taskService::list()[taskCursor].used) {
    for (uint8_t i = 0; i < taskService::MAX_TASKS; ++i) {
      if (taskService::list()[i].used) {
        taskCursor = i;
        break;
      }
    }
  }

  const taskService::Task &task = taskService::list()[taskCursor];
  
  g.setFont(u8g2_font_helvB08_tr);
  display::centerText(task.title, 36);

  g.setFont(u8g2_font_4x6_tf);
  display::centerText(task.done ? "DONE" : "OPEN", 53);

  char position[16];
  snprintf(position, sizeof(position), "%u/%u", taskCursor + 1, total);
  g.setCursor(0, 16);
  g.print(position);
}

static void drawReminders() {
  U8G2 &g = display::gfx();
  const uint8_t total = reminderService::count();

  g.setFont(u8g2_font_4x6_tf);
  if (total == 0) {
    display::centerText("No reminders", 30);
    display::centerText("add them from the dashboard", 40);
    return;
  }

  if (!reminderService::list()[reminderCursor].used) {
    for (uint8_t i = 0; i < reminderService::MAX_REMINDERS; ++i) {
      if (reminderService::list()[i].used) {
        reminderCursor = i;
        break;
      }
    }
  }

  const reminderService::Reminder &rem = reminderService::list()[reminderCursor];
  
  g.setFont(u8g2_font_helvB08_tr);
  display::centerText(rem.text, 30);

  g.setFont(u8g2_font_4x6_tf);
  struct tm ti;
  time_t epochSecs = (rem.remindAt / 1000ULL) + clocktime::utcOffsetSeconds();
  if (gmtime_r(&epochSecs, &ti)) {
    char stamp[64];
    snprintf(stamp, sizeof(stamp), "%04d-%02d-%02d %02d:%02d",
             1900 + ti.tm_year, ti.tm_mon + 1, ti.tm_mday, ti.tm_hour, ti.tm_min);
    display::centerText(stamp, 45);
  }

  char position[16];
  snprintf(position, sizeof(position), "%u/%u", reminderCursor + 1, total);
  g.setCursor(0, 16);
  g.print(position);
}

static void drawRelay() {
  U8G2 &g = display::gfx();
  const bool on = relay::isOn();

  g.setFont(u8g2_font_helvB10_tr);
  display::centerText(on ? "LED ON" : "LED OFF", 26);

  // A little lamp glyph so the screen reads as a light, not a bare relay. When
  // the LED is on the bulb is filled and short rays radiate from it; off, it is
  // a hollow outline with no rays.
  const int16_t cx = 64;
  const int16_t cy = 40;
  const int16_t r = 7;
  if (on) {
    g.drawDisc(cx, cy, r);
    // rays
    g.drawLine(cx, cy - r - 2, cx, cy - r - 5);
    g.drawLine(cx, cy + r + 2, cx, cy + r + 5);
    g.drawLine(cx - r - 2, cy, cx - r - 5, cy);
    g.drawLine(cx + r + 2, cy, cx + r + 5, cy);
    g.drawLine(cx - r - 1, cy - r - 1, cx - r - 3, cy - r - 3);
    g.drawLine(cx + r + 1, cy - r - 1, cx + r + 3, cy - r - 3);
    g.drawLine(cx - r - 1, cy + r + 1, cx - r - 3, cy + r + 3);
    g.drawLine(cx + r + 1, cy + r + 1, cx + r + 3, cy + r + 3);
  } else {
    g.drawCircle(cx, cy, r);
  }

  g.setFont(u8g2_font_4x6_tf);
  display::centerText("2x tap to toggle", 60);
}

static void drawNetwork() {
  U8G2 &g = display::gfx();
  g.setFont(u8g2_font_4x6_tf);

  int16_t y = 16;
  char line[34];

  snprintf(line, sizeof(line), "WiFi  %s",
           netLink::wifiConnected() ? netLink::ssid() : "disconnected");
  g.setCursor(0, y);
  g.print(line);
  y += 8;

  if (netLink::wifiConnected()) {
    snprintf(line, sizeof(line), "IP    %s", netLink::ipAddress());
    g.setCursor(0, y);
    g.print(line);
    y += 8;
    snprintf(line, sizeof(line), "RSSI  %ld dBm", static_cast<long>(netLink::rssi()));
    g.setCursor(0, y);
    g.print(line);
    y += 8;
  }

  snprintf(line, sizeof(line), "Host  %s:%u", netLink::backendHost(),
           netLink::backendPort());
  g.setCursor(0, y);
  g.print(line);
  y += 8;

  const char *linkState = netLink::socketConnected()
                              ? "connected"
                              : (netLink::everConnected() ? "reconnecting" : "never linked");
  snprintf(line, sizeof(line), "Link  %s", linkState);
  g.setCursor(0, y);
  g.print(line);
  y += 8;

  snprintf(line, sizeof(line), "Clock %s",
           clocktime::isSynced() ? "synced (NTP)" : "not set");
  g.setCursor(0, y);
  g.print(line);
}

static void drawNotice() {
  U8G2 &g = display::gfx();
  g.drawRFrame(2, 12, 124, 40, 4);
  g.setFont(u8g2_font_helvB10_tr);
  display::centerText(noticeTitle, 30);
  g.setFont(u8g2_font_4x6_tf);
  if (noticeBody[0] != '\0') display::centerText(noticeBody, 44);
}

bool animating() {
  if (!display::present() || !display::isAwake()) return false;
  // The waveform is the whole point of the listening screen; at DISPLAY_FPS it
  // would lag well behind the audio driving it.
  if (voice::active()) return true;
  // True for as long as the face is up, including the still gaps between blinks.
  // Polling at ANIMATION_FPS costs a buffer clear per frame and nothing else,
  // because drawFace() refuses to redraw an unchanged pose — and being at the
  // faster cadence already is what keeps a blink from starting late.
  return animations::faceActive();
}

void render() {
  // No panel: the rest of the device still works, there is just nothing to draw.
  if (!display::present()) return;

  display::updatePowerSave();
  if (!display::isAwake()) return;

  // Revert to Home screen after idle timeout, unless we are already there.
  if (active != Screen::Home && display::idleTimeMs() > RETURN_TO_HOME_AFTER_MS) {
    show(Screen::Home);
  }

  U8G2 &g = display::gfx();
  g.clearBuffer();
  // Every screen draws lit-on-dark. Set it once here so a screen that flipped to
  // colour 0 for a knockout effect cannot leave the next frame invisible.
  g.setDrawColor(1);

  // A ringing alarm or a notice outranks the face. Both are the device trying to
  // tell you something, and neither should wait behind an idle animation that
  // only a touch would otherwise clear.
  if (alarmService::isRinging() || noticeActive()) animations::dismissFace();

  // Listening and thinking take the whole panel. Checked before the face and
  // before notices: while the device is recording, what it is recording is the
  // only thing worth showing, and the countdown is the user's cue to talk.
  if (voice::active()) {
    animations::dismissFace();
    voice::draw(g);
    g.sendBuffer();
    return;
  }

  // The face owns the whole panel — no status bar, no hint line. Those would be
  // chrome around something that is deliberately just a face.
  if (animations::faceActive()) {
    // Between blinks the frame is identical, and pushing an unchanged 1 KB buffer
    // over I2C 25 times a second would be pure waste. Skipping the send leaves
    // the panel holding exactly what it already shows.
    if (animations::drawFace(g)) g.sendBuffer();
    return;
  }

  if (alarmService::isRinging()) {
    const Alarm &alarm = alarmService::at(alarmService::ringingIndex());
    char body[40];
    snprintf(body, sizeof(body), "%02u:%02u  %s", alarm.hour, alarm.minute, alarm.label);
    display::statusBar("ALARM");
    g.drawRFrame(2, 12, 124, 40, 4);
    g.setFont(u8g2_font_helvB10_tr);
    display::centerText("ALARM", 30);
    g.setFont(u8g2_font_4x6_tf);
    display::centerText(body, 44);
    display::hintBar("any touch = dismiss");
    g.sendBuffer();
    return;
  }

  if (noticeActive()) {
    display::statusBar("NOTICE");
    drawNotice();
    display::hintBar("any touch = dismiss");
    g.sendBuffer();
    return;
  }

  // Hints describe the gestures that exist. Home advertises voice on the double
  // tap; everywhere else it is the hold, so "hold talk" appears on every other
  // screen. A hint that promises an action the firmware no longer performs is
  // worse than no hint at all.
  const char *title = "HOME";
  const char *hint = "tap next  2x talk";

  switch (active) {
    case Screen::Timer:
      title = "TIMER";
      hint = (timerService::state() == RunState::Running ||
              timerService::state() == RunState::Paused)
                 ? "tap next  2x pause  hold talk"
                 : "tap next  2x start  hold talk";
      drawTimer();
      break;
    case Screen::Stopwatch:
      title = "STOPWATCH";
      hint = stopwatchService::state() == RunState::Running
                 ? "tap next  2x stop  hold talk"
                 : "tap next  2x start  hold talk";
      drawStopwatch();
      break;
    case Screen::Pomodoro:
      title = "POMODORO";
      hint = pomodoroService::state() == RunState::Idle
                 ? "tap next  2x start  hold talk"
                 : "tap next  2x pause  hold talk";
      drawPomodoro();
      break;
    case Screen::Alarms:
      title = "ALARMS";
      hint = "tap next  2x select  hold talk";
      drawAlarms();
      break;
    case Screen::Tasks:
      title = "TASKS";
      hint = "tap next  2x cycle  hold talk";
      drawTasks();
      break;
    case Screen::Reminders:
      title = "REMINDERS";
      hint = "tap next  2x cycle  hold talk";
      drawReminders();
      break;
    case Screen::Relay:
      title = "LED";
      hint = "tap next  2x toggle  hold talk";
      drawRelay();
      break;
    case Screen::Network:
      title = "NETWORK";
      hint = "tap next  2x reconnect  hold talk";
      drawNetwork();
      break;
    default:
      drawHome();
      break;
  }

  display::statusBar(title);
  display::hintBar(hint);
  drawHoldFeedback();
  g.sendBuffer();
}

}  // namespace screens
