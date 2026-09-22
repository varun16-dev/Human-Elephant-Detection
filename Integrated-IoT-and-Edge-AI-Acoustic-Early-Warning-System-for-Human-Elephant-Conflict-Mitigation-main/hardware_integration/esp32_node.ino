/*
============================================================
       INTEGRATED IoT WILDLIFE MONITOR - FINAL
                 ESP32 NODE

HARDWARE
------------------------------------------------------------
PIR SENSOR       -> D19
SOUND SENSOR DO  -> D18
RELAY            -> D23
STATUS LED       -> D22

GPS TX           -> ESP32 D16
GPS RX           -> ESP32 D17

LCD SDA          -> D25
LCD SCL          -> D26
LCD I2C ADDRESS  -> 0x27

FUNCTION
------------------------------------------------------------
PIR OR SOUND DETECTION
        ↓
5 SECOND ALERT
        ↓
LED + RELAY BLINK
        ↓
DATA SENT TO YOUR DASHBOARD

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

const char* DEVICE_ID = "ESP32-NODE-01";


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


// LED / relay blink speed
const unsigned long BLINK_INTERVAL = 250;


// ============================================================
// SENSOR VARIABLES
// ============================================================

bool pirDetected = false;

bool soundDetected = false;


// ============================================================
// GPS VARIABLES
// ============================================================

bool gpsFix = false;

double latitude = 0.0;

double longitude = 0.0;

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

unsigned long lastBlinkTime = 0;

bool blinkState = false;


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

  // Relay OFF at startup
  digitalWrite(
    RELAY_PIN,
    LOW
  );


  // ========================================================
  // LED
  // ========================================================

  pinMode(LED_PIN, OUTPUT);

  digitalWrite(
    LED_PIN,
    LOW
  );


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
  Serial.println("RELAY     : D23");
  Serial.println("LED       : D22");
  Serial.println("GPS RX    : D16");
  Serial.println("GPS TX    : D17");
  Serial.println("LCD SDA   : D25");
  Serial.println("LCD SCL   : D26");

  Serial.println();
  Serial.println("Dashboard:");
  Serial.println(SERVER_URL);

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
// Alert:
// LED    -> BLINK
// RELAY  -> BLINK
// Duration = 5 seconds
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
  // START ALERT
  // ========================================================

  if (
    newPIRDetection ||
    newSoundDetection
  )
  {

    alertActive = true;

    alertStartTime =
      millis();

    lastBlinkTime =
      millis();

    blinkState = true;


    digitalWrite(
      LED_PIN,
      HIGH
    );


    digitalWrite(
      RELAY_PIN,
      HIGH
    );


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
      "LED: BLINKING"
    );

    Serial.println(
      "RELAY: BLINKING"
    );

    Serial.println(
      "Duration: 5 seconds"
    );
  }


  // ========================================================
  // RUN ALERT
  // ========================================================

  if (alertActive)
  {

    // ------------------------------------------------------
    // BLINK
    // ------------------------------------------------------

    if (
      millis() - lastBlinkTime >=
      BLINK_INTERVAL
    )
    {

      lastBlinkTime =
        millis();

      blinkState =
        !blinkState;


      digitalWrite(
        LED_PIN,
        blinkState
      );


      digitalWrite(
        RELAY_PIN,
        blinkState
      );
    }


    // ------------------------------------------------------
    // STOP AFTER 5 SECONDS
    // ------------------------------------------------------

    if (
      millis() - alertStartTime >=
      ALERT_DURATION
    )
    {

      alertActive = false;

      blinkState = false;


      digitalWrite(
        LED_PIN,
        LOW
      );


      digitalWrite(
        RELAY_PIN,
        LOW
      );


      Serial.println();
      Serial.println("ALERT ENDED");
      Serial.println("LED: OFF");
      Serial.println("RELAY: OFF");
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
      lcd.print("GPS: SEARCH");
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

      lcd.print("GPS: NO FIX");
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

      lcd.print("Waiting...");
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