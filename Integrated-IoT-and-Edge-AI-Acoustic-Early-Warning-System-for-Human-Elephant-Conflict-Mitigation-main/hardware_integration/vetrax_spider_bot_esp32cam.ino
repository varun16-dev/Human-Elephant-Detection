/*
================================================================================
          VETRAX SPIDER ROBOT - ESP32-CAM WIRELESS VIDEO TELEMETRY
          Department of AI & ML, Sri Sairam College of Engineering
================================================================================

HARDWARE OVERVIEW:
- Microcontroller: AI-Thinker ESP32-CAM (ESP32-S + OV2640 2MP Camera)
- Flash Memory: 4MB Flash + 4MB external PSRAM
- Communication: 2.4GHz 802.11 b/g/n Wi-Fi
- Host Server: Early Warning Central Dashboard (Flask Edge-AI Engine)

WHY AI INFERENCE IS OFFLOADED TO THE LAPTOP/SERVER:
--------------------------------------------------------------------------------
The existing elephant detection model uses SSD MobileNet v3 trained on COCO
(320x320 floating-point convolutional neural network, weights: ~13.5MB).
The ESP32 microcontroller features 520KB internal SRAM and 4MB PSRAM with a 240MHz
dual-core processor. Running full 320x320 SSD MobileNet on ESP32 would exceed
memory capacity and result in 5-10 second inference latency per frame.
Therefore, VETRAX captures lightweight JPEG frames and streams them over HTTP
to the high-performance laptop/server REST API (/api/robot/vetrax/frame).
The server executes real-time neural inference (<150ms) and dispatches alerts.
================================================================================
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// =============================================================================
// NETWORK CONFIGURATION
// =============================================================================
const char* WIFI_SSID     = "WILDLIFE_MESH_NET";
const char* WIFI_PASSWORD = "ElephantAlertSecure2026";

// Laptop / Edge Server IP address and port
const char* SERVER_FRAME_URL = "http://192.168.1.100:5000/api/robot/vetrax/frame";
const char* DEVICE_ID        = "VETRAX-SPIDER-01";
const char* DEVICE_TOKEN     = "vetrax-secure-edge-token-2026";

// Frame capture interval in milliseconds
const unsigned long FRAME_INTERVAL_MS = 1000; // 1 frame per second
unsigned long lastFrameTime = 0;

// =============================================================================
// AI-THINKER ESP32-CAM PIN DEFINITIONS
// =============================================================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define LED_FLASH_PIN      4   // Bright white flashlight LED
#define STATUS_LED_PIN    33   // Small red onboard status LED (active LOW on AI-Thinker)

// Exponential backoff for network / server error recovery
int consecutiveFailures = 0;
const int MAX_BACKOFF_MS = 10000;

// =============================================================================
// CAMERA INITIALIZATION
// =============================================================================
bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Frame resolution: VGA (640x480) provides optimal balance between bandwidth and AI accuracy
  if (psramFound()) {
    config.frame_size   = FRAMESIZE_VGA;
    config.jpeg_quality = 12; // 10-63, lower number means higher quality
    config.fb_count     = 2;
  } else {
    config.frame_size   = FRAMESIZE_QVGA;
    config.jpeg_quality = 16;
    config.fb_count     = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAMERA] Error: Camera init failed with error 0x%x\n", err);
    return false;
  }

  Serial.println("[CAMERA] OV2640 camera module initialized successfully.");
  return true;
}

// =============================================================================
// TRANSMIT FRAME TO LAPTOP/SERVER AI INFERENCE API
// =============================================================================
bool sendFrameToServer(camera_fb_t* fb) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Warning: WiFi disconnected. Cannot transmit frame.");
    return false;
  }

  HTTPClient http;
  http.begin(SERVER_FRAME_URL);
  http.setTimeout(4000); // 4-second timeout

  // Set HTTP headers
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-ID", DEVICE_ID);
  http.addHeader("X-Device-Token", DEVICE_TOKEN);

  // Turn status LED ON during active transmission
  digitalWrite(STATUS_LED_PIN, LOW); // Active LOW
  int httpCode = http.POST(fb->buf, fb->len);
  digitalWrite(STATUS_LED_PIN, HIGH); // Turn OFF

  if (httpCode > 0) {
    String response = http.getString();
    Serial.printf("[VETRAX] Server Response (%d): %s\n", httpCode, response.c_str());
    http.end();
    if (httpCode == 200) {
      consecutiveFailures = 0; // Reset backoff on success
      return true;
    } else {
      consecutiveFailures++;
      return false;
    }
  } else {
    consecutiveFailures++;
    Serial.printf("[VETRAX] HTTP POST Failed (%d), error: %s (consecutive failures: %d)\n",
                  httpCode, http.errorToString(httpCode).c_str(), consecutiveFailures);
    http.end();
    return false;
  }
}

// =============================================================================
// SETUP
// =============================================================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n[BOOT] Starting VETRAX Spider Robot Video Telemetry...");

  pinMode(LED_FLASH_PIN, OUTPUT);
  digitalWrite(LED_FLASH_PIN, LOW);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, HIGH); // Off (active LOW)

  if (!initCamera()) {
    Serial.println("[FATAL] Camera could not start. Halting.");
    while (true) {
      digitalWrite(STATUS_LED_PIN, LOW); delay(200);
      digitalWrite(STATUS_LED_PIN, HIGH); delay(200);
    }
  }

  // Connect to WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    digitalWrite(STATUS_LED_PIN, (attempts % 2 == 0) ? LOW : HIGH);
    attempts++;
  }
  digitalWrite(STATUS_LED_PIN, HIGH); // Off

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Connected! IP Address: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WIFI] Warning: WiFi connection timeout. Will retry in loop.");
  }
}

// =============================================================================
// MAIN LOOP
// =============================================================================
void loop() {
  unsigned long now = millis();

  // Reconnect WiFi if dropped
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(1000);
    return;
  }

  // Transmit frame at configured interval with failure backoff
  unsigned long currentInterval = FRAME_INTERVAL_MS;
  if (consecutiveFailures > 0) {
    currentInterval += min((unsigned long)consecutiveFailures * 1000UL, (unsigned long)MAX_BACKOFF_MS);
  }

  if (now - lastFrameTime >= currentInterval) {
    lastFrameTime = now;

    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[CAMERA] Error: Failed to capture frame from OV2640.");
      return;
    }

    sendFrameToServer(fb);
    esp_camera_fb_return(fb); // Release frame buffer
  }
}
