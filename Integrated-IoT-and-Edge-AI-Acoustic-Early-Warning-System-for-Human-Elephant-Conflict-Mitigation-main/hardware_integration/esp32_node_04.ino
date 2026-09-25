/*
============================================================
       INTEGRATED IoT WILDLIFE MONITOR - FINAL
                 ESP32 NODE

HARDWARE
------------------------------------------------------------
PIR SENSOR       -> D19
SOUND SENSOR DO  -> D18
RELAY (Strobe)   -> D23 (Controls physical strobe light)
STATUS LED       -> D22 (Local status indicator)

GPS TX           -> ESP32 D16
GPS RX           -> ESP32 D17

LCD SDA          -> D25
LCD SCL          -> D26
LCD I2C ADDRESS  -> 0x27

FUNCTION
------------------------------------------------------------
PIR OR SOUND DETECTION
        ↓
5 SECOND ALERT (Sensors only - no LED/RELAY control)
        ↓
DATA SENT TO YOUR DASHBOARD

LED STROBE CONTROL
        ↓
MANUAL DASHBOARD CONTROL ONLY
        ↓
ON: Both Relay and LED blink together continuously
        ↓
OFF: Both Relay and LED completely OFF immediately
        ↓
NO AUTOMATIC TRIGGERS

NO MAKE CLOUD
NO EXTERNAL CLOUD API
============================================================
*/


// ============================================================
// LIBRARIES
// ============================================================

#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <TinyGPSPlus.h>


// ============================================================
// PIN DEFINITIONS
// ============================================================

#define PIR_PIN       19
#define SOUND_PIN     18

#define RELAY_PIN     23
#define LED_PIN       22
#define ONBOARD_LED_PIN 2

// ============================================================
// RELAY CONTROL CONSTANTS
// ============================================================
// Configure relay polarity here only
// Active-HIGH relay: RELAY_ON = HIGH, RELAY_OFF = LOW
// Active-LOW relay:  RELAY_ON = LOW,  RELAY_OFF = HIGH
// ============================================================

#define RELAY_ON  LOW
#define RELAY_OFF HIGH

#define GPS_RX_PIN    16
#define GPS_TX_PIN    17

#define LCD_SDA_PIN   25
#define LCD_SCL_PIN   26


// ============================================================
// LCD
// ============================================================

LiquidCrystal_I2C lcd(0x27, 16, 2);


// ============================================================
// GPS
// ============================================================

TinyGPSPlus gps;

HardwareSerial GPSSerial(2);


// ============================================================
// WIFI CONFIGURATION
// ============================================================

WebServer server(80);

Preferences preferences;


// ESP32 configuration hotspot
const char* CONFIG_AP_SSID = "ESP32_Config";
const char* CONFIG_AP_PASSWORD = "12345678";


// ============================================================
// YOUR DASHBOARD BACKEND
// ============================================================
//
// This is YOUR dashboard backend.
//
// IMPORTANT:
// If the computer running server.py gets a new IP,
// change SERVER_URL below.
//
// ============================================================

const char* SERVER_URL =
  "http://10.238.159.122:5000/api/esp32/data";


// ============================================================
// DEVICE ID
// ============================================================

const char* DEVICE_ID = "ESP32-NODE-04";


// ============================================================
// SOUND SENSOR LOGIC
// ============================================================
//
// Current hardware testing uses:
// HIGH = sound detected
// LOW  = no sound
//
// If your sensor is opposite, change HIGH to LOW.
//
// ============================================================

#define SOUND_ACTIVE_STATE HIGH


// ============================================================
// TIMINGS
// ============================================================

const unsigned long SEND_INTERVAL = 2000;

const unsigned long LCD_INTERVAL = 2000;

const unsigned long WIFI_CHECK_INTERVAL = 5000;


// Alert duration
const unsigned long ALERT_DURATION = 5000;


// ============================================================
// SENSOR VARIABLES
// ============================================================

bool pirDetected = false;

bool soundDetected = false;


// ============================================================
// GPS VARIABLES
// ============================================================

bool gpsFix = false;

// Default GPS coordinates for Node 4 - Ragihalli Village
// These are used if GPS has no fix
double latitude = 12.7180;

double longitude = 77.5840;

int satellites = 0;


// ============================================================
// PREVIOUS SENSOR STATES
// ============================================================
//
// Used to detect a NEW event.
// This prevents the alert timer from restarting
// continuously while a sensor remains active.
// ============================================================

bool previousPIR = false;

bool previousSound = false;


// ============================================================
// ALERT VARIABLES
// ============================================================

bool alertActive = false;

unsigned long alertStartTime = 0;


// ============================================================
// STROBE CONTROL VARIABLES (Global for state management)
// ============================================================

bool strobeLightManualControl = false;  // Manual control from dashboard
bool strobeLightState = false;          // Current strobe light state
unsigned long strobeBlinkInterval = 250;  // Blink every 250ms
unsigned long lastStrobeBlinkTime = 0;
bool strobeBlinkState = false;          // Current blink state





// ============================================================
// LCD PAGE
// ============================================================

int lcdPage = 0;


// ============================================================
// CONFIGURATION PORTAL
// ============================================================

bool configPortalActive = false;


// ============================================================
// TIMERS
// ============================================================

unsigned long lastSendTime = 0;

unsigned long lastLCDTime = 0;

unsigned long lastWiFiCheck = 0;


// ============================================================
// FUNCTION DECLARATIONS
// ============================================================

void handleRoot();

void handleSave();

void startConfigPortal();

bool connectToSavedWiFi();

bool connectToWiFi(
  String ssid,
  String password
);

void readPIR();

void readSound();

void readGPS();

void handleAlert();

void updateLCD();

void sendDataToDashboard();

void handleActuatorCommand();

void handleManualStrobe();


// ============================================================
// SETUP
// ============================================================

void setup()
{

  Serial.begin(115200);

  delay(1000);


  Serial.println();
  Serial.println("========================================");
  Serial.println("       ESP32 WILDLIFE MONITOR");
  Serial.println("       NODE 04 - Ragihalli Village");
  Serial.println("========================================");


  // ========================================================
  // PIR
  // ========================================================

  pinMode(PIR_PIN, INPUT);


  // ========================================================
  // SOUND
  // ========================================================

  pinMode(SOUND_PIN, INPUT);


  // ========================================================
  // RELAY
  // ========================================================

  pinMode(RELAY_PIN, OUTPUT);

  // Force relay OFF at startup
  digitalWrite(RELAY_PIN, RELAY_OFF);


  // ========================================================
  // LED
  // ========================================================

  pinMode(LED_PIN, OUTPUT);
  pinMode(ONBOARD_LED_PIN, OUTPUT);

  // LED OFF at startup
  digitalWrite(LED_PIN, LOW);
  digitalWrite(ONBOARD_LED_PIN, LOW);


  // ========================================================
  // INITIALIZE STROBE STATE
  // ========================================================

  strobeLightManualControl = false;
  strobeLightState = false;
  strobeBlinkState = false;
  lastStrobeBlinkTime = 0;

  // Force hardware OFF immediately at startup
  digitalWrite(RELAY_PIN, RELAY_OFF);
  digitalWrite(LED_PIN, LOW);
  digitalWrite(ONBOARD_LED_PIN, LOW);


  // ========================================================
  // GPS COORDINATES (Node 4 - Ragihalli Village)
  // ========================================================

  // These coordinates will be sent to the dashboard
  // If GPS has a fix, these will be overridden by actual GPS data
  // If GPS has no fix, these serve as fallback coordinates

  Serial.println("GPS Coordinates configured:");
  Serial.println("  Latitude:  12.7180");
  Serial.println("  Longitude: 77.5840");


  // ========================================================
  // LCD
  // ========================================================

  Wire.begin(
    LCD_SDA_PIN,
    LCD_SCL_PIN
  );

  lcd.init();

  lcd.backlight();

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("ESP32 Starting");

  lcd.setCursor(0, 1);
  lcd.print("Please wait...");

  delay(2000);


  // ========================================================
  // GPS
  // ========================================================

  GPSSerial.begin(
    9600,
    SERIAL_8N1,
    GPS_RX_PIN,
    GPS_TX_PIN
  );

  Serial.println("GPS Serial Started");


  // ========================================================
  // WIFI
  // ========================================================

  bool connected =
    connectToSavedWiFi();


  if (!connected)
  {

    Serial.println();
    Serial.println("No working WiFi found.");

    startConfigPortal();
  }

  else
  {

    Serial.println();
    Serial.println("Using saved WiFi configuration.");

    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("WiFi Connected");

    lcd.setCursor(0, 1);
    lcd.print(WiFi.localIP());

    delay(3000);
  }


  lcd.clear();


  Serial.println();
  Serial.println("========================================");
  Serial.println("             SYSTEM READY");
  Serial.println("========================================");

  Serial.println("PIR       : D19");
  Serial.println("SOUND     : D18");
  Serial.println("RELAY     : D23 (Physical Strobe - active-HIGH)");
  Serial.println("LED       : D22 (Status LED - blinks with relay)");
  Serial.println("GPS RX    : D16");
  Serial.println("GPS TX    : D17");
  Serial.println("LCD SDA   : D25");
  Serial.println("LCD SCL   : D26");

  Serial.println();
  Serial.println("LOCATION  : Ragihalli Village, Bengaluru Urban, KA");
  Serial.println("GPS LAT   : 12.7180");
  Serial.println("GPS LON   : 77.5840");

  Serial.println();
  Serial.println("LED STROBE: MANUAL CONTROL ONLY");
  Serial.println("ON: Both relay and LED blink together");
  Serial.println("OFF: Both relay and LED completely OFF immediately");
  Serial.println("Dashboard:");
  Serial.println(SERVER_URL);

  // ========================================================
  // START WEB SERVER FOR ACTUATOR COMMANDS
  // ========================================================
  
  server.on(
    "/actuator",
    HTTP_POST,
    handleActuatorCommand
  );
  
  server.begin();
  Serial.println("Web server started for actuator commands");

  Serial.println("========================================");
}


// ============================================================
// MAIN LOOP
// ============================================================

void loop()
{

  // ========================================================
  // CONFIGURATION SERVER
  // ========================================================

  if (configPortalActive)
  {
    server.handleClient();
  }
  else
  {
    // Always handle web server requests for actuator commands
    server.handleClient();
  }


  // ========================================================
  // READ GPS
  // ========================================================

  readGPS();


  // ========================================================
  // READ PIR
  // ========================================================

  readPIR();


  // ========================================================
  // READ SOUND
  // ========================================================

  readSound();


  // ========================================================
  // HANDLE ALERT
  // ========================================================

  handleAlert();


  // ========================================================
  // HANDLE MANUAL STROBE CONTROL
  // ========================================================

  handleManualStrobe();


  // ========================================================
  // WIFI MONITOR
  // ========================================================

  if (
    millis() - lastWiFiCheck >=
    WIFI_CHECK_INTERVAL
  )
  {

    lastWiFiCheck = millis();


    if (WiFi.status() != WL_CONNECTED)
    {

      Serial.println();
      Serial.println("WiFi disconnected!");


      lcd.clear();

      lcd.setCursor(0, 0);
      lcd.print("WiFi Offline");

      lcd.setCursor(0, 1);
      lcd.print("Reconnecting...");


      bool connected =
        connectToSavedWiFi();


      if (!connected)
      {

        Serial.println(
          "Reconnection failed."
        );

        startConfigPortal();
      }
    }
  }


  // ========================================================
  // LCD UPDATE
  // ========================================================

  if (
    millis() - lastLCDTime >=
    LCD_INTERVAL
  )
  {

    lastLCDTime = millis();

    updateLCD();
  }


  // ========================================================
  // SEND DATA TO DASHBOARD
  // ========================================================

  if (
    millis() - lastSendTime >=
    SEND_INTERVAL
  )
  {

    lastSendTime = millis();

    sendDataToDashboard();
  }


  delay(10);
}


// ============================================================
// READ PIR
// ============================================================

void readPIR()
{

  int state =
    digitalRead(PIR_PIN);


  if (state == HIGH)
  {
    pirDetected = true;
  }
  else
  {
    pirDetected = false;
  }
}


// ============================================================
// READ SOUND
// ============================================================

void readSound()
{

  int state =
    digitalRead(SOUND_PIN);


  if (
    state ==
    SOUND_ACTIVE_STATE
  )
  {
    soundDetected = true;
  }
  else
  {
    soundDetected = false;
  }
}


// ============================================================
// READ GPS
// ============================================================

void readGPS()
{

  while (
    GPSSerial.available() > 0
  )
  {

    char c =
      GPSSerial.read();

    gps.encode(c);
  }


  // ========================================================
  // VALID GPS LOCATION
  // ========================================================

  if (
    gps.location.isValid()
  )
  {

    gpsFix = true;

    latitude =
      gps.location.lat();

    longitude =
      gps.location.lng();


    if (
      gps.satellites.isValid()
    )
    {

      satellites =
        gps.satellites.value();
    }
    else
    {

      satellites = 0;
    }
  }

  else
  {

    gpsFix = false;
  }
}


// ============================================================
// HANDLE ALERT
// ============================================================
//
// PIR OR SOUND = ALERT
//
// NOTE: LED/RELAY automatic triggering REMOVED - strobe is now manual only
// ============================================================

void handleAlert()
{

  // ========================================================
  // NEW PIR DETECTION
  // ========================================================

  bool newPIRDetection =
    pirDetected &&
    !previousPIR;


  // ========================================================
  // NEW SOUND DETECTION
  // ========================================================

  bool newSoundDetection =
    soundDetected &&
    !previousSound;


  // ========================================================
  // START ALERT (Sensors only - no LED/RELAY control)
  // ========================================================

  if (newPIRDetection || newSoundDetection)
  {

    alertActive = true;

    alertStartTime =
      millis();


    Serial.println();
    Serial.println("========================================");
    Serial.println("           !!! ALERT !!!");
    Serial.println("========================================");


    if (newPIRDetection)
    {
      Serial.println(
        "PIR: DETECTED"
      );
    }


    if (newSoundDetection)
    {
      Serial.println(
        "SOUND: DETECTED"
      );
    }


    Serial.println(
      "Duration: 5 seconds"
    );
  }


  // ========================================================
  // RUN ALERT (Sensors only - no LED/RELAY control)
  // ========================================================

  if (alertActive)
  {

    // ------------------------------------------------------
    // STOP AFTER 5 SECONDS
    // ------------------------------------------------------

    if (
      millis() - alertStartTime >=
      ALERT_DURATION
    )
    {

      alertActive = false;


      Serial.println();
      Serial.println("ALERT ENDED");
    }
  }


  // ========================================================
  // SAVE CURRENT SENSOR STATES
  // ========================================================

  previousPIR =
    pirDetected;

  previousSound =
    soundDetected;
}


// ============================================================
// LCD UPDATE
// ============================================================

void updateLCD()
{

  lcd.clear();


  // ========================================================
  // ALERT SCREEN
  // ========================================================

  if (alertActive)
  {

    lcd.setCursor(0, 0);

    lcd.print("!!! ALERT !!!");


    lcd.setCursor(0, 1);


    if (
      pirDetected &&
      soundDetected
    )
    {

      lcd.print("PIR + SOUND");
    }

    else if (pirDetected)
    {

      lcd.print("PIR DETECTED");
    }

    else if (soundDetected)
    {

      lcd.print("SOUND DETECTED");
    }

    else
    {

      lcd.print("DETECTION");
    }


    return;
  }


  // ========================================================
  // PAGE 0
  // ========================================================

  if (lcdPage == 0)
  {

    lcd.setCursor(0, 0);

    lcd.print("PIR:");

    if (pirDetected)
      lcd.print("YES ");
    else
      lcd.print("NO  ");


    lcd.print("S:");

    if (soundDetected)
      lcd.print("YES");
    else
      lcd.print("NO");


    lcd.setCursor(0, 1);


    if (pirDetected)
    {
      lcd.print("Motion Detected");
    }

    else if (soundDetected)
    {
      lcd.print("Sound Detected");
    }

    else
    {
      lcd.print("No Detection");
    }
  }


  // ========================================================
  // PAGE 1
  // ========================================================

  else if (lcdPage == 1)
  {

    lcd.setCursor(0, 0);

    if (gpsFix)
    {
      lcd.print("GPS: FIXED");
    }
    else
    {
      lcd.print("Searching...");
    }


    lcd.setCursor(0, 1);

    if (gpsFix)
    {

      lcd.print("SAT:");

      lcd.print(
        satellites
      );
    }
    else
    {

      lcd.print("No Location");
    }
  }


  // ========================================================
  // PAGE 2
  // ========================================================

  else if (lcdPage == 2)
  {

    lcd.setCursor(0, 0);

    if (gpsFix)
    {

      lcd.print("LAT:");

      lcd.print(
        latitude,
        4
      );
    }
    else
    {

      lcd.print("Acquiring...");
    }


    lcd.setCursor(0, 1);

    if (gpsFix)
    {

      lcd.print("LON:");

      lcd.print(
        longitude,
        4
      );
    }
    else
    {

      lcd.print("Signal...");
    }
  }


  // ========================================================
  // PAGE 3
  // ========================================================

  else if (lcdPage == 3)
  {

    lcd.setCursor(0, 0);

    if (
      WiFi.status() ==
      WL_CONNECTED
    )
    {

      lcd.print("WiFi: CONNECTED");
    }
    else
    {

      lcd.print("WiFi: OFFLINE");
    }


    lcd.setCursor(0, 1);

    if (
      WiFi.status() ==
      WL_CONNECTED
    )
    {

      lcd.print("RSSI:");

      lcd.print(
        WiFi.RSSI()
      );
    }
    else
    {

      lcd.print("No Connection");
    }
  }


  // ========================================================
  // NEXT PAGE
  // ========================================================

  lcdPage++;

  if (lcdPage > 3)
  {
    lcdPage = 0;
  }
}


// ============================================================
// SEND DATA TO YOUR DASHBOARD
// ============================================================

void sendDataToDashboard()
{

  // ========================================================
  // WIFI CHECK
  // ========================================================

  if (
    WiFi.status() !=
    WL_CONNECTED
  )
  {

    Serial.println(
      "Dashboard: WiFi offline"
    );

    return;
  }


  // ========================================================
  // HTTP
  // ========================================================

  HTTPClient http;


  http.begin(
    SERVER_URL
  );


  http.setTimeout(3000);


  http.addHeader(
    "Content-Type",
    "application/json"
  );


  // ========================================================
  // JSON
  // ========================================================

  String json = "{";


  // DEVICE ID
  json += "\"deviceId\":\"";
  json += DEVICE_ID;
  json += "\",";


  // PIR
  json += "\"pir\":";

  json +=
    pirDetected
    ? "true"
    : "false";

  json += ",";


  // SOUND
  json += "\"sound\":";

  json +=
    soundDetected
    ? "true"
    : "false";

  json += ",";


  // GPS FIX
  json += "\"gpsFix\":";

  json +=
    gpsFix
    ? "true"
    : "false";

  json += ",";


  // LATITUDE
  json += "\"latitude\":";

  json += String(
    latitude,
    6
  );

  json += ",";


  // LONGITUDE
  json += "\"longitude\":";

  json += String(
    longitude,
    6
  );

  json += ",";


  // SATELLITES
  json += "\"satellites\":";

  json += String(
    satellites
  );

  json += ",";


  // ALERT
  json += "\"alert\":";

  json +=
    alertActive
    ? "true"
    : "false";

  json += ",";


  // WIFI RSSI
  json += "\"wifiRSSI\":";

  json += String(
    WiFi.RSSI()
  );

  json += ",";


  // STROBE LIGHT STATE
  json += "\"ledStrobe\":";

  json += strobeLightState ? "true" : "false";

  json += ",";


  // STROBE MANUAL CONTROL
  json += "\"strobeManualControl\":";

  json += strobeLightManualControl ? "true" : "false";


  // CLOSE JSON
  json += "}";


  // ========================================================
  // DEBUG
  // ========================================================

  Serial.println();
  Serial.println("----------------------------------------");
  Serial.println("Sending data to YOUR dashboard:");
  Serial.println(json);


  // ========================================================
  // POST
  // ========================================================

  int responseCode =
    http.POST(
      json
    );


  if (
    responseCode > 0
  )
  {

    Serial.print(
      "Dashboard HTTP: "
    );

    Serial.println(
      responseCode
    );


    String response =
      http.getString();


    Serial.print(
      "Dashboard response: "
    );

    Serial.println(
      response
    );
  }

  else
  {

    Serial.print(
      "Dashboard connection error: "
    );

    Serial.println(
      responseCode
    );
  }


  http.end();
}


// ============================================================
// CONNECT TO SAVED WIFI
// ============================================================

bool connectToSavedWiFi()
{

  preferences.begin(
    "wifi",
    true
  );


  String ssid =
    preferences.getString(
      "ssid",
      ""
    );


  String password =
    preferences.getString(
      "password",
      ""
    );


  preferences.end();


  if (
    ssid.length() == 0
  )
  {

    Serial.println(
      "No saved WiFi."
    );

    return false;
  }


  Serial.println();
  Serial.println(
    "Connecting to saved WiFi..."
  );

  Serial.print(
    "SSID: "
  );

  Serial.println(
    ssid
  );


  WiFi.mode(
    WIFI_STA
  );


  WiFi.disconnect();

  delay(500);


  WiFi.begin(
    ssid.c_str(),
    password.c_str()
  );


  unsigned long startTime =
    millis();


  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - startTime < 20000
  )
  {

    delay(500);

    Serial.print(".");
  }


  Serial.println();


  if (
    WiFi.status() ==
    WL_CONNECTED
  )
  {

    Serial.println(
      "WiFi connected!"
    );

    Serial.print(
      "ESP32 IP: "
    );

    Serial.println(
      WiFi.localIP()
    );


    configPortalActive =
      false;


    return true;
  }


  Serial.println(
    "WiFi connection failed."
  );


  return false;
}


// ============================================================
// START CONFIGURATION PORTAL
// ============================================================

void startConfigPortal()
{

  Serial.println();
  Serial.println(
    "Starting ESP32 WiFi setup..."
  );


  WiFi.mode(
    WIFI_AP
  );


  bool result =
    WiFi.softAP(
      CONFIG_AP_SSID,
      CONFIG_AP_PASSWORD
    );


  if (!result)
  {

    Serial.println(
      "Failed to start WiFi AP."
    );

    return;
  }


  configPortalActive =
    true;


  Serial.println();
  Serial.println(
    "========================================"
  );

  Serial.println(
    "        WIFI CONFIGURATION"
  );

  Serial.println(
    "========================================"
  );


  Serial.print(
    "Connect phone to: "
  );

  Serial.println(
    CONFIG_AP_SSID
  );


  Serial.print(
    "Password: "
  );

  Serial.println(
    CONFIG_AP_PASSWORD
  );


  Serial.print(
    "Open: "
  );

  Serial.println(
    "192.168.4.1"
  );


  // ========================================================
  // ROUTES
  // ========================================================

  server.on(
    "/",
    HTTP_GET,
    handleRoot
  );


  server.on(
    "/save",
    HTTP_POST,
    handleSave
  );


  server.on(
    "/actuator",
    HTTP_POST,
    handleActuatorCommand
  );


  server.begin();


  // ========================================================
  // LCD
  // ========================================================

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("WiFi Setup");

  lcd.setCursor(0, 1);
  lcd.print("192.168.4.1");
}


// ============================================================
// WIFI SETUP PAGE
// ============================================================

void handleRoot()
{

  String html = R"rawliteral(

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>ESP32 WiFi Setup</title>

<style>

body {
  font-family: Arial;
  background: #f2f4f7;
  padding: 20px;
}

.container {
  max-width: 420px;
  margin: auto;
  background: white;
  padding: 25px;
  border-radius: 15px;
}

input {
  width: 100%;
  padding: 12px;
  margin-top: 8px;
  margin-bottom: 15px;
  box-sizing: border-box;
}

button {
  width: 100%;
  padding: 13px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 8px;
}

</style>

</head>

<body>

<div class="container">

<h2>ESP32 WiFi Setup</h2>

<p>
Connect ESP32 to your WiFi or mobile hotspot.
</p>

<form action="/save" method="POST">

<label>WiFi / Hotspot Name</label>

<input
type="text"
name="ssid"
required
>

<label>WiFi Password</label>

<input
type="password"
name="password"
>

<button type="submit">
Save & Connect
</button>

</form>

</div>

</body>

</html>

)rawliteral";


  server.send(
    200,
    "text/html",
    html
  );
}


// ============================================================
// SAVE WIFI
// ============================================================

void handleSave()
{

  if (
    !server.hasArg("ssid")
  )
  {

    server.send(
      400,
      "text/plain",
      "SSID missing"
    );

    return;
  }


  String ssid =
    server.arg("ssid");


  String password =
    server.arg("password");


  // ========================================================
  // SAVE
  // ========================================================

  preferences.begin(
    "wifi",
    false
  );


  preferences.putString(
    "ssid",
    ssid
  );


  preferences.putString(
    "password",
    password
  );


  preferences.end();


  // ========================================================
  // RESPONSE
  // ========================================================

  server.send(
    200,
    "text/html",
    "<h2>WiFi Saved</h2>"
    "<p>ESP32 is connecting...</p>"
  );


  delay(1500);


  WiFi.softAPdisconnect(
    true
  );


  configPortalActive =
    false;


  // ========================================================
  // CONNECT
  // ========================================================

  connectToWiFi(
    ssid,
    password
  );
}


// ============================================================
// CONNECT TO NEW WIFI
// ============================================================

bool connectToWiFi(
  String ssid,
  String password
)
{

  Serial.println();
  Serial.println(
    "Connecting to new WiFi..."
  );


  WiFi.mode(
    WIFI_STA
  );


  WiFi.begin(
    ssid.c_str(),
    password.c_str()
  );


  unsigned long startTime =
    millis();


  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - startTime < 20000
  )
  {

    delay(500);

    Serial.print(".");
  }


  Serial.println();


  if (
    WiFi.status() ==
    WL_CONNECTED
  )
  {

    Serial.println(
      "WiFi connected successfully!"
    );


    Serial.print(
      "ESP32 IP: "
    );

    Serial.println(
      WiFi.localIP()
    );


    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("WiFi Connected");

    lcd.setCursor(0, 1);
    lcd.print(WiFi.localIP());


    delay(3000);

    lcd.clear();


    return true;
  }


  Serial.println(
    "New WiFi connection failed."
  );


  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("WiFi Failed");

  lcd.setCursor(0, 1);
  lcd.print("Try Again");


  delay(2000);


  startConfigPortal();


  return false;
}


// ============================================================
// HANDLE ACTUATOR COMMAND FROM DASHBOARD
// ============================================================

void handleActuatorCommand()
{
  Serial.println();
  Serial.println("----------------------------------------");
  Serial.println("Received actuator command from dashboard");


  // Check if request has JSON body
  if (!server.hasArg("plain"))
  {
    Serial.println("Error: No JSON body received");
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"No JSON body\"}");
    return;
  }


  String jsonBody = server.arg("plain");
  Serial.print("JSON received: ");
  Serial.println(jsonBody);


  // Parse JSON (simple manual parsing for this use case)
  String actuator = "";
  String action = "";


  // Extract actuator
  int actuatorIndex = jsonBody.indexOf("\"actuator\":");
  if (actuatorIndex >= 0)
  {
    int valueStart = jsonBody.indexOf("\"", actuatorIndex + 11) + 1; // Skip ":"
    int valueEnd = jsonBody.indexOf("\"", valueStart);
    if (valueStart > 0 && valueEnd > valueStart)
    {
      actuator = jsonBody.substring(valueStart, valueEnd);
    }
  }


  // Extract action
  int actionIndex = jsonBody.indexOf("\"action\":");
  if (actionIndex >= 0)
  {
    int valueStart = jsonBody.indexOf("\"", actionIndex + 9) + 1; // Skip ":"
    int valueEnd = jsonBody.indexOf("\"", valueStart);
    if (valueStart > 0 && valueEnd > valueStart)
    {
      action = jsonBody.substring(valueStart, valueEnd);
    }
  }


  Serial.print("Actuator: ");
  Serial.println(actuator);
  Serial.print("Action: ");
  Serial.println(action);


  // Process strobe light command
  if (actuator == "strobe_light")
  {
    if (action == "on" || (action == "toggle" && !strobeLightState))
    {
      strobeLightManualControl = true;
      strobeLightState = true;
      strobeBlinkState = true;
      lastStrobeBlinkTime = millis();
      
      // Start blinking immediately - both relay and LED ON
      digitalWrite(RELAY_PIN, RELAY_ON);
      digitalWrite(LED_PIN, HIGH);
      digitalWrite(ONBOARD_LED_PIN, HIGH);
      
      Serial.println("STROBE LIGHT: ON (Continuous blinking started)");
      
      String response = "{\"status\":\"success\",\"actuator\":\"strobe_light\",\"state\":\"on\",\"message\":\"Strobe light turned ON - continuous blinking\"}";
      server.send(200, "application/json", response);
    }
    else if (action == "off" || (action == "toggle" && strobeLightState))
    {
      // IMMEDIATELY force OFF - do this first
      strobeLightManualControl = false;
      strobeLightState = false;
      strobeBlinkState = false;
      
      // IMMEDIATELY turn OFF both relay and status LED
      digitalWrite(RELAY_PIN, RELAY_OFF);
      digitalWrite(LED_PIN, LOW);
  digitalWrite(ONBOARD_LED_PIN, LOW);
      
      Serial.println("STROBE LIGHT: OFF (IMMEDIATE - Hardware forced OFF)");
      
      String response = "{\"status\":\"success\",\"actuator\":\"strobe_light\",\"state\":\"off\",\"message\":\"Strobe light turned OFF immediately\"}";
      server.send(200, "application/json", response);
    }
    else
    {
      Serial.println("Error: Invalid action for strobe_light");
      String response = "{\"status\":\"error\",\"message\":\"Invalid action\"}";
      server.send(400, "application/json", response);
    }
  }
  else
  {
    Serial.println("Error: Unknown actuator");
    String response = "{\"status\":\"error\",\"message\":\"Unknown actuator\"}";
    server.send(400, "application/json", response);
  }
}

// ============================================================
// HANDLE MANUAL STROBE CONTROL
// ============================================================
// Continuous non-blocking blink control for manual strobe operation
// Both relay and LED blink together when strobe is active
// ============================================================

void handleManualStrobe()
{
  // IF strobe is disabled, immediately force hardware OFF and return
  if (strobeLightManualControl == false || strobeLightState == false)
  {
    strobeBlinkState = false;
    digitalWrite(RELAY_PIN, RELAY_OFF);
    digitalWrite(LED_PIN, LOW);
  digitalWrite(ONBOARD_LED_PIN, LOW);
    return;
  }
  
  // OTHERWISE strobe is enabled - use non-blocking blink
  if (millis() - lastStrobeBlinkTime >= strobeBlinkInterval)
  {
    lastStrobeBlinkTime = millis();
    strobeBlinkState = !strobeBlinkState;
    
    // Toggle both relay and LED together using relay constants
    if (strobeBlinkState)
    {
      digitalWrite(RELAY_PIN, RELAY_ON);
      digitalWrite(LED_PIN, HIGH);
      digitalWrite(ONBOARD_LED_PIN, HIGH);
    }
    else
    {
      digitalWrite(RELAY_PIN, RELAY_OFF);
      digitalWrite(LED_PIN, LOW);
  digitalWrite(ONBOARD_LED_PIN, LOW);
    }
  }
}