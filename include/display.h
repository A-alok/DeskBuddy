#pragma once
/**
 * SH1106 panel wrapper: the U8g2 instance, drawing helpers, and burn-in
 * protection.
 *
 * OLEDs degrade where they are lit, and a clock face is the worst case: the same
 * pixels on for hours. The panel dims after two minutes of no interaction and
 * blanks after ten, waking on any touch.
 */

#include <Arduino.h>
#include <U8g2lib.h>

namespace display {

/**
 * Probe the I2C bus and initialise the panel.
 *
 * Returns false if no display answered at 0x3C. That is not fatal: the rest of
 * the firmware carries on and every draw call becomes a no-op. A desk clock that
 * refuses to boot because its screen is unplugged is worse than one that boots
 * and tells you the screen is unplugged.
 */
bool begin();

/** False when no panel answered at boot. */
bool present();

/** The U8g2 object, for screens that need to draw directly. */
U8G2 &gfx();

/** Reset the dim/blank timers. Call on any user interaction. */
void noteActivity();

/** Apply dim/blank policy. Call once per frame before drawing. */
void updatePowerSave();

bool isAwake();
/** Wake the panel. Returns true if it had been dimmed or blanked. */
bool wake();

void setBrightness(uint8_t value);  // 10..255
uint8_t brightness();

/** Returns how long the panel has been idle, in milliseconds. */
uint64_t idleTimeMs();

// --- drawing helpers ----------------------------------------------------- //

/** Draw `text` horizontally centred at baseline `y`. */
void centerText(const char *text, int16_t y);

/** Centred within an explicit x range — for split layouts. */
void centerTextIn(const char *text, int16_t x, int16_t width, int16_t y);

/** Hairline progress bar. `value` is clamped to 0..1. */
void progressBar(int16_t x, int16_t y, int16_t w, int16_t h, float value);

/** The top status strip: screen title, Wi-Fi dot, link dot, clock. */
void statusBar(const char *title);

/** The bottom hint line describing what the gestures do here. */
void hintBar(const char *hint);

/** mm:ss or h:mm:ss into `out`. */
void formatClock(uint32_t totalSeconds, char *out, size_t len);
/** mm:ss.cc for the stopwatch. */
void formatStopwatch(uint64_t totalMs, char *out, size_t len);

}  // namespace display
