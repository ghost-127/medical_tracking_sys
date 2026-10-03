#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>

// ============================================================================
// WIFI & TELEMETRY CONFIGURATION
// ============================================================================
const char* WIFI_SSID = "iqoo z9";
const char* WIFI_PASSWORD = "12345671";
const char* FLASK_SERVER_URL = "http://10.111.176.58:5000";
const String TELEMETRY_ENDPOINT = "/api/telemetry";
const unsigned long TELEMETRY_INTERVAL_MS = 2000;

// ============================================================================
// RECEIVER CONFIGURATION
// ============================================================================
const String RECEIVER_ID = "RECEIVER_A";
const String ZONE_NAME = "ICU";
const String TEST_POSITION = "ICU"; // ONLY for test organization
const String TRACKING_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b";
const String TARGET_PREFIX = "MED-TAG:"; // Base prefix used by tags

int scanTime = 3; // Scan for 3 seconds
BLEScan* pBLEScan;

// ============================================================================
// RSSI SMOOTHING
// ============================================================================
const int RSSI_SAMPLE_COUNT = 5;
int rssiReadings[RSSI_SAMPLE_COUNT];
int rssiIndex = 0;
bool rssiWindowFilled = false;

// ============================================================================
// ZONE DECISION CONFIGURATION
// ============================================================================
// Placeholders for thresholds determined from the calibration test
const float ICU_DECISION_THRESHOLD = -60.0;     // Minimum smoothed RSSI to be considered in ICU
const float MIN_RELIABLE_RSSI = -90.0;          // Signals weaker than this are completely ignored
const float HYSTERESIS_MARGIN = 3.0;            // Margin to prevent rapid toggling between zones

// State tracking for stability
String currentLocalZone = "UNKNOWN";
String pendingZone = "UNKNOWN";
unsigned long zoneStabilizationStartTime = 0;
const unsigned long REQUIRED_STABILITY_MS = 2000; // Require 2 seconds of consistent readings to switch

// Track if tag was found during this scan
bool tagFoundInCurrentScan = false;

float getSmoothedRSSI() {
  int sum = 0;
  int count = rssiWindowFilled ? RSSI_SAMPLE_COUNT : rssiIndex;
  if (count == 0) return 0;
  for (int i = 0; i < count; i++) {
    sum += rssiReadings[i];
  }
  return (float)sum / count;
}

class MyAdvertisedDeviceCallbacks: public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice advertisedDevice) {
      String deviceName = advertisedDevice.haveName() ? advertisedDevice.getName().c_str() : "Unknown";
      
      bool isTarget = false;

      // Identify our medical equipment tag using exactly the same logic as Receiver B
      // 1. Check if name matches our Tag
      if (deviceName.startsWith(TARGET_PREFIX)) {
        isTarget = true;
      }

      // 2. Or check if service UUID matches our Tracking UUID
      if (advertisedDevice.haveServiceUUID()) {
        BLEUUID devUUID = advertisedDevice.getServiceUUID();
        if (devUUID.equals(BLEUUID(TRACKING_UUID.c_str()))) {
           isTarget = true;
        }
      }

      if (isTarget) {
          tagFoundInCurrentScan = true;
          int currentRSSI = advertisedDevice.getRSSI();
          
          String equipmentId = "";
          if (deviceName.startsWith(TARGET_PREFIX)) {
            equipmentId = deviceName.substring(TARGET_PREFIX.length());
          } else {
            equipmentId = "VENT-001"; // Fallback
          }

          // Update rolling average
          rssiReadings[rssiIndex] = currentRSSI;
          rssiIndex = (rssiIndex + 1) % RSSI_SAMPLE_COUNT;
          if (rssiIndex == 0) rssiWindowFilled = true;

          float smoothedRSSI = getSmoothedRSSI();

          // Zone Decision Logic with Hysteresis
          String calculatedZone = currentLocalZone;
          
          // Process only reliable signals
          if (smoothedRSSI >= MIN_RELIABLE_RSSI) {
              if (currentLocalZone == "ICU") {
                  // Must drop below threshold - margin to lose ICU status (Hysteresis)
                  if (smoothedRSSI < (ICU_DECISION_THRESHOLD - HYSTERESIS_MARGIN)) {
                      calculatedZone = "UNKNOWN";
                  }
              } else {
                  // Must meet or exceed threshold to gain ICU status
                  if (smoothedRSSI >= ICU_DECISION_THRESHOLD) {
                      calculatedZone = "ICU";
                  }
              }
          } else {
              calculatedZone = "UNKNOWN";
          }

          // Apply stability mechanism (prevent rapid flipping)
          if (calculatedZone != currentLocalZone) {
              if (calculatedZone == pendingZone) {
                  // We are waiting for stability
                  if (millis() - zoneStabilizationStartTime >= REQUIRED_STABILITY_MS) {
                      currentLocalZone = calculatedZone;
                  }
              } else {
                  // New zone detected, start stabilization timer
                  pendingZone = calculatedZone;
                  zoneStabilizationStartTime = millis();
              }
          } else {
              // Stable in current zone
              pendingZone = currentLocalZone;
          }

          // Telemetry and Output Throttling
          static unsigned long lastTelemetryTime = 0;
          if (millis() - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
            lastTelemetryTime = millis();

            Serial.println("========================================");
            Serial.println("BLE RECEIVER");
            Serial.println("========================================");
            Serial.println("Receiver: " + RECEIVER_ID);
            Serial.println("Zone: " + ZONE_NAME);
            Serial.println("");
            Serial.println("Equipment ID: " + equipmentId);
            Serial.println("Raw RSSI: " + String(currentRSSI) + " dBm");
            Serial.println("Smoothed RSSI: " + String(smoothedRSSI, 1) + " dBm");
            Serial.println("");
            
            if (WiFi.status() == WL_CONNECTED) {
              Serial.println("Wi-Fi: CONNECTED");
              Serial.println("IP: " + WiFi.localIP().toString());
              Serial.println("");
              Serial.println("Telemetry:");
              Serial.println("POST " + TELEMETRY_ENDPOINT);
              
              HTTPClient http;
              String fullUrl = String(FLASK_SERVER_URL) + TELEMETRY_ENDPOINT;
              http.begin(fullUrl);
              http.addHeader("Content-Type", "application/json");
              http.setTimeout(3000); // 3 second timeout so we don't block BLE too long
              
              // Build JSON payload
              String jsonPayload = "{\"equipment_id\":\"" + equipmentId + "\",\"receiver_id\":\"" + RECEIVER_ID + "\",\"zone\":\"" + currentLocalZone + "\",\"rssi\":" + String(currentRSSI) + ",\"smoothed_rssi\":" + String(smoothedRSSI, 1) + "}";
              
              int httpResponseCode = http.POST(jsonPayload);
              
              Serial.print("HTTP Status: ");
              Serial.println(httpResponseCode);
              
              if (httpResponseCode == 200) {
                 Serial.println("Telemetry sent successfully");
              } else if (httpResponseCode <= 0) {
                 Serial.println("Error: Server unavailable");
              }
              http.end();
            } else {
              Serial.println("Wi-Fi: DISCONNECTED");
            }
            Serial.println("========================================\n");
          }
      }
    }
};

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(WIFI_SSID);
  
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  unsigned long startAttemptTime = millis();
  const unsigned long WIFI_TIMEOUT_MS = 10000; // 10 seconds timeout
  
  while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < WIFI_TIMEOUT_MS) {
    Serial.print(".");
    delay(500);
  }
  
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Wi-Fi connected");
    Serial.print("ESP32 IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi connection failed or timed out.");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000); // Give Serial monitor time to connect

  Serial.println("========================================");
  Serial.println("Medical Equipment BLE Receiver");
  Serial.println("========================================");
  Serial.println("Receiver ID: " + RECEIVER_ID);
  Serial.println("Zone: " + ZONE_NAME);
  Serial.println("Tracking UUID: " + TRACKING_UUID);
  Serial.println("BLE receiver started");
  Serial.println("========================================\n");

  // Connect to Wi-Fi
  connectWiFi();

  // Initialize BLE scanning
  BLEDevice::init("");
  pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new MyAdvertisedDeviceCallbacks(), true);
  pBLEScan->setActiveScan(true); 
  pBLEScan->setInterval(100);
  pBLEScan->setWindow(99); 
}

void loop() {
  // Auto-reconnect Wi-Fi if lost
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  tagFoundInCurrentScan = false;
  
  // Continuously scan for BLE advertisements
  BLEScanResults foundDevices = pBLEScan->start(scanTime, false);
  
  // If VENT-001 is not detected for a reasonable period, print:
  if (!tagFoundInCurrentScan) {
      Serial.println("Equipment tag not detected.");
  }
  
  pBLEScan->clearResults(); // Crucial: clear buffer to avoid memory leaks
  delay(1000); // Continue scanning after short delay
}
