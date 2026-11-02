#include "ble_prov.h"

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <WiFi.h>

#include "clock_time.h"
#include "config.h"
#include "net_link.h"
#include "screens.h"
#include "secrets.h"

namespace bleProv {

// Custom 128-bit DeskMate Provisioning UUIDs
#define BLE_SERVICE_UUID     "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define BLE_CHAR_SSID_UUID   "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define BLE_CHAR_PASS_UUID   "beb5483e-36e1-4688-b7f5-ea07361b26a9"
#define BLE_CHAR_STATUS_UUID "beb5483e-36e1-4688-b7f5-ea07361b26aa"
#define BLE_CHAR_CMD_UUID    "beb5483e-36e1-4688-b7f5-ea07361b26ab"

static bool initialized = false;
static bool advertising = false;
static bool clientConnected = false;
static bool hasAdvertisedOnce = false;

static char stagedSsid[33] = "";
static char stagedPass[65] = "";
static bool connecting = false;
static uint64_t connectStartedMs = 0;

static BLEServer *pServer = nullptr;
static BLECharacteristic *pStatusChar = nullptr;

static void updateStatus(const char *status) {
  if (pStatusChar != nullptr) {
    pStatusChar->setValue(status);
    pStatusChar->notify();
  }
  Serial.printf("[ble] status -> %s\n", status);
}

static void commitCredentials() {
  if (strlen(stagedSsid) == 0) return;
  Serial.printf("[ble] applying Wi-Fi credentials for '%s'...\n", stagedSsid);
  updateStatus("CONNECTING");
  netLink::applyWifiCredentials(stagedSsid, stagedPass);
  connecting = true;
  connectStartedMs = clocktime::monotonicMs();
}

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *pServer) override {
    clientConnected = true;
    Serial.println("[ble] client paired over Bluetooth");
    screens::showNotice("BLE PAIRED", "Receiving Wi-Fi...", 4000);
    updateStatus("READY");
  }

  void onDisconnect(BLEServer *pServer) override {
    clientConnected = false;
    Serial.println("[ble] client disconnected");
    if (advertising && !netLink::wifiConnected()) {
      pServer->startAdvertising();
    }
  }
};

class SsidCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pChar) override {
    String val = pChar->getValue().c_str();
    val.trim();
    if (val.length() > 0) {
      strlcpy(stagedSsid, val.c_str(), sizeof(stagedSsid));
      Serial.printf("[ble] received SSID: '%s'\n", stagedSsid);
    }
  }
};

class PassCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pChar) override {
    String val = pChar->getValue().c_str();
    strlcpy(stagedPass, val.c_str(), sizeof(stagedPass));
    Serial.printf("[ble] received Password (%u chars)\n", (unsigned)strlen(stagedPass));

    // When password is provided, trigger the connection
    if (strlen(stagedSsid) > 0) {
      commitCredentials();
    }
  }
};

class CmdCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pChar) override {
    String val = pChar->getValue().c_str();
    val.trim();
    if (val.equalsIgnoreCase("CONNECT")) {
      commitCredentials();
    }
  }
};

void begin() {
  if (initialized) return;

  BLEDevice::init("DeskMate-01");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  BLEService *pService = pServer->createService(BLE_SERVICE_UUID);

  // SSID Characteristic (Write)
  BLECharacteristic *pSsidChar = pService->createCharacteristic(
      BLE_CHAR_SSID_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
  );
  pSsidChar->setCallbacks(new SsidCallbacks());

  // Password Characteristic (Write)
  BLECharacteristic *pPassChar = pService->createCharacteristic(
      BLE_CHAR_PASS_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
  );
  pPassChar->setCallbacks(new PassCallbacks());

  // Status Characteristic (Read + Notify)
  pStatusChar = pService->createCharacteristic(
      BLE_CHAR_STATUS_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
  );
  pStatusChar->addDescriptor(new BLE2902());
  pStatusChar->setValue("IDLE");

  // Command Characteristic (Write)
  BLECharacteristic *pCmdChar = pService->createCharacteristic(
      BLE_CHAR_CMD_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
  );
  pCmdChar->setCallbacks(new CmdCallbacks());

  pService->start();
  initialized = true;
  Serial.println("[ble] Bluetooth provisioning service started");
}

void startAdvertising() {
  if (!initialized) begin();
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(BLE_SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();
  advertising = true;
  Serial.println("[ble] BLE advertising started as 'DeskMate-01'");
}

void stop() {
  if (advertising) {
    BLEDevice::getAdvertising()->stop();
    advertising = false;
    Serial.println("[ble] BLE advertising stopped");
  }
}

void update() {
  if (!initialized) return;

  const uint64_t now = clocktime::monotonicMs();

  // If Wi-Fi is disconnected after 10s of booting, start BLE advertising automatically
  if (!advertising && !netLink::wifiConnected() && !connecting) {
    if (now > 10000 && !hasAdvertisedOnce) {
      hasAdvertisedOnce = true;
      startAdvertising();
      screens::showNotice("BLE PAIRING", "Ready on Bluetooth", 4000);
    }
  }

  // Monitor connection progress
  if (connecting) {
    if (netLink::wifiConnected()) {
      connecting = false;
      char statusBuf[64];
      snprintf(statusBuf, sizeof(statusBuf), "CONNECTED:%s", netLink::ipAddress());
      updateStatus(statusBuf);
      screens::showNotice("WI-FI CONNECTED", netLink::ipAddress(), 5000);
      Serial.printf("[ble] Wi-Fi connection successful! IP: %s\n", netLink::ipAddress());
    } else if (now - connectStartedMs > 25000) {
      connecting = false;
      updateStatus("FAILED:Connection timeout");
      screens::showNotice("WI-FI FAILED", "Check password", 5000);
      Serial.println("[ble] Wi-Fi connection attempt timed out");
    }
  }
}

bool isAdvertising() { return advertising; }
bool isClientConnected() { return clientConnected; }

}  // namespace bleProv

