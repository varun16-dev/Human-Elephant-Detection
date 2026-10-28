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


// ENTER YOUR MOBILE HOTSPOT DETAILS HERE
const char* HOTSPOT_SSID = "OnePlus Nord CE3";
const char* HOTSPOT_PASSWORD = "vaha3116";

// Legacy configuration-portal constants.
const char* CONFIG_AP_SSID = "ESP32_Config";
const char* CONFIG_AP_PASSWORD = "12345678";


// ============================================================
// DASHBOARD BACKEND
// ============================================================

const char* DEFAULT_SERVER_URL =
  "http://10.57.175.122:5000/api/esp32/data";

String dashboardServerURL = DEFAULT_SERVER_URL;


// ============================================================
// DEVICE ID
// ============================================================

const char* DEVICE_ID = "ESP32-NODE-01";


// ============================================================
// SOUND SENSOR LOGIC
// ============================================================

// HIGH = sound detected
// LOW  = no sound

#define SOUND_ACTIVE_STATE HIGH


// ============================================================
// TIMINGS
// ============================================================

const unsigned long SEND_INTERVAL = 2000;

const unsigned long LCD_INTERVAL = 2000;

const unsigned long WIFI_CHECK_INTERVAL = 5000;

const unsigned long ALERT_DURATION = 5000;

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
bool webServerStarted = false;


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


  // PIR

  pinMode(PIR_PIN, INPUT);


  // SOUND

  pinMode(SOUND_PIN, INPUT);


  // RELAY

  pinMode(RELAY_PIN, OUTPUT);

  digitalWrite(RELAY_PIN, LOW);


  // LED

  pinMode(LED_PIN, OUTPUT);

  digitalWrite(LED_PIN, LOW);


  // LCD

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


  // GPS

  GPSSerial.begin(
    9600,
    SERIAL_8N1,
    GPS_RX_PIN,
    GPS_TX_PIN
  );

  Serial.println("GPS Serial Started");


  // CONNECT TO MOBILE HOTSPOT

  bool connected = connectToSavedWiFi();

  if (!connected)
  {
    Serial.println();
    Serial.println("Could not connect to the phone hotspot.");
    Serial.println("Check HOTSPOT_SSID and HOTSPOT_PASSWORD in the code.");

    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("Hotspot Failed");

    lcd.setCursor(0, 1);
    lcd.print("Check WiFi info");

    delay(3000);
  }
  else
  {
    Serial.println();
    Serial.println("Connected to the configured hotspot.");

    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("WiFi Connected");

    lcd.setCursor(0, 1);
    lcd.print(WiFi.localIP());

    delay(3000);
  }


  // START WEB SERVER

  if (!webServerStarted)
  {
    server.on("/", HTTP_GET, handleRoot);
    server.on("/save", HTTP_POST, handleSave);

    server.begin();

    webServerStarted = true;
  }

  Serial.print("ESP32 network address: http://");

  Serial.println(
    WiFi.status() == WL_CONNECTED
      ? WiFi.localIP().toString()
      : String("Not connected")
  );

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
  Serial.println(dashboardServerURL);

  Serial.println("========================================");
}


// ============================================================
// MAIN LOOP
// ============================================================

void loop()
{
  // CONFIGURATION SERVER

  if (webServerStarted)
  {
    server.handleClient();
  }


  // READ GPS

  readGPS();


  // READ PIR

  readPIR();


  // READ SOUND

  readSound();


  // HANDLE ALERT

  handleAlert();


  // WIFI MONITOR

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

      bool connected = connectToSavedWiFi();

      if (!connected)
      {
        Serial.println("Reconnection failed.");
        Serial.println("Will retry the configured phone hotspot automatically.");
      }
    }
  }


  // LCD UPDATE

  if (
    millis() - lastLCDTime >=
    LCD_INTERVAL
  )
  {
    lastLCDTime = millis();

    updateLCD();
  }


  // SEND DATA TO DASHBOARD

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
  int state = digitalRead(PIR_PIN);

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
  int state = digitalRead(SOUND_PIN);

  if (state == SOUND_ACTIVE_STATE)
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
  while (GPSSerial.available() > 0)
  {
    char c = GPSSerial.read();

    gps.encode(c);
  }


  // VALID GPS LOCATION

  if (gps.location.isValid())
  {
    gpsFix = true;

    latitude = gps.location.lat();

    longitude = gps.location.lng();

    if (gps.satellites.isValid())
    {
      satellites = gps.satellites.value();
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
// LED    -> BLINK
// RELAY  -> BLINK
// Duration = 5 seconds
// ============================================================

void handleAlert()
{
  // NEW PIR DETECTION

  bool newPIRDetection =
    pirDetected &&
    !previousPIR;


  // NEW SOUND DETECTION

  bool newSoundDetection =
    soundDetected &&
    !previousSound;


  // START ALERT

  if (
    newPIRDetection ||
    newSoundDetection
  )
  {
    alertActive = true;

    alertStartTime = millis();

    lastBlinkTime = millis();

    blinkState = true;

    digitalWrite(LED_PIN, HIGH);

    digitalWrite(RELAY_PIN, HIGH);

    Serial.println();
    Serial.println("========================================");
    Serial.println("           !!! ALERT !!!");
    Serial.println("========================================");

    if (newPIRDetection)
    {
      Serial.println("PIR: DETECTED");
    }

    if (newSoundDetection)
    {
      Serial.println("SOUND: DETECTED");
    }

    Serial.println("LED: BLINKING");
    Serial.println("RELAY: BLINKING");
    Serial.println("Duration: 5 seconds");
  }


  // RUN ALERT

  if (alertActive)
  {
    // BLINK

    if (
      millis() - lastBlinkTime >=
      BLINK_INTERVAL
    )
    {
      lastBlinkTime = millis();

      blinkState = !blinkState;

      digitalWrite(LED_PIN, blinkState);

      digitalWrite(RELAY_PIN, blinkState);
    }


    // STOP AFTER 5 SECONDS

    if (
      millis() - alertStartTime >=
      ALERT_DURATION
    )
    {
      alertActive = false;

      blinkState = false;

      digitalWrite(LED_PIN, LOW);

      digitalWrite(RELAY_PIN, LOW);

      Serial.println();
      Serial.println("ALERT ENDED");
      Serial.println("LED: OFF");
      Serial.println("RELAY: OFF");
    }
  }


  // SAVE CURRENT SENSOR STATES

  previousPIR = pirDetected;

  previousSound = soundDetected;
}


// ============================================================
// LCD UPDATE
// GPS IS NOT DISPLAYED ON THE LCD
// GPS DATA STILL GOES TO THE DASHBOARD
// ============================================================

void updateLCD()
{
  lcd.clear();

  // ALERT SCREEN

  if (alertActive)
  {
    lcd.setCursor(0, 0);
    lcd.print("!!! ALERT !!!");

    lcd.setCursor(0, 1);

    if (pirDetected && soundDetected)
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


  // PAGE 0: SENSOR STATUS

  if (lcdPage == 0)
  {
    lcd.setCursor(0, 0);

    lcd.print("PIR:");
    lcd.print(pirDetected ? "YES " : "NO  ");

    lcd.print("S:");
    lcd.print(soundDetected ? "YES" : "NO ");

    lcd.setCursor(0, 1);

    if (pirDetected && soundDetected)
    {
      lcd.print("PIR + Sound Det.");
    }
    else if (pirDetected)
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


  // PAGE 1: WIFI STATUS

  else if (lcdPage == 1)
  {
    lcd.setCursor(0, 0);

    if (WiFi.status() == WL_CONNECTED)
    {
      lcd.print("WiFi: CONNECTED");
    }
    else
    {
      lcd.print("WiFi: OFFLINE");
    }

    lcd.setCursor(0, 1);

    if (WiFi.status() == WL_CONNECTED)
    {
      lcd.print("RSSI:");
      lcd.print(WiFi.RSSI());
      lcd.print(" dBm");
    }
    else
    {
      lcd.print("No Connection");
    }
  }


  // PAGE 2: SYSTEM STATUS

  else if (lcdPage == 2)
  {
    lcd.setCursor(0, 0);
    lcd.print("Wildlife Monitor");

    lcd.setCursor(0, 1);

    if (WiFi.status() == WL_CONNECTED)
    {
      lcd.print("System Online");
    }
    else
    {
      lcd.print("System Offline");
    }
  }


  // ROTATE THROUGH LCD PAGES

  lcdPage++;

  if (lcdPage > 2)
  {
    lcdPage = 0;
  }
}


// ============================================================
// SEND DATA TO DASHBOARD
// ============================================================

void sendDataToDashboard()
{
  // WIFI CHECK

  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("Dashboard: WiFi offline");

    return;
  }


  // HTTP

  HTTPClient http;

  http.setConnectTimeout(5000);
  http.setTimeout(5000);

  if (!http.begin(dashboardServerURL))
  {
    Serial.println("Dashboard HTTP initialization failed.");

    return;
  }

  http.addHeader("Content-Type", "application/json");


  // JSON

  String json = "{";


  // DEVICE ID

  json += "\"deviceId\":\"";
  json += DEVICE_ID;
  json += "\",";


  // PIR

  json += "\"pir\":";

  json += pirDetected ? "true" : "false";

  json += ",";


  // SOUND

  json += "\"sound\":";

  json += soundDetected ? "true" : "false";

  json += ",";


  // GPS FIX

  json += "\"gpsFix\":";

  json += gpsFix ? "true" : "false";

  json += ",";


  // LATITUDE

  json += "\"latitude\":";

  json += String(latitude, 6);

  json += ",";


  // LONGITUDE

  json += "\"longitude\":";

  json += String(longitude, 6);

  json += ",";


  // SATELLITES

  json += "\"satellites\":";

  json += String(satellites);

  json += ",";


  // ALERT

  json += "\"alert\":";

  json += alertActive ? "true" : "false";

  json += ",";


  // WIFI RSSI

  json += "\"wifiRSSI\":";

  json += String(WiFi.RSSI());


  // CLOSE JSON

  json += "}";


  // DEBUG

  Serial.println();
  Serial.println("----------------------------------------");
  Serial.println("Sending data to YOUR dashboard:");
  Serial.println(json);


  // POST

  int responseCode = http.POST(json);

  if (responseCode > 0)
  {
    Serial.print("Dashboard HTTP: ");
    Serial.println(responseCode);

    String response = http.getString();

    Serial.print("Dashboard response: ");
    Serial.println(response);
  }
  else
  {
    Serial.print("Dashboard connection error: ");
    Serial.println(responseCode);

    Serial.print("HTTP error detail: ");
    Serial.println(http.errorToString(responseCode));

    Serial.print("ESP32 Wi-Fi IP: ");
    Serial.println(WiFi.localIP());

    Serial.print("Dashboard URL: ");
    Serial.println(dashboardServerURL);

    Serial.println("Check the computer IP, backend status, port 5000, and firewall.");
  }

  http.end();
}


// ============================================================
// CONNECT TO MOBILE HOTSPOT
// ============================================================

bool connectToSavedWiFi()
{
  // ALWAYS USE CURRENT DEFAULT_SERVER_URL FIRST TO PREVENT STALE SAVED IP
  dashboardServerURL = DEFAULT_SERVER_URL;

  // USE HOTSPOT CREDENTIALS FROM CODE

  String ssid = HOTSPOT_SSID;

  String password = HOTSPOT_PASSWORD;

  if (
    ssid.length() == 0 ||
    ssid == "YOUR_PHONE_HOTSPOT_NAME"
  )
  {
    Serial.println("Set HOTSPOT_SSID in the code before uploading.");

    return false;
  }

  if (password == "YOUR_PHONE_HOTSPOT_PASSWORD")
  {
    Serial.println("Set HOTSPOT_PASSWORD in the code before uploading.");

    return false;
  }


  Serial.println();
  Serial.println("Connecting to your phone hotspot...");

  Serial.print("Hotspot SSID: ");
  Serial.println(ssid);


  WiFi.mode(WIFI_STA);

  WiFi.setAutoReconnect(true);

  WiFi.disconnect();

  delay(500);

  WiFi.begin(
    ssid.c_str(),
    password.c_str()
  );


  unsigned long startTime = millis();

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - startTime < 20000
  )
  {
    delay(500);

    Serial.print(".");
  }

  Serial.println();


  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("Phone hotspot connected!");

    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());

    configPortalActive = false;

    return true;
  }


  Serial.println("Hotspot connection failed. Check SSID, password, and 2.4 GHz hotspot setting.");

  return false;
}


// ============================================================
// START CONFIGURATION PORTAL
// ============================================================

void startConfigPortal()
{
  Serial.println();
  Serial.println("Starting ESP32 WiFi setup...");

  WiFi.mode(WIFI_AP);

  bool result = WiFi.softAP(
    CONFIG_AP_SSID,
    CONFIG_AP_PASSWORD
  );

  if (!result)
  {
    Serial.println("Failed to start WiFi AP.");

    return;
  }

  configPortalActive = true;

  Serial.println();
  Serial.println("========================================");
  Serial.println("        WIFI CONFIGURATION");
  Serial.println("========================================");

  Serial.print("Connect phone to: ");
  Serial.println(CONFIG_AP_SSID);

  Serial.print("Password: ");
  Serial.println(CONFIG_AP_PASSWORD);

  Serial.print("Open: ");
  Serial.println("192.168.4.1");


  // ROUTES

  if (!webServerStarted)
  {
    server.on("/", HTTP_GET, handleRoot);
    server.on("/save", HTTP_POST, handleSave);

    server.begin();

    webServerStarted = true;
  }


  // LCD

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
autocomplete="current-password"
>

<label>Dashboard Backend URL</label>

<input
type="url"
name="backendUrl"
required
value="__BACKEND_URL__"
>

<p>Example: http://192.168.1.100:5000/api/esp32/data</p>

<button type="submit">
Save & Connect
</button>

</form>

</div>

</body>

</html>

)rawliteral";


  preferences.begin("dashboard", true);

  String savedBackendUrl =
    preferences.getString("url", DEFAULT_SERVER_URL);

  preferences.end();

  html.replace("__BACKEND_URL__", savedBackendUrl);

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
  if (!server.hasArg("ssid"))
  {
    server.send(
      400,
      "text/plain",
      "SSID missing"
    );

    return;
  }


  String ssid = server.arg("ssid");

  String password = server.arg("password");

  String backendUrl = server.arg("backendUrl");

  backendUrl.trim();


  if (
    backendUrl.length() == 0 ||
    !backendUrl.startsWith("http://")
  )
  {
    server.send(
      400,
      "text/plain",
      "Invalid dashboard URL. Use an http:// address."
    );

    return;
  }


  // KEEP OLD PASSWORD IF THE SAME SSID IS SUBMITTED

  preferences.begin("wifi", true);

  String oldSSID = preferences.getString("ssid", "");

  String oldPassword = preferences.getString("password", "");

  preferences.end();


  if (
    password.length() == 0 &&
    ssid == oldSSID
  )
  {
    password = oldPassword;
  }


  // SAVE WIFI CREDENTIALS

  preferences.begin("wifi", false);

  preferences.putString("ssid", ssid);

  preferences.putString("password", password);

  preferences.end();


  // SAVE DASHBOARD URL

  preferences.begin("dashboard", false);

  preferences.putString("url", backendUrl);

  preferences.end();

  dashboardServerURL = backendUrl;


  // RESPONSE

  server.send(
    200,
    "text/html",
    "<h2>WiFi Saved</h2>"
    "<p>ESP32 is connecting...</p>"
  );

  delay(1500);


  WiFi.softAPdisconnect(true);

  configPortalActive = false;


  // CONNECT

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
  Serial.println("Connecting to new WiFi...");

  WiFi.mode(WIFI_STA);

  WiFi.begin(
    ssid.c_str(),
    password.c_str()
  );


  unsigned long startTime = millis();

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - startTime < 20000
  )
  {
    delay(500);

    Serial.print(".");
  }

  Serial.println();


  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("WiFi connected successfully!");

    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());

    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("WiFi Connected");

    lcd.setCursor(0, 1);
    lcd.print(WiFi.localIP());

    delay(3000);

    lcd.clear();

    return true;
  }


  Serial.println("New WiFi connection failed.");

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("WiFi Failed");

  lcd.setCursor(0, 1);
  lcd.print("Try Again");

  delay(2000);

  startConfigPortal();

  return false;
}