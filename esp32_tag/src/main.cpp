/*
 * ============================================================================
 * YODHA HEALTHCARE HACKATHON — MEDICAL EQUIPMENT TRACKING
 * PHASE 1: ESP32 #1 — MOVABLE MEDICAL EQUIPMENT BLE TAG
 * ============================================================================
 *
 * Hardware: DOIT ESP32 DevKit V1 (esp32dev)
 * Framework: Arduino / PlatformIO
 *
 * Role:
 * - Movable BLE beacon attached to physical medical equipment.
 * - Broadcasts its Equipment ID continuously using Bluetooth Low Energy (BLE).
 * - No Wi-Fi is used.
 * - No backend or database connection from this tag.
 * - Does not scan for other devices; it only advertises.
 * ============================================================================
 */

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLEAdvertising.h>

// ============================================================================
// 1. CONFIGURABLE EQUIPMENT ID
// ============================================================================
// Change this ID for different hospital equipment (e.g., "VENT-001", "PUMP-102")
// You do not need to touch any other code when changing this value.
const char* EQUIPMENT_ID = "VENT-001";

// Dedicated Service UUID for our Medical Equipment Tracking System.
// Receivers scan specifically for this UUID to recognize our equipment tags.
#define TRACKING_SERVICE_UUID "4fafc201-1fb5-459e-8fcc-c5c9c331914b"

// Pointer to BLE Advertising controller
BLEAdvertising* pAdvertising = nullptr;

void setup() {
  // Step 1: Start Serial communication at 115200 baud
  Serial.begin(115200);
  delay(1500); // Short delay to let USB Serial stabilize

  // Step 2: Print startup diagnostics
  Serial.println();
  Serial.println("==================================================");
  Serial.println("   YODHA: MEDICAL EQUIPMENT BLE TAG (ESP32 #1)    ");
  Serial.println("==================================================");
  Serial.print("  Equipment ID       : ");
  Serial.println(EQUIPMENT_ID);
  Serial.print("  Tracking UUID      : ");
  Serial.println(TRACKING_SERVICE_UUID);

  // Device name broadcast over BLE (e.g., "MED-TAG:VENT-001")
  String advertisedName = "MED-TAG:" + String(EQUIPMENT_ID);
  Serial.print("  BLE Device Name    : ");
  Serial.println(advertisedName);

  // Step 3: Initialize the BLE stack with our advertised device name
  BLEDevice::init(advertisedName.c_str());

  // Print the tag's physical BLE MAC Address
  Serial.print("  Tag BLE MAC Address: ");
  Serial.println(BLEDevice::getAddress().toString().c_str());

  // Step 4: Create a BLE Server (required by ESP32 BLE stack to advertise)
  BLEServer* pServer = BLEDevice::createServer();

  // Step 5: Configure the Advertising Payload
  pAdvertising = BLEDevice::getAdvertising();

  BLEAdvertisementData advData;
  advData.setName(advertisedName.c_str());
  advData.setCompleteServices(BLEUUID(TRACKING_SERVICE_UUID));

  // Also include the Equipment ID in the Manufacturer Data payload
  // (0xFFFF is the standard test company identifier)
  std::string mfgData = "\xFF\xFF";
  mfgData += EQUIPMENT_ID;
  advData.setManufacturerData(mfgData);

  pAdvertising->setAdvertisementData(advData);

  // Step 6: Configure Scan Response for active BLE scanners
  BLEAdvertisementData scanResponseData;
  scanResponseData.setName(advertisedName.c_str());
  pAdvertising->setScanResponseData(scanResponseData);

  // Step 7: Set advertising parameters for fast, reliable discovery
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06); // 7.5 ms interval helper
  pAdvertising->setMinPreferred(0x12); // 22.5 ms interval helper

  // Step 8: Start continuous BLE advertising
  BLEDevice::startAdvertising();

  Serial.println("--------------------------------------------------");
  Serial.println("  [STATUS] BLE Advertising STARTED successfully!");
  Serial.println("  [STATUS] Broadcasting beacons continuously...");
  Serial.println("==================================================");
  Serial.println();
}

void loop() {
  // Print heartbeat diagnostic message every 5 seconds
  static unsigned long lastHeartbeatTime = 0;
  unsigned long currentTime = millis();

  if (currentTime - lastHeartbeatTime >= 5000) {
    lastHeartbeatTime = currentTime;
    Serial.print("[HEARTBEAT] Tag Active | Equipment: ");
    Serial.print(EQUIPMENT_ID);
    Serial.print(" | Uptime: ");
    Serial.print(currentTime / 1000);
    Serial.println("s");
  }

  // Small delay to yield execution to FreeRTOS background tasks
  delay(100);
}
