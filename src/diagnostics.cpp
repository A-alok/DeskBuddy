#include "diagnostics.h"

#include <U8g2lib.h>
#include <nvs.h>
#include <nvs_flash.h>

#include "chime.h"
#include "clock_time.h"
#include "config.h"
#include "display.h"
#include "relay.h"

namespace diagnostics {

static void rule(const char *title) {
  Serial.println();
  Serial.print("=== ");
  Serial.print(title);
  Serial.println(" ===");
}

static void line(const char *label, uint32_t used, uint32_t total) {
  const float percent = total > 0 ? (100.0f * used) / total : 0.0f;
  // Bar makes the ratio obvious at a glance in a wall of numbers.
  char bar[21];
  const int filled = total > 0 ? static_cast<int>((used * 20UL) / total) : 0;
  for (int i = 0; i < 20; ++i) bar[i] = i < filled ? '#' : '.';
  bar[20] = '\0';

  Serial.printf("%-14s [%s] %5.1f%%  %7lu / %7lu KB  free %lu KB\n", label, bar,
                percent, static_cast<unsigned long>(used / 1024),
                static_cast<unsigned long>(total / 1024),
                static_cast<unsigned long>((total - used) / 1024));
}

void memoryReport() {
  rule("MEMORY");

  // --- program flash ---
  const uint32_t sketch = ESP.getSketchSize();
  const uint32_t sketchFree = ESP.getFreeSketchSpace();
  line("app partition", sketch, sketch + sketchFree);
  Serial.printf("%-14s %lu MB total on the chip\n", "flash chip",
                static_cast<unsigned long>(ESP.getFlashChipSize() / (1024 * 1024)));

  // --- internal RAM ---
  const uint32_t heapTotal = ESP.getHeapSize();
  const uint32_t heapFree = ESP.getFreeHeap();
  line("internal RAM", heapTotal - heapFree, heapTotal);
  Serial.printf("%-14s %lu KB  (worst case since boot)\n", "min free heap",
                static_cast<unsigned long>(ESP.getMinFreeHeap() / 1024));
  Serial.printf("%-14s %lu KB  (largest single allocation possible)\n",
                "max alloc", static_cast<unsigned long>(ESP.getMaxAllocHeap() / 1024));

  // --- PSRAM ---
  const uint32_t psramTotal = ESP.getPsramSize();
  if (psramTotal > 0) {
    const uint32_t psramFree = ESP.getFreePsram();
    line("PSRAM", psramTotal - psramFree, psramTotal);
    Serial.printf("%-14s %lu KB\n", "min free PSRAM",
                  static_cast<unsigned long>(ESP.getMinFreePsram() / 1024));
  } else {
    Serial.println("PSRAM          not initialised");
  }

  // --- NVS (settings, alarms) ---
  nvs_stats_t stats;
  if (nvs_get_stats(nullptr, &stats) == ESP_OK) {
    Serial.printf("%-14s %u / %u entries used  (%u free, %u namespaces)\n", "NVS",
                  stats.used_entries, stats.total_entries, stats.free_entries,
                  stats.namespace_count);
  }
}

// --------------------------------------------------------------------------- //
// Display self-test
// --------------------------------------------------------------------------- //

static void screenTest() {
  rule("DISPLAY TEST");

  if (!display::present()) {
    Serial.println("No panel answered at 0x3C, so there is nothing to test.");
    Serial.println("Everything below is serial-only.");
    return;
  }

  U8G2 &g = display::gfx();

  Serial.println("1/3  every pixel ON — the panel should be solid bright");
  g.clearBuffer();
  g.drawBox(0, 0, 128, 64);
  g.sendBuffer();
  delay(2500);

  Serial.println("2/3  border + crosshair — edges and centre should be crisp");
  g.clearBuffer();
  g.drawFrame(0, 0, 128, 64);
  g.drawFrame(2, 2, 124, 60);
  g.drawLine(0, 32, 127, 32);
  g.drawLine(64, 0, 64, 63);
  for (int x = 0; x < 128; x += 8) g.drawPixel(x, 4);
  g.sendBuffer();
  delay(2500);

  Serial.println("3/3  text at four sizes — all four lines should be readable");
  g.clearBuffer();
  g.setFont(u8g2_font_4x6_tf);
  g.setCursor(2, 7);
  g.print("4x6  the quick brown fox");
  g.setFont(u8g2_font_6x10_tf);
  g.setCursor(2, 20);
  g.print("6x10  DeskMate 0.1.0");
  g.setFont(u8g2_font_helvB10_tr);
  g.setCursor(2, 36);
  g.print("helvB10 OK");
  g.setFont(u8g2_font_logisoso24_tn);
  g.setCursor(2, 62);
  g.print("12:34");
  g.sendBuffer();
  delay(3000);

  Serial.println();
  Serial.println(">>> If the screen stayed blank through all three, the OLED is");
  Serial.println("    the problem, NOT the touch pad. Check SDA=GPIO8, SCL=GPIO9,");
  Serial.println("    VCC=3V3, GND. The panel does ACK on I2C, so power and the");
  Serial.println("    bus are fine — suspect the panel itself or its ribbon.");
}

// --------------------------------------------------------------------------- //
// Relay + chime
// --------------------------------------------------------------------------- //

static void actuatorTest() {
  rule("RELAY TEST");
  Serial.println("Two clicks coming, half a second apart. Listen.");
  const bool before = relay::isOn();
  for (int i = 0; i < 2; ++i) {
    relay::set(true);
    delay(500);
    relay::set(false);
    delay(500);
  }
  relay::set(before);
  Serial.println("No click? Check IN=GPIO13, VCC=5V, GND, and RELAY_ACTIVE_LOW");
  Serial.println("in config.h (currently " +
                 String(RELAY_ACTIVE_LOW ? "1 = active-LOW" : "0 = active-HIGH") + ").");

  rule("CHIME TEST");
  Serial.println("Playing a three-note chime through the MAX98357.");
  chime::playTimerDone();
  const uint64_t until = clocktime::monotonicMs() + 3000;
  while (clocktime::monotonicMs() < until) {
    chime::update();
    delay(2);
  }
  Serial.println("Silent? Check BCLK=15, LRC=16, DIN=7, VIN=5V, and that the");
  Serial.println("speaker is on the amp's output terminals (never to GND).");
  Serial.printf("Volume is %u/10.\n", chime::volume());
}

// --------------------------------------------------------------------------- //
// Live touch
// --------------------------------------------------------------------------- //

static void touchLoop() {
  rule("TOUCH TEST — live");
  Serial.printf("Reading GPIO %d continuously. Tap the pad now.\n", PIN_TOUCH);
  Serial.println("Each change prints a line AND updates the screen.");
  Serial.println("This runs until you reflash with DIAGNOSTIC_MODE 0.");
  Serial.println();

  pinMode(PIN_TOUCH, INPUT);

  bool last = digitalRead(PIN_TOUCH) == HIGH;
  uint32_t transitions = 0;
  uint32_t touches = 0;
  uint64_t lastStatus = 0;
  uint64_t lastDraw = 0;

  while (true) {
    const bool now = digitalRead(PIN_TOUCH) == HIGH;
    const uint64_t ms = clocktime::monotonicMs();

    if (now != last) {
      last = now;
      ++transitions;
      if (now) ++touches;
      Serial.printf("[%8lu ms] pin -> %s   (transitions %lu, touches %lu)\n",
                    static_cast<unsigned long>(ms), now ? "HIGH  ** TOUCH **" : "LOW   release",
                    static_cast<unsigned long>(transitions),
                    static_cast<unsigned long>(touches));
      lastDraw = 0;  // force an immediate redraw
    }

    // Heartbeat so a completely dead pin is still obviously being polled.
    if (ms - lastStatus > 3000) {
      lastStatus = ms;
      Serial.printf("[%8lu ms] polling... pin=%d transitions=%lu\n",
                    static_cast<unsigned long>(ms), now ? 1 : 0,
                    static_cast<unsigned long>(transitions));
      if (transitions == 0 && ms > 15000) {
        Serial.println("           still zero transitions — see the checklist below");
      }
    }

    if (display::present() && ms - lastDraw > 100) {
      lastDraw = ms;
      U8G2 &g = display::gfx();
      g.clearBuffer();

      g.setFont(u8g2_font_4x6_tf);
      g.setCursor(0, 6);
      g.printf("GPIO %d  TOUCH TEST", PIN_TOUCH);
      g.drawHLine(0, 8, 128);

      // The whole point: unmistakable state, readable across a desk.
      if (now) {
        g.drawBox(0, 12, 128, 30);
        g.setDrawColor(0);
        g.setFont(u8g2_font_helvB10_tr);
        g.setCursor(30, 32);
        g.print("TOUCH");
        g.setDrawColor(1);
      } else {
        g.drawFrame(0, 12, 128, 30);
        g.setFont(u8g2_font_helvB10_tr);
        g.setCursor(24, 32);
        g.print("release");
      }

      g.setFont(u8g2_font_6x10_tf);
      g.setCursor(0, 54);
      g.printf("changes:%lu", static_cast<unsigned long>(transitions));
      g.setCursor(76, 54);
      g.printf("hi:%lu", static_cast<unsigned long>(touches));

      g.setFont(u8g2_font_4x6_tf);
      g.setCursor(0, 63);
      g.printf("raw pin level = %d", now ? 1 : 0);
      g.sendBuffer();
    }

    delay(5);
  }
}

void run() {
  Serial.println();
  Serial.println("################################################################");
  Serial.println("#  DIAGNOSTIC MODE — the normal UI and networking are disabled  #");
  Serial.println("#  Set DIAGNOSTIC_MODE 0 in include/config.h to go back         #");
  Serial.println("################################################################");

  memoryReport();
  screenTest();
  actuatorTest();
  touchLoop();  // never returns
}

}  // namespace diagnostics
