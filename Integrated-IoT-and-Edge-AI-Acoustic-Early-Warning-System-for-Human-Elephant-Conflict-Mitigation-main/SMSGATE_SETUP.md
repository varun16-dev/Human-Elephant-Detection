# SMS Gateway for Android (SMSGate) - Setup & Operational Guide
**Human-Elephant Conflict (HEC) Early Warning System**  
**Department of AI & ML, Sri Sairam College of Engineering**

---

## Overview

This guide explains how to install, configure, and operate **SMS Gateway for Android** (by [capcom6](https://github.com/capcom6/android-sms-gateway)) in **Local Server mode**. With this transport, early warning elephant detection alerts are transmitted directly via your dedicated Android phone's physical SIM card—eliminating third-party cloud aggregator fees and external dependencies.

---

## 1. Prerequisites

- An Android smartphone running **Android 8.0 through Android 15**.
- Active SIM card with an SMS pack enabled (unlimited or 100 SMS/day allowance).
- Wi-Fi connection connecting the phone and the early warning system server on the same private local network.
- USB charger and permanent power supply for the phone.

---

## 2. App Installation

1. On your Android phone, download the latest APK release from the official repository:
   - **GitHub Releases**: [https://github.com/capcom6/android-sms-gateway/releases](https://github.com/capcom6/android-sms-gateway/releases)
   - Download `android-sms-gateway-vX.X.X.apk` (or universal release APK).
2. Tap the downloaded `.apk` file to install.

### Android 15 & Play Protect Notes
- **Google Play Protect Prompt**: Because this app is sideloaded from GitHub and requests the `SEND_SMS` permission, Google Play Protect may display a warning: *"Blocked by Play Protect"*. Tap **More details** $\rightarrow$ **Install anyway**.
- **Manual SMS Permissions**: On Android 13, 14, and 15, Android restricts SMS background permissions.
  1. Go to phone **Settings** $\rightarrow$ **Apps** $\rightarrow$ **SMS Gateway**.
  2. Tap **Permissions** $\rightarrow$ **SMS** $\rightarrow$ select **Allow**.
  3. Tap **Notifications** $\rightarrow$ select **Allow** (so background service notifications are never silenced).
  4. If prompted with *"Restricted settings"*, go to **Settings** $\rightarrow$ **Apps** $\rightarrow$ **SMS Gateway** $\rightarrow$ tap the **three dots** in the top right $\rightarrow$ select **Allow restricted settings**.

---

## 3. Local Server Configuration

1. Launch the **SMS Gateway** app.
2. In the app settings/dashboard:
   - Enable **Local Server** (toggle on).
   - Note the **IP address** displayed on the screen (e.g. `http://192.168.1.150:8080`).
   - Note the default **Username** and generated **Password**.
3. **Set Custom Credentials**:
   - Change the password to a strong, secure passphrase.
   - Tap **Save** and **Restart Server** to apply the new credentials.

---

## 4. Power & Background Reliability

To prevent Android OS from sleeping or terminating the background server:

1. **Disable Battery Optimization**:
   - Go to phone **Settings** $\rightarrow$ **Apps** $\rightarrow$ **SMS Gateway** $\rightarrow$ **App battery usage**.
   - Change setting from *Optimized* to **Unrestricted**.
2. **Keep Device Charging**:
   - Keep the phone connected to a continuous USB charger.
   - In **Developer Options**, you may optionally enable **Stay awake while charging** (Screen will never sleep while charging).
3. **Lock App in Recent Apps**:
   - Open Recent Apps view, tap the app icon above the card, and select **Lock** (keeps app pinned in memory on MIUI/OneUI/ColorOS).

---

## 5. Network Setup (DHCP Reservation & Security)

### Router DHCP Reservation
- Because your early warning server talks to the phone via its local IP (e.g. `192.168.1.150`), an IP change would break alert dispatch.
- Log into your local Wi-Fi router settings:
  1. Navigate to **DHCP Server** / **Address Reservation**.
  2. Find your Android phone's MAC address (found in phone **Settings** $\rightarrow$ **About phone** $\rightarrow$ **Status information**).
  3. Assign a static DHCP reservation so the phone always gets the exact same IP address.

### Security Warning: Never Port-Forward
> [!WARNING]
> **Local Server mode uses HTTP Basic Authentication in plaintext.**
> - **NEVER** configure port-forwarding or expose port `8080` to the public internet.
> - Keep both the server and the phone strictly inside the private LAN/Wi-Fi subnet.
> - If deploying across different sites, connect via a secure private VPN tunnel (such as WireGuard or Tailscale).

---

## 6. Verify Endpoint Path in Swagger

Open a browser on any computer connected to the same Wi-Fi:
```text
http://<phone-ip>:8080/docs
```
1. Inspect the interactive Swagger / OpenAPI documentation provided by the phone app.
2. Verify the messages endpoint route:
   - Modern releases use `/messages` (plural).
   - Some builds use `/message` (singular).
   - If your documentation displays `POST /message`, configure `SMSGATE_MESSAGES_PATH=/message` in `.env`.

---

## 7. Server Environment Configuration (.env)

Add the following environment variables to your private `.env` file on the server.  
*(Reference template available in `.env.sms.example`)*:

```bash
# ------------------------------------------------------------------------------
# SMS GATEWAY FOR ANDROID (SMSGate Local Server Mode)
# ------------------------------------------------------------------------------
SMS_GATEWAY_PROVIDER=smsgate
SMSGATE_BASE_URL=http://192.168.1.150:8080
SMSGATE_USERNAME=admin
SMSGATE_PASSWORD=YourSecureGatewayPasswordHere
SMSGATE_MESSAGES_PATH=/messages
SMSGATE_TIMEOUT=8.0
SMSGATE_MAX_RETRIES=3
SMSGATE_BACKOFF=2.0
SMS_TTL_SECONDS=900
SMS_PRIORITY=100
SMSGATE_ALLOW_PUBLIC_HOST=false

# Alert Policy & Monitoring
ALERT_MONITORING_STATE=karnataka
ALERT_MONITORING_LOCATION=Bandipur Wildlife Corridor
ALERT_SMS_COOLDOWN_SECONDS=300
ALERT_COUNT_CHANGE_POLICY=always
ALERT_ABSENCE_RESET_SECONDS=120
```

> [!IMPORTANT]
> - Never commit `.env` or paste real passwords in version control.
> - The application automatically validates that `SMSGATE_BASE_URL` is a private, loopback, or `.local`/`.lan` address. Global public IPs are blocked for security unless `SMSGATE_ALLOW_PUBLIC_HOST=true` is set.

---

## 8. Carrier SMS Charges & Message Segmentation

Bilingual alerts contain Unicode characters in Indic scripts (Kannada / தமிழ்).

- **GSM-7 Standard**: Plain ASCII allows up to 160 characters per segment.
- **UCS-2 Unicode**: Any text containing Indic script requires UCS-2 encoding:
  - 1 segment: up to **70 characters**.
  - Multi-part concatenated SMS: **67 characters per segment**.
- **Bilingual Alert Payload**:
  - A full alert containing English + Kannada (or English + Tamil), live herd count, location, timestamp, and dashboard link averages **250 to 380 characters**.
  - This translates to approximately **4 to 6 billed SMS segments per recipient**.
- **Carrier Advice**:
  - Ensure your SIM card has an active unlimited SMS plan or bulk SMS package.
  - Indian telecom operators (Jio, Airtel, Vi) typically enforce a regulatory cap of 100 SMS/day per SIM on standard prepaid plans.

---

## 9. End-to-End Verification Procedure

Follow this 5-step checklist to confirm end-to-end operation before live field deployment:

### Step 1: Gateway Direct Health Check
Run a curl command from the server terminal:
```bash
curl -u admin:YourSecureGatewayPasswordHere http://<phone-ip>:8080/health
```
Expected response:
```json
{"status":"OK","battery":95,"internet":true}
```

### Step 2: Dashboard "Test Connection"
1. Open the web dashboard: `http://localhost:5000/dashboard`
2. Navigate to the **Android SIM SMS Gateway** card.
3. Click **Test Gateway Connection**.
4. Confirm green badge: `CONNECTED` showing phone battery % and local server status.

### Step 3: Bilingual Message Preview
1. In the SMS Settings section, click **Preview Message**.
2. Select Karnataka (Kannada) or Tamil Nadu (Tamil).
3. Confirm dynamic variables are populated correctly:
   - Herd count (e.g., `3 elephants detected`)
   - Location name
   - Timestamp
   - Local script accuracy
4. *Note: Preview never dispatches an SMS.*

### Step 4: Confirmed Test SMS
1. Verify that your authorized test phone number is listed under **Recipients**.
2. Click **Send Test SMS**.
3. Type the confirmation phrase or accept the security confirmation dialog.
4. Verify on your phone:
   - An SMS arrives from your Android phone's SIM number.
   - Message clearly states `[SYSTEM TEST]` with zero elephant count.
   - History logs status as `gateway_accepted` $\rightarrow$ `sent_to_carrier` $\rightarrow$ `delivered`.

### Step 5: Live Video Pipeline Test
1. Run a sample detection video clip through the edge AI detector.
2. Verify that the dynamic elephant count is extracted directly from the vision model.
3. Observe SMS delivery to configured Forest Officer and Villager recipient groups.
