# Web Push Notification System - Setup Guide

Department of AI & ML, Sri Sairam College of Engineering

## Overview

This Web Push notification system adds browser-based alert capabilities to the existing elephant detection system. It provides:

- **Confirmation Layer**: Filters false positives using configurable thresholds
- **Alert Cooldown**: Prevents notification spam during continuous detections
- **Web Push Notifications**: Browser-based alerts for forest officers and villagers
- **Alert History**: Complete tracking of all confirmed elephant events
- **Dashboard UI**: Full management interface for alerts

## Architecture

```
Laptop Camera (Existing)
    ↓
AI Detector (Existing - NOT MODIFIED)
    ↓
CSV Logging (Existing - NOT MODIFIED)
    ↓
Camera Alert Monitor (NEW - reads CSV)
    ↓
Confirmation Layer (NEW)
    ↓
Alert Event (NEW)
    ↓
Web Push (NEW)
    ↓
Subscribed Browsers
```

## Installation

### 1. Install Required Python Packages

```bash
cd "Integrated-IoT-and-Edge-AI-Acoustic-Early-Warning-System-for-Human-Elephant-Conflict-Mitigation-main"
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your VAPID keys:

**Web Push VAPID Keys:**
- Generate using: `python -c "from py_vapid import Vapid; v = Vapid(); print(v.keys())"`
- Copy the public and private keys to `.env`

### 3. Configure Alert Settings (Optional)

Edit `alert_config.json` to customize alert behavior:

```json
{
  "confirmation_settings": {
    "confirmation_frames": 3,
    "min_confirmation_confidence": 0.50,
    "alert_cooldown_seconds": 300
  },
  "web_push_settings": {
    "enabled": true,
    "notification_ttl_seconds": 3600
  }
}
```

## Running the System

### Start the Flask Dashboard

```bash
cd "Integrated-IoT-and-Edge-AI-Acoustic-Early-Warning-System-for-Human-Elephant-Conflict-Mitigation-main"
python server.py
```

The dashboard will be available at: http://127.0.0.1:5000

### Start the Camera Detector (Existing)

```bash
cd "WelcomeScreen/fall_final"
python human_fall_detect_final_count.py
```

### Start the Camera Alert Monitor (NEW)

```bash
cd "Integrated-IoT-and-Edge-AI-Acoustic-Early-Warning-System-for-Human-Elephant-Conflict-Mitigation-main"
python camera_alert_monitor.py
```

This script monitors the CSV file and forwards detections to the alert system.

## Dashboard Features

### Alert Management Tab

Access the new "Alert Management" tab in the dashboard to:

1. **View Alert History**: See all confirmed elephant events with delivery status
2. **Monitor Alert Status**: Real-time state of the confirmation system
3. **Subscribe to Web Push**: Enable browser notifications
4. **Test Notifications**: Send test alerts to verify configuration
5. **Reset Cooldown**: For testing purposes

### Alert States

The confirmation system uses these states:

- **NO_DETECTION**: No elephants detected
- **POSSIBLE**: Elephant detected, waiting for confirmation
- **CONFIRMED**: Elephant confirmed (thresholds met)
- **ALERT_SENT**: Alert notifications sent
- **MONITORING**: Still detecting, monitoring continues

## How Alerts Work

### Confirmation Process

1. Camera detects elephant in a frame
2. Alert monitor reads CSV entry
3. Confirmation layer checks:
   - Consecutive frames (default: 3)
   - Average confidence (default: 50%)
4. If thresholds met → Alert created
5. Notifications sent to:
   - Forest Officers (Web Push)
   - Villagers (Web Push)

### Cooldown Mechanism

After an alert is sent:
- System enters cooldown (default: 300 seconds)
- New alerts blocked during cooldown
- Cooldown resets when detection ends
- Prevents notification spam

### Notification Content

**Web Push:**
```
🐘 Elephant Confirmed
Count: 2 | Confidence: 94.7%
```

## Testing

### Test Web Push

1. Open dashboard at http://127.0.0.1:5000
2. Go to "Alert Management" tab
3. Click "Subscribe" and grant permission
4. Click "Test to Forest Officers" or "Test to Villagers"

### Test Full Integration

1. Start all three components (dashboard, detector, monitor)
2. Point camera at elephant image/video
3. Wait for confirmation (3 consecutive frames)
4. Check dashboard for alert
5. Check browser notification

## Troubleshooting

### Web Push Not Working

- Verify VAPID keys are generated correctly
- Ensure browser supports Web Push (Chrome, Firefox, Edge)
- Check notification permission is granted
- Service worker must be served from HTTPS (localhost is exception)

### Alerts Not Creating

- Check camera_alert_monitor.py is running
- Verify CSV file is being written by detector
- Check Flask server is running
- Review alert_config.json settings
- Check browser console for errors

### ESP32 Issues

**ESP32 is completely out of scope for this alert system.**
- Do not modify ESP32 code
- Do not change ESP32 hardware
- ESP32 functionality remains completely separate

## Security Notes

- Never commit `.env` file to version control
- Never hardcode VAPID private key in frontend code
- VAPID private key stays on server only

## Files Added (Non-Invasive)

**New Files:**
- `alert_config.json` - Alert configuration
- `alert_history.json` - Alert event storage (auto-created)
- `notification_service.py` - Confirmation layer
- `push_service.py` - Web push integration
- `camera_alert_monitor.py` - CSV monitor
- `static/js/service-worker.js` - Push service worker
- `static/js/push_subscription.js` - Push subscription UI
- `static/js/alerts.js` - Alert management UI
- `static/css/alerts.css` - Alert styles
- `.env.example` - Environment variables template

**Modified Files:**
- `server.py` - Added alert API endpoints (only additions)
- `templates/index.html` - Added alert UI tab (only additions)
- `requirements.txt` - Added new packages

**Files NOT Touched:**
- `WelcomeScreen/fall_final/human_fall_detect_final_count.py` - Existing detector (unchanged)
- `hardware_integration/esp32_node.ino` - ESP32 code (completely untouched)
- All existing dashboard functionality (unchanged)

## Support

For issues or questions:
1. Check this README
2. Review browser console for errors
3. Check Flask server logs
4. Verify environment variables
5. Test individual components
