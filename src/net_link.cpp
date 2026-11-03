#include "net_link.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WebSocketsClient.h>
#include <WiFi.h>
#include <Preferences.h>

#include "alarm_service.h"
#include "bus.h"
#include "chime.h"
#include "clock_time.h"
#include "config.h"
#include "display.h"
#include "pomodoro_service.h"
#include "relay.h"
#include "screens.h"
#include "secrets.h"
#include "stopwatch_service.h"
#include "timer_service.h"
#include "task_service.h"
#include "reminder_service.h"
#include "weather_service.h"
#include "voice.h"

namespace netLink {

/**
 * Why did the association fail?
 *
 * "connecting..." forever is useless. The ESP-IDF disconnect reason separates
 * the two causes that look identical from the outside: the AP was never seen,
 * versus the AP rejected our key.
 */
static const char *wifiReasonName(uint8_t reason) {
  switch (reason) {
    case 1: return "UNSPECIFIED";
    case 2: return "AUTH_EXPIRE";
    case 4: return "ASSOC_EXPIRE";
    case 6: return "NOT_AUTHED";
    case 7: return "NOT_ASSOCED";
    case 8: return "ASSOC_LEAVE";
    case 15: return "4WAY_HANDSHAKE_TIMEOUT (wrong password)";
    case 200: return "BEACON_TIMEOUT";
    case 201: return "NO_AP_FOUND (SSID not visible from here)";
    case 202: return "AUTH_FAIL (wrong password)";
    case 203: return "ASSOC_FAIL";
    case 204: return "HANDSHAKE_TIMEOUT (wrong password)";
    case 205: return "CONNECTION_FAIL";
    default: return "see esp_wifi_types.h";
  }
}

static void onWifiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  switch (event) {
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED: {
      const uint8_t reason = info.wifi_sta_disconnected.reason;
      Serial.printf("[net] association failed: reason %u — %s\n", reason,
                    wifiReasonName(reason));
      break;
    }
    case ARDUINO_EVENT_WIFI_STA_CONNECTED:
      Serial.println("[net] associated, waiting for an IP");
      break;
    default:
      break;
  }
}

static char activeSsid[33] = "";
static char activePass[65] = "";

/** List what the ESP32 can actually see. Catches typos, case and range. */
static void scanAndReport() {
  Serial.println("[net] scanning for nearby networks...");
  const int found = WiFi.scanNetworks();
  if (found <= 0) {
    Serial.println("[net] scan found nothing — check the antenna");
    return;
  }

  const char *targetSsid = (activeSsid[0] != '\0') ? activeSsid : WIFI_SSID;
  bool sawTarget = false;
  for (int i = 0; i < found && i < 20; ++i) {
    const String ssid = WiFi.SSID(i);
    const bool match = (ssid == targetSsid);
    if (match) sawTarget = true;
    Serial.printf("[net]   %-32s %4d dBm  ch%-3d %s%s\n", ssid.c_str(),
                  WiFi.RSSI(i), WiFi.channel(i),
                  WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "open" : "secured",
                  match ? "   <== configured SSID" : "");
  }

  if (!sawTarget) {
    Serial.printf(
        "[net] *** '%s' is NOT in the scan. The name must match exactly,\n"
        "[net]     including case. Hidden networks will not appear here.\n",
        targetSsid);
  } else {
    Serial.printf(
        "[net] '%s' IS visible, so the SSID is right. A failure now points at\n"
        "[net]     the password (see the reason code above).\n",
        targetSsid);
  }
  WiFi.scanDelete();
}

static WebSocketsClient socket;

static bool socketUp = false;
static bool linkedOnce = false;
static bool wifiWasUp = false;
static bool ntpStarted = false;
static bool socketConfigured = false;

static uint64_t lastWifiAttemptMs = 0;
static uint32_t wifiAttempts = 0;
static uint64_t lastHeartbeatMs = 0;
static uint64_t lastInboundMs = 0;
static bool snapshotPending = false;

static char ipBuffer[16] = "0.0.0.0";

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //

static uint8_t daysMaskFromJson(JsonArrayConst days) {
  uint8_t mask = 0;
  for (JsonVariantConst day : days) {
    int index = day.as<int>();
    if (index >= 0 && index <= 6) mask |= static_cast<uint8_t>(1u << index);
  }
  return mask;
}

static void sendFrame(const char *type, JsonDocument &payload) {
  if (!socketUp) return;
  JsonDocument frame;
  frame["type"] = type;
  frame["payload"] = payload.as<JsonObjectConst>();
  String out;
  serializeJson(frame, out);
  socket.sendTXT(out);
}

static void sendFrame(const char *type) {
  JsonDocument empty;
  empty.to<JsonObject>();
  sendFrame(type, empty);
}

// --------------------------------------------------------------------------- //
// Telemetry
// --------------------------------------------------------------------------- //

static int readBatteryPercent(float &voltsOut) {
#if BATTERY_SENSE_ENABLED
  // ADC1 only: ADC2 is unavailable while the Wi-Fi radio is active.
  uint32_t total = 0;
  for (uint8_t i = 0; i < 8; ++i) total += analogReadMilliVolts(PIN_BATTERY_SENSE);
  float millivolts = (static_cast<float>(total) / 8.0f) * BATTERY_DIVIDER_RATIO;
  voltsOut = millivolts / 1000.0f;
  float span = static_cast<float>(BATTERY_FULL_MV - BATTERY_EMPTY_MV);
  int percent = static_cast<int>((millivolts - BATTERY_EMPTY_MV) * 100.0f / span);
  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;
  return percent;
#else
  (void)voltsOut;
  return -1;  // no divider fitted; running on USB
#endif
}

static void sendHeartbeat() {
  if (!socketUp) return;

  JsonDocument payload;
  JsonObject root = payload.to<JsonObject>();
  root["firmware_version"] = FIRMWARE_VERSION;
  root["wifi_connected"] = WiFi.status() == WL_CONNECTED;
  root["wifi_ssid"] = WiFi.SSID();
  root["wifi_rssi"] = WiFi.RSSI();
  root["ip_address"] = ipBuffer;
  root["free_heap_bytes"] = ESP.getFreeHeap();
  root["uptime_seconds"] = static_cast<uint32_t>(clocktime::monotonicMs() / 1000ULL);
  root["relay_on"] = relay::isOn();
  root["current_screen"] = screens::currentName();

  float volts = 0.0f;
  int percent = readBatteryPercent(volts);
  if (percent >= 0) {
    root["battery_percent"] = percent;
    root["battery_voltage"] = volts;
  }

  sendFrame("device.heartbeat", payload);
  lastHeartbeatMs = clocktime::monotonicMs();
}

// --------------------------------------------------------------------------- //
// Outbound: drain the local event bus
// --------------------------------------------------------------------------- //

static void publish(bus::Event event) {
  if (!socketUp) return;

  JsonDocument payload;
  JsonObject root = payload.to<JsonObject>();

  switch (event) {
    case bus::Event::TimerStarted: {
      // Send the time *remaining*, not the original duration. If this event is
      // being flushed a moment after the fact, remaining is what makes both
      // sides land on the same finish instant.
      root["duration_seconds"] = timerService::remainingSeconds();
      root["label"] = timerService::label();
      sendFrame("timer.start", payload);
      return;
    }
    case bus::Event::TimerPaused: sendFrame("timer.pause"); return;
    case bus::Event::TimerResumed: sendFrame("timer.resume"); return;
    case bus::Event::TimerCancelled: sendFrame("timer.cancel"); return;

    case bus::Event::TimerFinished:
      // Deliberately silent. The backend holds the same absolute deadline and
      // its own scheduler fires it. Publishing here would double-notify every
      // dashboard.
      return;

    case bus::Event::StopwatchStarted: sendFrame("stopwatch.start"); return;
    case bus::Event::StopwatchStopped: sendFrame("stopwatch.stop"); return;
    case bus::Event::StopwatchLapped: sendFrame("stopwatch.lap"); return;
    case bus::Event::StopwatchReset: sendFrame("stopwatch.reset"); return;

    case bus::Event::PomodoroStarted: {
      root["focus_minutes"] = pomodoroService::focusMinutes();
      root["short_break_minutes"] = pomodoroService::shortBreakMinutes();
      root["long_break_minutes"] = pomodoroService::longBreakMinutes();
      root["cycles_before_long_break"] = pomodoroService::cyclesPerLongBreak();
      sendFrame("pomodoro.start", payload);
      return;
    }
    case bus::Event::PomodoroPaused: sendFrame("pomodoro.pause"); return;
    case bus::Event::PomodoroResumed: sendFrame("pomodoro.resume"); return;
    case bus::Event::PomodoroStopped: sendFrame("pomodoro.stop"); return;
    case bus::Event::PomodoroSkipped: sendFrame("pomodoro.skip"); return;

    case bus::Event::PomodoroPhaseChanged:
      // Same reasoning as TimerFinished: the backend advances its own phase.
      return;

    case bus::Event::RelaySet: {
      root["on"] = relay::isOn();
      sendFrame("relay.set", payload);
      return;
    }
    case bus::Event::ScreenChanged: {
      root["screen"] = screens::currentName();
      sendFrame("screen.changed", payload);
      return;
    }
    case bus::Event::Touch: {
      root["gesture"] = "tap";
      sendFrame("touch", payload);
      return;
    }
    case bus::Event::AlarmTriggered:
      // Alarms exist on both sides and each evaluates the same definition, so
      // the backend has already told the dashboard.
      return;

    default:
      return;
  }
}

static void drainBus() {
  bus::Event event;
  uint8_t budget = 8;  // bound the work done in a single loop pass
  while (budget-- > 0 && bus::nextForNet(event)) {
    if (socketUp) {
      publish(event);
    }
    // When the socket is down the event is simply dropped. State is recovered
    // wholesale from GET /api/snapshot on reconnect, so there is nothing to
    // queue and nothing to replay incorrectly.
  }
}

// --------------------------------------------------------------------------- //
// Inbound
// --------------------------------------------------------------------------- //

static void applyTimer(JsonObjectConst payload) {
  RunState state = runStateFromName(payload["state"] | "idle");
  uint32_t duration = payload["duration_seconds"] | 0;
  uint32_t remaining = payload["remaining_seconds"] | 0;
  const char *label = payload["label"] | "Timer";
  uint64_t endsAt = clocktime::parseIso8601(payload["ends_at"] | "");
  timerService::applyRemote(state, duration, endsAt, remaining, label);
}

static void applyStopwatch(JsonObjectConst payload) {
  RunState state = runStateFromName(payload["state"] | "idle");
  uint64_t accumulated = payload["accumulated_ms"] | 0ULL;
  uint64_t startedAt = clocktime::parseIso8601(payload["started_at"] | "");
  stopwatchService::applyRemote(state, accumulated, startedAt);
}

static void applyPomodoro(JsonObjectConst payload) {
  PomodoroPhase phase = pomodoroPhaseFromName(payload["phase"] | "idle");
  RunState state = runStateFromName(payload["state"] | "idle");
  uint64_t endsAt = clocktime::parseIso8601(payload["ends_at"] | "");
  uint32_t remaining = payload["remaining_seconds"] | 0;
  uint8_t cycles = payload["completed_focus_cycles"] | 0;
  pomodoroService::applyRemote(phase, state, endsAt, remaining, cycles,
                               payload["focus_minutes"] | 0,
                               payload["short_break_minutes"] | 0,
                               payload["long_break_minutes"] | 0,
                               payload["cycles_before_long_break"] | 0);
}

static void applySettings(JsonObjectConst values) {
  if (values["oled_brightness"].is<int>()) {
    int level = values["oled_brightness"].as<int>();
    if (level >= 10 && level <= 255) display::setBrightness(static_cast<uint8_t>(level));
  }
  if (values["speaker_volume"].is<int>()) {
    int level = values["speaker_volume"].as<int>();
    if (level >= 0 && level <= 10) chime::setVolume(static_cast<uint8_t>(level));
  }
}

static void applyAlarm(JsonObjectConst payload) {
  const char *id = payload["id"] | "";
  if (*id == '\0') return;
  uint8_t hour = 7;
  uint8_t minute = 0;
  const char *timeOfDay = payload["time_of_day"] | "07:00";
  int parsedHour = 0;
  int parsedMinute = 0;
  if (sscanf(timeOfDay, "%2d:%2d", &parsedHour, &parsedMinute) == 2) {
    hour = static_cast<uint8_t>(parsedHour);
    minute = static_cast<uint8_t>(parsedMinute);
  }
  alarmService::upsertRemote(id, hour, minute,
                             daysMaskFromJson(payload["days_of_week"].as<JsonArrayConst>()),
                             payload["enabled"] | true, payload["label"] | "Alarm");
  alarmService::flush();
}

static void applyTask(JsonObjectConst payload) {
  const char *id = payload["id"] | "";
  if (*id == '\0') return;
  taskService::upsertRemote(id, payload["title"] | "Task", payload["done"] | false);
}

static void applyReminder(JsonObjectConst payload) {
  const char *id = payload["id"] | "";
  if (*id == '\0') return;
  uint64_t remindAt = clocktime::parseIso8601(payload["remind_at"] | "");
  reminderService::upsertRemote(id, payload["text"] | "Reminder", remindAt);
}

static void handleFrame(const char *text, size_t length) {
  lastInboundMs = clocktime::monotonicMs();

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, text, length);
  if (error) {
    Serial.printf("[net] bad frame: %s\n", error.c_str());
    return;
  }

  const char *type = doc["type"] | "";
  JsonObjectConst payload = doc["payload"].as<JsonObjectConst>();

  // Log every inbound state change. Without this the whole sync path is
  // invisible from the serial monitor, which makes bring-up guesswork — you
  // cannot tell "the dashboard never sent it" from "the device ignored it".
  // Heartbeat echoes and keepalives are skipped; they would drown everything.
  if (strcmp(type, "device.status") != 0 && strcmp(type, "pong") != 0 &&
      strcmp(type, "ping") != 0) {
    Serial.printf("[net] <- %s (from %s)\n", type, doc["origin"] | "?");
  }

  if (strcmp(type, "hello") == 0) {
    linkedOnce = true;
    Serial.println("[net] backend said hello");
    // No snapshot request here: WStype_CONNECTED already queued one and always
    // fires first, so doing it again just means two HTTP GETs per connect.
    return;
  }

  if (strcmp(type, "ping") == 0) {
    sendFrame("pong");
    return;
  }
  if (strcmp(type, "pong") == 0 || strcmp(type, "ack") == 0) return;

  if (strcmp(type, "error") == 0) {
    Serial.printf("[net] backend error: %s\n", payload["detail"] | "?");
    return;
  }

  // --- timer ---
  if (strncmp(type, "timer.", 6) == 0) {
    applyTimer(payload);
    if (strcmp(type, "timer.started") == 0 || strcmp(type, "timer.resumed") == 0) {
      screens::dismissNotice();
      screens::show(screens::Screen::Timer);
    } else if (strcmp(type, "timer.finished") == 0) {
      chime::playTimerDone();
      screens::showNotice("TIMER DONE", payload["label"] | "", NOTICE_DURATION_MS);
      screens::show(screens::Screen::Timer);
    }
    return;
  }

  // --- stopwatch ---
  if (strncmp(type, "stopwatch.", 10) == 0) {
    applyStopwatch(payload);
    if (strcmp(type, "stopwatch.started") == 0) {
      screens::dismissNotice();
      screens::show(screens::Screen::Stopwatch);
    }
    return;
  }

  // --- pomodoro ---
  if (strncmp(type, "pomodoro.", 9) == 0) {
    applyPomodoro(payload);
    if (strcmp(type, "pomodoro.started") == 0 || strcmp(type, "pomodoro.resumed") == 0) {
      screens::dismissNotice();
      screens::show(screens::Screen::Pomodoro);
    } else if (strcmp(type, "pomodoro.phase_changed") == 0) {
      bool focus = pomodoroService::phase() == PomodoroPhase::Focus;
      if (focus) {
        chime::playPomodoroFocus();
        screens::showNotice("FOCUS", "break over", NOTICE_DURATION_MS);
      } else {
        chime::playPomodoroBreak();
        screens::showNotice("BREAK", "focus block done", NOTICE_DURATION_MS);
      }
      screens::show(screens::Screen::Pomodoro);
    }
    return;
  }

  // --- relay / screen ---
  if (strcmp(type, "relay.set") == 0) {
    relay::applyRemote(payload["on"] | false);
    screens::dismissNotice();
    screens::show(screens::Screen::Relay);
    return;
  }
  if (strcmp(type, "screen.changed") == 0) {
    screens::showByName(payload["screen"] | "home");
    return;
  }

  // --- alarms ---
  if (strcmp(type, "alarm.created") == 0 || strcmp(type, "alarm.updated") == 0) {
    applyAlarm(payload);
    screens::dismissNotice();
    screens::show(screens::Screen::Alarms);
    return;
  }
  if (strcmp(type, "alarm.deleted") == 0) {
    if (alarmService::removeByRemoteId(payload["id"] | "")) alarmService::flush();
    return;
  }
  if (strcmp(type, "alarm.triggered") == 0) {
    // The device rings its own copy from NVS. Only react to the backend's
    // version if our local evaluation did not already catch it — otherwise a
    // clock a second apart would chime twice.
    if (!alarmService::isRinging()) {
      if (!alarmService::triggerRemote(payload["id"] | "")) {
        // Fallback if the device doesn't have the alarm locally
        chime::playAlarmLoop();
        screens::showNotice("ALARM", payload["label"] | "", NOTICE_DURATION_MS);
      }
    }
    return;
  }

  // --- reminders are backend-only; the device just announces them ---
  if (strcmp(type, "reminder.due") == 0) {
    chime::playConfirm();
    screens::showNotice("REMINDER", payload["text"] | "", NOTICE_DURATION_MS);
    return;
  }
  if (strcmp(type, "reminder.created") == 0 || strcmp(type, "reminder.updated") == 0) {
    applyReminder(payload);
    screens::dismissNotice();
    screens::show(screens::Screen::Reminders);
    return;
  }
  if (strcmp(type, "reminder.deleted") == 0) {
    reminderService::removeByRemoteId(payload["id"] | "");
    return;
  }

  // --- tasks ---
  if (strcmp(type, "task.created") == 0 || strcmp(type, "task.updated") == 0) {
    applyTask(payload);
    screens::dismissNotice();
    screens::show(screens::Screen::Tasks);
    return;
  }
  if (strcmp(type, "task.deleted") == 0) {
    taskService::removeByRemoteId(payload["id"] | "");
    return;
  }
  
  // --- weather ---
  if (strcmp(type, "weather.updated") == 0) {
    weatherService::update(payload["short"] | "", payload["temperature"] | 0.0f);
    return;
  }

  if (strcmp(type, "settings.updated") == 0) {
    applySettings(payload["values"].as<JsonObjectConst>());
    return;
  }

  // --- Wi-Fi credentials set from dashboard/database ---
  if (strcmp(type, "device.wifi_set") == 0) {
    const char *newSsid = payload["ssid"] | "";
    const char *newPass = payload["password"] | "";
    if (newSsid[0] != '\0') {
      applyWifiCredentials(newSsid, newPass);
    }
    return;
  }

  if (strcmp(type, "speak") == 0 || strcmp(type, "voice.reply") == 0) {
    const char *text = (strcmp(type, "speak") == 0) ? (payload["text"] | "") : (payload["reply"] | "");
    const char *intent = payload["intent"] | "";

    if (text[0] != '\0') {
      if (strncmp(intent, "timer.", 6) == 0) {
        screens::dismissNotice();
        screens::show(screens::Screen::Timer);
      } else if (strncmp(intent, "pomodoro.", 9) == 0) {
        screens::dismissNotice();
        screens::show(screens::Screen::Pomodoro);
      } else if (strncmp(intent, "alarm.", 6) == 0) {
        screens::dismissNotice();
        screens::show(screens::Screen::Alarms);
      } else if (strncmp(intent, "stopwatch.", 10) == 0) {
        screens::dismissNotice();
        screens::show(screens::Screen::Stopwatch);
      } else if (strncmp(intent, "relay.", 6) == 0) {
        screens::dismissNotice();
        screens::show(screens::Screen::Relay);
      } else {
        screens::showNotice("DESKMATE", text, NOTICE_DURATION_MS);
      }
      const bool isQuiz = (strcmp(intent, "notes.quiz") == 0);
      voice::speak(text, isQuiz);
    }
    return;
  }
}

// --------------------------------------------------------------------------- //
// Voice upload
// --------------------------------------------------------------------------- //

VoiceResult postVoice(const uint8_t *body, size_t length, const char *boundary) {
  VoiceResult result = {};
  result.ok = false;
  result.httpStatus = 0;

  const uint64_t started = clocktime::monotonicMs();

  if (body == nullptr || length == 0) {
    strlcpy(result.reply, "Nothing was recorded", sizeof(result.reply));
    return result;
  }
  if (WiFi.status() != WL_CONNECTED) {
    strlcpy(result.reply, "No Wi-Fi", sizeof(result.reply));
    return result;
  }

  char url[200];
  // speak=false: the reply comes back in this response, and letting the server
  // also push a `speak` frame would show the same notice twice.
  snprintf(url, sizeof(url),
           "http://%s:%u/api/voice/transcribe?device_id=%s&speak=false",
           BACKEND_HOST, static_cast<unsigned>(BACKEND_PORT), DEVICE_ID);

  HTTPClient http;
  // Generous: Whisper plus an LLM fallback is the slowest thing the device waits
  // on, and timing out early would throw away a request that was about to land.
  http.setTimeout(20000);
  if (!http.begin(url)) {
    strlcpy(result.reply, "Could not reach backend", sizeof(result.reply));
    return result;
  }
  if (strlen(DEVICE_TOKEN) > 0) http.addHeader("X-Device-Token", DEVICE_TOKEN);

  char contentType[96];
  snprintf(contentType, sizeof(contentType),
           "multipart/form-data; boundary=%s", boundary);
  http.addHeader("Content-Type", contentType);

  Serial.printf("[voice] uploading %u bytes\n", static_cast<unsigned>(length));
  // const_cast: HTTPClient's signature is non-const but it only reads the buffer.
  const int status = http.POST(const_cast<uint8_t *>(body), length);
  result.httpStatus = status;

  if (status != 200) {
    Serial.printf("[voice] HTTP %d\n", status);
    if (status > 0) {
      // The backend puts a readable explanation in `detail`; worth surfacing on
      // the panel rather than showing a bare status code.
      JsonDocument error;
      if (deserializeJson(error, http.getStream()) == DeserializationError::Ok) {
        strlcpy(result.reply, error["detail"] | "Transcription failed",
                sizeof(result.reply));
      } else {
        snprintf(result.reply, sizeof(result.reply), "Backend error %d", status);
      }
    } else {
      snprintf(result.reply, sizeof(result.reply), "Upload failed (%d)", status);
    }
    http.end();
    result.elapsedMs = static_cast<uint32_t>(clocktime::monotonicMs() - started);
    return result;
  }

  // Filtered parse: the response also carries timings and entities the panel has
  // no room for.
  JsonDocument filter;
  filter["transcript"] = true;
  filter["reply"] = true;
  filter["intent"] = true;
  filter["action_taken"] = true;

  JsonDocument doc;
  const DeserializationError error =
      deserializeJson(doc, http.getStream(), DeserializationOption::Filter(filter));
  http.end();

  if (error) {
    Serial.printf("[voice] parse failed: %s\n", error.c_str());
    strlcpy(result.reply, "Bad reply from backend", sizeof(result.reply));
    result.elapsedMs = static_cast<uint32_t>(clocktime::monotonicMs() - started);
    return result;
  }

  const char *transcript = doc["transcript"] | "";
  // Whisper returns a leading space on essentially every transcript. Harmless in
  // JSON, but it shows as an off-centre first character on a centred line.
  while (*transcript == ' ') ++transcript;

  strlcpy(result.transcript, transcript, sizeof(result.transcript));
  strlcpy(result.reply, doc["reply"] | "", sizeof(result.reply));
  strlcpy(result.intent, doc["intent"] | "", sizeof(result.intent));
  strlcpy(result.action, doc["action_taken"] | "", sizeof(result.action));
  result.ok = true;
  result.elapsedMs = static_cast<uint32_t>(clocktime::monotonicMs() - started);

  Serial.printf("[voice] heard \"%s\" -> intent %s (%lu ms)\n", result.transcript,
                result.intent[0] != '\0' ? result.intent : "(llm)",
                static_cast<unsigned long>(result.elapsedMs));
  if (result.action[0] != '\0') Serial.printf("[voice] did: %s\n", result.action);
  return result;
}

// --------------------------------------------------------------------------- //
// TTS download
// --------------------------------------------------------------------------- //

SpeechResult fetchSpeech(const char *text) {
  SpeechResult result = {};
  result.ok = false;

  if (text == nullptr || *text == '\0') return result;
  if (WiFi.status() != WL_CONNECTED) return result;

  const uint64_t started = clocktime::monotonicMs();

  // URL-encode is overkill for a query param the backend parses; just POST the
  // text. But HTTPClient.POST() is simpler for a multipart, and the endpoint
  // accepts a query param, so we just put it in the URL. We need to be careful
  // with special chars though — for now, POST with the text in the query.
  // The backend accepts: POST /api/voice/speak?text=<text>
  // We'll URL-encode minimally.

  char url[256];
  snprintf(url, sizeof(url), "http://%s:%u/api/voice/speak",
           BACKEND_HOST, static_cast<unsigned>(BACKEND_PORT));

  HTTPClient http;
  http.setTimeout(15000);  // TTS can take a few seconds
  if (!http.begin(url)) {
    Serial.println("[tts] HTTP begin failed");
    return result;
  }
  http.addHeader("Content-Type", "text/plain; charset=utf-8");
  if (strlen(DEVICE_TOKEN) > 0) http.addHeader("X-Device-Token", DEVICE_TOKEN);

  Serial.printf("[tts] requesting speech for: %.40s...\n", text);
  int status = http.POST(reinterpret_cast<uint8_t *>(const_cast<char *>(text)), strlen(text));

  if (status != 200) {
    Serial.printf("[tts] HTTP %d\n", status);
    http.end();
    result.elapsedMs = static_cast<uint32_t>(clocktime::monotonicMs() - started);
    return result;
  }

  int contentLength = http.getSize();
  if (contentLength <= 44) {
    Serial.printf("[tts] response too small: %d bytes\n", contentLength);
    http.end();
    result.elapsedMs = static_cast<uint32_t>(clocktime::monotonicMs() - started);
    return result;
  }

  // Allocate PSRAM for the entire WAV
  uint8_t *wavBuf = static_cast<uint8_t *>(ps_malloc(contentLength));
  if (wavBuf == nullptr) {
    Serial.printf("[tts] PSRAM alloc failed for %d bytes\n", contentLength);
    http.end();
    result.elapsedMs = static_cast<uint32_t>(clocktime::monotonicMs() - started);
    return result;
  }

  // Read the entire response
  WiFiClient *stream = http.getStreamPtr();
  size_t totalRead = 0;
  while (totalRead < static_cast<size_t>(contentLength)) {
    if (!stream->connected() && !stream->available()) break;
    int avail = stream->available();
    if (avail <= 0) {
      delay(1);
      continue;
    }
    int toRead = avail;
    if (totalRead + toRead > static_cast<size_t>(contentLength)) {
      toRead = contentLength - totalRead;
    }
    int bytesRead = stream->readBytes(wavBuf + totalRead, toRead);
    if (bytesRead <= 0) break;
    totalRead += bytesRead;
  }
  http.end();

  if (totalRead < 44) {
    Serial.printf("[tts] incomplete download: %u bytes\n", static_cast<unsigned>(totalRead));
    free(wavBuf);
    result.elapsedMs = static_cast<uint32_t>(clocktime::monotonicMs() - started);
    return result;
  }

  // Skip the 44-byte WAV header → raw 16-bit PCM starts at byte 44
  size_t pcmBytes = totalRead - 44;
  size_t sampleCount = pcmBytes / sizeof(int16_t);

  // Move PCM data to the front and realloc (or just point past the header).
  // Since ps_malloc can't realloc easily, we'll just offset the pointer.
  // The caller will free the original allocation.
  result.pcm = reinterpret_cast<int16_t *>(wavBuf + 44);
  result.sampleCount = sampleCount;
  result.ok = true;
  result.elapsedMs = static_cast<uint32_t>(clocktime::monotonicMs() - started);

  float durationSec = static_cast<float>(sampleCount) / AUDIO_SAMPLE_RATE;
  Serial.printf("[tts] downloaded %.1f s of audio (%u bytes) in %lu ms\n",
                durationSec, static_cast<unsigned>(totalRead),
                static_cast<unsigned long>(result.elapsedMs));

  return result;
}

// --------------------------------------------------------------------------- //
// Snapshot adoption
// --------------------------------------------------------------------------- //

void requestSnapshot() { snapshotPending = true; }

static void fetchSnapshot() {
  if (WiFi.status() != WL_CONNECTED) return;
  char url[256];
  snprintf(url, sizeof(url), "http://%s:%u/api/snapshot?device_id=%s&range_days=1&tasks_limit=10&reminders_limit=10",
           BACKEND_HOST, static_cast<unsigned>(BACKEND_PORT), DEVICE_ID);

  HTTPClient http;
  http.setTimeout(SNAPSHOT_TIMEOUT_MS);
  if (!http.begin(url)) {
    Serial.println("[net] snapshot: begin failed");
    return;
  }
  if (strlen(DEVICE_TOKEN) > 0) http.addHeader("X-Device-Token", DEVICE_TOKEN);

  int status = http.GET();
  if (status != 200) {
    Serial.printf("[net] snapshot HTTP %d\n", status);
    http.end();
    return;
  }

  // The snapshot also carries analytics, which the OLED doesn't show.
  // Filtering during parse keeps this to a few kB instead of
  // deserialising the whole document into RAM.
  JsonDocument filter;
  filter["server_time"] = true;
  filter["device"]["relay_on"] = true;
  filter["device"]["current_screen"] = true;
  filter["timer"] = true;
  filter["stopwatch"] = true;
  filter["pomodoro"] = true;
  filter["weather"]["short"] = true;
  filter["weather"]["temperature"] = true;
  filter["alarms"] = true;
  filter["settings"] = true;
  filter["tasks"] = true;
  filter["reminders"] = true;

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, http.getStream(),
                                               DeserializationOption::Filter(filter));
  http.end();

  if (error) {
    Serial.printf("[net] snapshot parse failed: %s\n", error.c_str());
    return;
  }

  // Policy: on (re)connect the backend is authoritative. It survives device
  // reboots and is shared with the dashboard and the phone.
  JsonObjectConst timer = doc["timer"].as<JsonObjectConst>();
  bool backendHasTimer = !timer.isNull();
  if (backendHasTimer) {
    applyTimer(timer);
  } else if (timerService::state() == RunState::Running ||
             timerService::state() == RunState::Paused) {
    // One exception: a timer started on the device while offline would otherwise
    // vanish. Push it up instead of losing it.
    publish(bus::Event::TimerStarted);
  }

  if (!doc["stopwatch"].isNull()) applyStopwatch(doc["stopwatch"].as<JsonObjectConst>());
  if (!doc["pomodoro"].isNull()) applyPomodoro(doc["pomodoro"].as<JsonObjectConst>());

  if (!doc["weather"].isNull()) {
    JsonObjectConst w = doc["weather"].as<JsonObjectConst>();
    weatherService::update(w["short"] | "", w["temperature"] | 0.0f);
  } else {
    weatherService::begin(); // clear it
  }

  JsonObjectConst device = doc["device"].as<JsonObjectConst>();
  if (!device.isNull() && device["relay_on"].is<bool>()) {
    relay::applyRemote(device["relay_on"].as<bool>());
  }

  JsonArrayConst alarms = doc["alarms"].as<JsonArrayConst>();
  if (!alarms.isNull()) {
    alarmService::clearRemote();
    for (JsonObjectConst alarm : alarms) applyAlarm(alarm);
    alarmService::flush();
  }

  JsonArrayConst tasks = doc["tasks"].as<JsonArrayConst>();
  if (!tasks.isNull()) {
    taskService::clearRemote();
    for (JsonObjectConst task : tasks) applyTask(task);
  }

  JsonArrayConst reminders = doc["reminders"].as<JsonArrayConst>();
  if (!reminders.isNull()) {
    reminderService::clearRemote();
    for (JsonObjectConst reminder : reminders) applyReminder(reminder);
  }

  if (!doc["settings"].isNull()) applySettings(doc["settings"].as<JsonObjectConst>());

  // Report what was actually adopted. "snapshot adopted" on its own does not tell
  // you whether the alarms made it into NVS, which is the thing most likely to
  // be silently empty.
  Serial.printf("[net] snapshot adopted: timer=%s alarms=%u relay=%s\n",
                backendHasTimer ? (timer["state"] | "?") : "none",
                alarmService::count(), relay::isOn() ? "on" : "off");
}

// --------------------------------------------------------------------------- //
// Socket lifecycle
// --------------------------------------------------------------------------- //

static void onSocketEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      socketUp = true;
      linkedOnce = true;
      lastInboundMs = clocktime::monotonicMs();
      Serial.println("[net] websocket connected");
      sendHeartbeat();
      snapshotPending = true;
      break;

    case WStype_DISCONNECTED:
      if (socketUp) Serial.println("[net] websocket disconnected");
      socketUp = false;
      break;

    case WStype_TEXT:
      handleFrame(reinterpret_cast<const char *>(payload), length);
      break;

    case WStype_ERROR:
      Serial.println("[net] websocket error");
      break;

    default:
      break;
  }
}

static void openSocket() {
  char path[192];
  if (strlen(DEVICE_TOKEN) > 0) {
    snprintf(path, sizeof(path), "/ws?role=device&device_id=%s&token=%s", DEVICE_ID,
             DEVICE_TOKEN);
  } else {
    snprintf(path, sizeof(path), "/ws?role=device&device_id=%s", DEVICE_ID);
  }

  socket.begin(BACKEND_HOST, BACKEND_PORT, path);
  socket.onEvent(onSocketEvent);
  socket.setReconnectInterval(WS_RECONNECT_INTERVAL_MS);
  // Protocol-level ping. Detects a half-open socket, which is the failure mode
  // you get when the backend host sleeps or the AP drops the session silently.
  socket.enableHeartbeat(15000, 4000, 2);
  socketConfigured = true;
  Serial.printf("[net] websocket -> ws://%s:%u%s\n", BACKEND_HOST,
                static_cast<unsigned>(BACKEND_PORT), path);
}

// --------------------------------------------------------------------------- //
// Public
// --------------------------------------------------------------------------- //

void begin() {
  Preferences prefs;
  prefs.begin("deskmate", true);
  String nvsSsid = prefs.getString("wifi_ssid", "");
  String nvsPass = prefs.getString("wifi_pass", "");
  prefs.end();

  if (nvsSsid.length() > 0) {
    strlcpy(activeSsid, nvsSsid.c_str(), sizeof(activeSsid));
    strlcpy(activePass, nvsPass.c_str(), sizeof(activePass));
    Serial.printf("[net] Loaded Wi-Fi SSID '%s' from NVS flash\n", activeSsid);
  } else {
    strlcpy(activeSsid, WIFI_SSID, sizeof(activeSsid));
    strlcpy(activePass, WIFI_PASSWORD, sizeof(activePass));
  }

  if (strcmp(activeSsid, "CHANGE_ME") == 0 || strlen(activeSsid) == 0) {
    Serial.println("[net] Wi-Fi credentials not set (secrets.h or NVS) — "
                   "running offline. Local features are unaffected.");
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setHostname("deskmate");
  WiFi.onEvent(onWifiEvent);
  WiFi.setAutoReconnect(true);
  // Do NOT disable Wi-Fi sleep (WiFi.setSleep(false)) when Bluetooth coexistence is enabled,
  // as the ESP32-S3 radio arbiter requires modem sleep for Wi-Fi + BLE coexistence.
  WiFi.setSleep(true);
  WiFi.begin(activeSsid, activePass);
  lastWifiAttemptMs = clocktime::monotonicMs();
  Serial.printf("[net] connecting to '%s' (%u char password)\n", activeSsid,
                static_cast<unsigned>(strlen(activePass)));
}

void update() {
  const uint64_t now = clocktime::monotonicMs();
  const bool wifiUp = WiFi.status() == WL_CONNECTED;

  // --- Wi-Fi state transitions ---
  if (wifiUp && !wifiWasUp) {
    strlcpy(ipBuffer, WiFi.localIP().toString().c_str(), sizeof(ipBuffer));
    Serial.printf("[net] Wi-Fi up, IP %s, RSSI %ld\n", ipBuffer,
                  static_cast<long>(WiFi.RSSI()));
    if (!ntpStarted) {
      clocktime::beginNtp();
      ntpStarted = true;
    }
    if (!socketConfigured) openSocket();
  } else if (!wifiUp && wifiWasUp) {
    Serial.println("[net] Wi-Fi down");
    socketUp = false;
  }
  wifiWasUp = wifiUp;

  // --- retry a dead Wi-Fi link ---
  if (!wifiUp && strcmp(activeSsid, "CHANGE_ME") != 0 && strlen(activeSsid) > 0 &&
      (now - lastWifiAttemptMs) > WIFI_RETRY_INTERVAL_MS) {
    lastWifiAttemptMs = now;
    ++wifiAttempts;

    // Scan once, on the second failure. Doing it on the first would delay a
    // connection that was merely slow; never doing it leaves you guessing.
    if (wifiAttempts == 2) {
      scanAndReport();
    }

    Serial.printf("[net] retrying '%s' (attempt %lu, status %d)\n", activeSsid,
                  static_cast<unsigned long>(wifiAttempts),
                  static_cast<int>(WiFi.status()));
    WiFi.disconnect();
    WiFi.begin(activeSsid, activePass);
  }

  if (socketConfigured) socket.loop();

  if (socketUp && (now - lastHeartbeatMs) > HEARTBEAT_INTERVAL_MS) {
    sendHeartbeat();
  }

  // Snapshot fetch is blocking HTTP, so it is deferred out of the socket
  // callback and run here, once, between frames.
  if (snapshotPending && wifiUp) {
    snapshotPending = false;
    fetchSnapshot();
  }

  drainBus();
}

bool wifiConnected() { return WiFi.status() == WL_CONNECTED; }
bool socketConnected() { return socketUp; }
bool everConnected() { return linkedOnce; }
int32_t rssi() { return WiFi.RSSI(); }
int32_t wifiRssi() { return WiFi.RSSI(); }
const char *ipAddress() { return ipBuffer; }
uint16_t backendPort() { return BACKEND_PORT; }
const char *backendHost() { return BACKEND_HOST; }

const char *ssid() {
  static char buffer[33];
  strlcpy(buffer, WiFi.SSID().c_str(), sizeof(buffer));
  return buffer;
}

uint32_t sinceLastInboundMs() {
  if (lastInboundMs == 0) return 0;
  return static_cast<uint32_t>(clocktime::monotonicMs() - lastInboundMs);
}

void forceReconnect() {
  Serial.println("[net] manual reconnect");
  socketUp = false;
  if (socketConfigured) socket.disconnect();
  WiFi.disconnect();
  WiFi.begin(activeSsid, activePass);
  lastWifiAttemptMs = clocktime::monotonicMs();
  if (socketConfigured) {
    socket.setReconnectInterval(WS_RECONNECT_INTERVAL_MS);
  }
}

void applyWifiCredentials(const char *newSsid, const char *newPass) {
  if (newSsid == nullptr || newSsid[0] == '\0') return;

  Preferences prefs;
  if (prefs.begin("deskmate", false)) {
    prefs.putString("wifi_ssid", newSsid);
    prefs.putString("wifi_pass", newPass ? newPass : "");
    prefs.end();
    Serial.printf("[net] Saved new Wi-Fi credentials to NVS for '%s'\n", newSsid);
  }

  strlcpy(activeSsid, newSsid, sizeof(activeSsid));
  strlcpy(activePass, newPass ? newPass : "", sizeof(activePass));

  screens::showNotice("WI-FI SET", newSsid, NOTICE_DURATION_MS);
  WiFi.disconnect();
  WiFi.begin(activeSsid, activePass);
  lastWifiAttemptMs = clocktime::monotonicMs();
  wifiAttempts = 0;
}

}  // namespace netLink
