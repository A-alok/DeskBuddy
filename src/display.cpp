#include "display.h"

#include <Preferences.h>
#include <Wire.h>

#include "animations.h"
#include "clock_time.h"
#include "config.h"
#include "net_link.h"

namespace display {

// Full-buffer mode ("_F_"): one 1 KB frame buffer, drawn in one transaction.
// Page mode would save RAM we do not need to save and makes partial updates
// awkward. Clock and data pins are passed to the constructor so U8g2 configures
// Wire itself with the right pins on ESP32.
static U8G2_SH1106_128X64_NONAME_F_HW_I2C panel(U8G2_R0, U8X8_PIN_NONE,
                                                PIN_I2C_SCL, PIN_I2C_SDA);

static uint64_t lastActivityMs = 0;
static bool awake = true;
static bool dimmed = false;
static bool panelPresent = false;
static uint8_t brightnessValue = 180;
static Preferences prefs;

U8G2 &gfx() { return panel; }
bool present() { return panelPresent; }

/**
 * Is the bus electrically sane?
 *
 * A peripheral holding SDA low, or a short, leaves the ESP32's I2C peripheral
 * waiting for the bus to go idle — and `Wire.begin()` can block there forever.
 * That is a hang with no output, which is the worst kind to debug. Reading the
 * pins directly first costs nothing and turns it into a log line.
 */
static bool busIdle() {
  pinMode(PIN_I2C_SDA, INPUT_PULLUP);
  pinMode(PIN_I2C_SCL, INPUT_PULLUP);
  delay(5);
  const bool sda = digitalRead(PIN_I2C_SDA) == HIGH;
  const bool scl = digitalRead(PIN_I2C_SCL) == HIGH;
  if (!sda || !scl) {
    Serial.printf("[oled] I2C bus not idle (SDA=%d SCL=%d) — check wiring/pull-ups\n",
                  sda ? 1 : 0, scl ? 1 : 0);
    return false;
  }
  return true;
}

/** Does anything answer at 0x3C? */
static bool probePanel() {
  Wire.beginTransmission(0x3C);
  const uint8_t error = Wire.endTransmission();
  if (error != 0) {
    Serial.printf("[oled] no device at 0x3C (I2C error %u)\n", error);
    return false;
  }
  return true;
}

bool begin() {
  Serial.print("[oled] prefs...");
  Serial.flush();
  if (prefs.begin("deskmate", true)) {
    brightnessValue = prefs.getUChar("bright", 180);
    prefs.end();
  }
  if (brightnessValue < 10) brightnessValue = 180;
  Serial.print(" pins...");
  Serial.flush();

  if (!busIdle()) {
    panelPresent = false;
    return false;
  }

  // Probe on our own terms first, so "no panel" is a log line rather than a
  // silent hang inside the library.
  Serial.print(" Wire.begin...");
  Serial.flush();
  const bool wireOk = Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_CLOCK_HZ);
  if (!wireOk) {
    Serial.println(" FAILED");
    panelPresent = false;
    return false;
  }
  // Bound every transaction. Without this a NACKing or absent device can stall
  // the caller for the driver's default timeout on every single write.
  Wire.setTimeOut(50);
  Serial.print(" probe...");
  Serial.flush();

  const bool found = probePanel();

  // Hand the bus back before U8g2 touches it.
  //
  // The U8g2 constructor is given the clock/data pins, which makes its own
  // U8X8_MSG_BYTE_INIT call Wire.begin(sda, scl). Calling Wire.begin() twice on
  // an already-initialised ESP32 I2C peripheral deadlocks inside the driver —
  // that is a hang with no output, and it is what this cost an afternoon to find.
  // Releasing the bus first means exactly one begin() ever runs against it.
  Wire.end();

  if (!found) {
    panelPresent = false;
    return false;
  }

  Serial.print(" u8g2...");
  Serial.flush();
  panel.setI2CAddress(0x3C << 1);  // U8g2 wants the 8-bit form
  if (!panel.begin()) {
    Serial.println(" panel.begin() FAILED");
    panelPresent = false;
    return false;
  }
  // Re-apply: the bus was re-initialised by U8g2 above.
  Wire.setTimeOut(50);
  Serial.println(" ok");

  panel.setBusClock(I2C_CLOCK_HZ);
  panel.setContrast(brightnessValue);
  panel.setPowerSave(0);
  panel.clearBuffer();
  panel.sendBuffer();

  panelPresent = true;
  awake = true;
  dimmed = false;
  lastActivityMs = clocktime::monotonicMs();
  Serial.printf("[oled] SH1106 ready at 0x3C, contrast %u\n", brightnessValue);
  return true;
}

void noteActivity() {
  lastActivityMs = clocktime::monotonicMs();
  if (!awake || dimmed) {
    if (panelPresent) {
      panel.setPowerSave(0);
      panel.setContrast(brightnessValue);
    }
    // Coming back from *blank* is the moment the device opens its eyes, so the
    // face is armed here rather than in wake(): every path that revives the panel
    // — a touch, a notice, a screen pushed from the dashboard — goes through
    // noteActivity(), and all of them should land on the face.
    //
    // A merely dimmed panel is deliberately excluded. It was still showing
    // readable content, and dropping the face over it would hide something the
    // user could already see.
    if (!awake && panelPresent) animations::startFace();
    awake = true;
    dimmed = false;
  }
}

bool wake() {
  // Only a *blanked* panel swallows the gesture that woke it — you cannot act on
  // a screen you could not read. A merely dimmed panel is still legible, so
  // swallowing there just makes the device feel broken: you tap, and nothing
  // happens for no visible reason.
  const bool wasBlanked = !awake;
  noteActivity();
  return wasBlanked;
}

bool isAwake() { return awake; }

void updatePowerSave() {
  if (!panelPresent) return;

  uint64_t idle = clocktime::monotonicMs() - lastActivityMs;

  if (idle > DISPLAY_OFF_AFTER_MS) {
    if (awake) {
      panel.setPowerSave(1);
      awake = false;
    }
    return;
  }

  if (awake && !dimmed && idle > DISPLAY_DIM_AFTER_MS) {
    // Roughly a third of the set brightness, floored so it stays legible.
    uint8_t dim = brightnessValue / 3;
    panel.setContrast(dim < 16 ? 16 : dim);
    dimmed = true;
  }
}

void setBrightness(uint8_t value) {
  brightnessValue = value < 10 ? 10 : value;
  if (prefs.begin("deskmate", false)) {
    prefs.putUChar("bright", brightnessValue);
    prefs.end();
  }
  if (panelPresent && awake && !dimmed) panel.setContrast(brightnessValue);
}

uint8_t brightness() { return brightnessValue; }

uint64_t idleTimeMs() {
  return clocktime::monotonicMs() - lastActivityMs;
}

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //

#include "clock_time.h"

void centerText(const char *text, int16_t y) {
  if (text == nullptr) return;
  int16_t width = panel.getStrWidth(text);
  if (width <= 128) {
    panel.setCursor((128 - width) / 2, y);
    panel.print(text);
  } else {
    // Scroll back and forth
    // Speed: ~30 pixels per second
    uint32_t t = clocktime::monotonicMs();
    int16_t overflow = width - 128;
    int16_t cycle = overflow * 2000 / 30; // ms for a full back-and-forth cycle
    if (cycle == 0) cycle = 1;
    uint32_t phase = t % cycle;
    int16_t offset;
    if (phase < cycle / 2) {
      offset = (phase * overflow) / (cycle / 2);
    } else {
      offset = overflow - ((phase - cycle / 2) * overflow) / (cycle / 2);
    }
    panel.setCursor(-offset, y);
    panel.print(text);
  }
}

void centerTextIn(const char *text, int16_t x, int16_t width, int16_t y) {
  if (text == nullptr) return;
  int16_t textWidth = panel.getStrWidth(text);
  panel.setCursor(x + (width - textWidth) / 2, y);
  panel.print(text);
}

void progressBar(int16_t x, int16_t y, int16_t w, int16_t h, float value) {
  if (value < 0.0f) value = 0.0f;
  if (value > 1.0f) value = 1.0f;
  panel.drawFrame(x, y, w, h);
  int16_t inner = static_cast<int16_t>((w - 2) * value);
  if (inner > 0) panel.drawBox(x + 1, y + 1, inner, h - 2);
}

void statusBar(const char *title) {
  panel.setFont(u8g2_font_4x6_tf);
  panel.setCursor(0, 6);
  panel.print(title);

  // Right side, built right-to-left: clock, then link, then Wi-Fi.
  int16_t x = 128;

  struct tm local {};
  if (clocktime::localTime(local)) {
    char stamp[12];
    snprintf(stamp, sizeof(stamp), "%02d:%02d", local.tm_hour, local.tm_min);
    x -= panel.getStrWidth(stamp);
    panel.setCursor(x, 6);
    panel.print(stamp);
    x -= 4;
  }

  // Filled square = backend socket up, hollow = Wi-Fi only, nothing = offline.
  if (netLink::wifiConnected()) {
    x -= 5;
    if (netLink::socketConnected()) {
      panel.drawBox(x, 1, 4, 4);
    } else {
      panel.drawFrame(x, 1, 4, 4);
    }
  }

  panel.drawHLine(0, 8, 128);
}

void hintBar(const char *hint) {
  if (hint == nullptr) return;
  panel.setFont(u8g2_font_4x6_tf);
  panel.drawHLine(0, 55, 128);
  centerText(hint, 63);
}

void formatClock(uint32_t totalSeconds, char *out, size_t len) {
  uint32_t hours = totalSeconds / 3600;
  uint32_t minutes = (totalSeconds % 3600) / 60;
  uint32_t seconds = totalSeconds % 60;
  if (hours > 0) {
    snprintf(out, len, "%lu:%02lu:%02lu", static_cast<unsigned long>(hours),
             static_cast<unsigned long>(minutes),
             static_cast<unsigned long>(seconds));
  } else {
    snprintf(out, len, "%02lu:%02lu", static_cast<unsigned long>(minutes),
             static_cast<unsigned long>(seconds));
  }
}

void formatStopwatch(uint64_t totalMs, char *out, size_t len) {
  uint32_t hours = static_cast<uint32_t>(totalMs / 3600000ULL);
  uint32_t minutes = static_cast<uint32_t>((totalMs % 3600000ULL) / 60000ULL);
  uint32_t seconds = static_cast<uint32_t>((totalMs % 60000ULL) / 1000ULL);
  uint32_t hundredths = static_cast<uint32_t>((totalMs % 1000ULL) / 10ULL);
  if (hours > 0) {
    snprintf(out, len, "%lu:%02lu:%02lu", static_cast<unsigned long>(hours),
             static_cast<unsigned long>(minutes),
             static_cast<unsigned long>(seconds));
  } else {
    snprintf(out, len, "%02lu:%02lu.%02lu", static_cast<unsigned long>(minutes),
             static_cast<unsigned long>(seconds),
             static_cast<unsigned long>(hundredths));
  }
}

}  // namespace display
