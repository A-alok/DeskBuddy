#pragma once
/**
 * Bluetooth Low Energy (BLE) Provisioning for AI DeskMate.
 *
 * Implements smartwatch-style onboarding:
 * 1. Advertises as "DeskMate-01" (DEVICE_ID) over BLE.
 * 2. Companion web browser (via Web Bluetooth API) or phone pairs over BLE.
 * 3. Sends Wi-Fi SSID and Password over BLE characteristics.
 * 4. The ESP32 writes them to NVS flash and associates with Wi-Fi.
 * 5. Notifies the client of live connection status and local IP address.
 */

#include <Arduino.h>

namespace bleProv {

void begin();
void update();
void startAdvertising();
void stop();
bool isAdvertising();
bool isClientConnected();

}  // namespace bleProv

