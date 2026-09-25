"""
Local Baileys WhatsApp Notification Service
Department of AI & ML, Sri Sairam College of Engineering

Sends customized WhatsApp alert notifications ONLY to configured recipient (+917094528671).
Uses local Baileys Node.js microservice running on http://localhost:3001.
NO Twilio dependencies. NO Evolution API dependencies. NO paid WhatsApp APIs.
"""

import os
import json
import base64
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

# Single designated recipient for testing phase
DEFAULT_RECIPIENT = "+917094528671"
DEFAULT_SERVICE_URL = "http://localhost:3001"

# Cooldown duration: Once an elephant alert is sent, block further alerts for this duration
WHATSAPP_COOLDOWN_SECONDS = int(os.getenv('WHATSAPP_COOLDOWN_SECONDS', '300'))  # Default: 300 seconds (5 minutes)
LAST_ALERT_SENT_TIMESTAMP = 0

def get_whatsapp_recipient():
    """Returns the single configured WhatsApp recipient (+917094528671)"""
    recipient = os.getenv('WHATSAPP_RECIPIENT', DEFAULT_RECIPIENT).strip()
    return recipient if recipient else DEFAULT_RECIPIENT

def get_service_url():
    """Returns the local Baileys microservice URL (default: http://localhost:3001)"""
    url = os.getenv('WHATSAPP_SERVICE_URL', DEFAULT_SERVICE_URL).strip().rstrip('/')
    return url if url else DEFAULT_SERVICE_URL

def check_alert_cooldown():
    """
    Check if the notification system is in cooldown.
    Once an alert is sent, further alerts are blocked for WHATSAPP_COOLDOWN_SECONDS.
    Returns (is_blocked: bool, remaining_seconds: float)
    """
    import time
    global LAST_ALERT_SENT_TIMESTAMP
    now = time.time()
    
    # 1. Check in-memory timestamp
    if LAST_ALERT_SENT_TIMESTAMP > 0:
        elapsed = now - LAST_ALERT_SENT_TIMESTAMP
        if elapsed < WHATSAPP_COOLDOWN_SECONDS:
            return True, WHATSAPP_COOLDOWN_SECONDS - elapsed

    # 2. Check Supabase to maintain cooldown across server restarts
    try:
        from supabase_client import get_supabase_admin_client
        sb = get_supabase_admin_client()
        res = sb.table('alerts')\
            .select('sent_at')\
            .eq('alert_type', 'WHATSAPP')\
            .eq('status', 'sent')\
            .not_.is_('sent_at', 'null')\
            .order('sent_at', desc=True)\
            .limit(1)\
            .execute()
        if res.data and res.data[0].get('sent_at'):
            last_dt = datetime.fromisoformat(res.data[0]['sent_at'].replace('Z', '+00:00'))
            now_dt = datetime.now(timezone.utc)
            db_elapsed = (now_dt - last_dt).total_seconds()
            if db_elapsed < WHATSAPP_COOLDOWN_SECONDS:
                LAST_ALERT_SENT_TIMESTAMP = now - db_elapsed
                return True, WHATSAPP_COOLDOWN_SECONDS - db_elapsed
    except Exception as e:
        print(f"[WHATSAPP] Cooldown database check note: {e}")

    return False, 0.0

def reset_alert_cooldown():
    """Manually unblock/reset cooldown for testing or emergency override"""
    global LAST_ALERT_SENT_TIMESTAMP
    LAST_ALERT_SENT_TIMESTAMP = 0
    print("[WHATSAPP] Alert cooldown reset. Next alert will send immediately.")

def is_detection_already_alerted(detection_id):
    """
    Check Supabase alerts table to prevent duplicate WhatsApp notifications
    for the exact same detection_id.
    """
    if not detection_id:
        return False
    try:
        from supabase_client import get_supabase_admin_client
        sb = get_supabase_admin_client()
        res = sb.table('alerts')\
            .select('id, status')\
            .eq('detection_id', str(detection_id))\
            .eq('alert_type', 'WHATSAPP')\
            .eq('status', 'sent')\
            .execute()
        return len(res.data) > 0
    except Exception as e:
        print(f"[WHATSAPP] Note on idempotency check: {e}")
        return False

def record_alert_in_supabase(detection_id, device_id, recipient, message, status, provider_message_id=None, error_message=None):
    """
    Record WhatsApp notification outcome in Supabase alerts table.
    Ensures device_id conforms to foreign key constraint (ESP32-NODE-01 or ESP32-NODE-02).
    """
    try:
        from supabase_client import get_supabase_admin_client
        sb = get_supabase_admin_client()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        valid_dev = str(device_id) if device_id in ("ESP32-NODE-01", "ESP32-NODE-02") else "ESP32-NODE-01"
        
        record = {
            "detection_id": str(detection_id) if detection_id else None,
            "device_id": valid_dev,
            "alert_type": "WHATSAPP",
            "recipient": recipient,
            "message": message,
            "status": status,  # "sent" or "failed"
            "provider_message_id": str(provider_message_id) if provider_message_id else None,
            "created_at": now_iso,
            "sent_at": now_iso if status == "sent" else None,
            "error_message": str(error_message) if error_message else None
        }
        res = sb.table('alerts').insert(record).execute()
        print(f"[WHATSAPP] Saved alert record to Supabase (status={status}): {recipient}")
        return res.data
    except Exception as e:
        print(f"[WHATSAPP] Error saving alert record to Supabase: {e}")
        return None

def format_custom_elephant_message(detection_data):
    """
    Format personalized message for Varun using real Supabase detection values
    """
    elephant_count = detection_data.get('elephant_count', 1)
    
    # Confidence percentage
    conf = detection_data.get('confidence', 0.0)
    conf_pct = round(conf * 100 if conf <= 1 else conf, 1)
    
    # Location
    location = detection_data.get('location') or detection_data.get('location_name') or "Bannerghatta Forest Perimeter"
    device_id = detection_data.get('device_id') or "ESP32-NODE-01"
    
    # Timestamp formatting
    raw_time = detection_data.get('timestamp') or datetime.now().isoformat()
    try:
        dt = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
        time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        time_str = str(raw_time)
        
    lat = detection_data.get('latitude', 12.8224)
    lng = detection_data.get('longitude', 77.5770)
    
    message = f"""🚨 ELEPHANT ALERT

Hello Varun,

An elephant has been detected by the Elephant Monitoring System.

🐘 Elephant Count: {elephant_count}
🎯 AI Confidence: {conf_pct}%
📍 Location: {location}
📡 Device: {device_id}
🕐 Time: {time_str}
🌐 GPS: {lat}, {lng}

Please check the monitoring dashboard for more details.

— Elephant Monitoring System"""
    return message

def format_custom_image_caption(detection_data):
    """
    Format concise caption for elephant image detection
    """
    elephant_count = detection_data.get('elephant_count', 1)
    conf = detection_data.get('confidence', 0.0)
    conf_pct = round(conf * 100 if conf <= 1 else conf, 1)
    location = detection_data.get('location') or detection_data.get('location_name') or "Bannerghatta Forest Perimeter"
    
    raw_time = detection_data.get('timestamp') or datetime.now().isoformat()
    try:
        dt = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
        time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        time_str = str(raw_time)

    return f"""🚨 ELEPHANT ALERT

Hello Varun,

🐘 Count: {elephant_count}
🎯 Confidence: {conf_pct}%
📍 Location: {location}
🕐 Time: {time_str}"""

def send_local_baileys_whatsapp(message_text, image_path_or_filename=None, detection_id=None, device_id=None, caption=None):
    """
    Send WhatsApp message using local Node.js + Baileys service (http://localhost:3001)
    Restricted strictly to configured recipient (+917094528671).
    """
    recipient = get_whatsapp_recipient()
    service_url = get_service_url()
    
    # Check if image exists
    resolved_image = None
    if image_path_or_filename:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        alt_dirs = [
            os.path.abspath(image_path_or_filename),
            os.path.abspath(os.path.join(base_dir, '..', 'WelcomeScreen', 'fall_final', 'detected_elephants', os.path.basename(image_path_or_filename))),
            os.path.abspath(os.path.join(base_dir, 'static', 'detections', os.path.basename(image_path_or_filename)))
        ]
        for p in alt_dirs:
            if os.path.exists(p):
                resolved_image = p
                break

    # If image is available, attempt /send-image first
    if resolved_image:
        try:
            image_endpoint = f"{service_url}/send-image"
            payload = {
                "to": recipient,
                "image_path": resolved_image,
                "caption": caption if caption else message_text
            }
            print(f"[WHATSAPP] Sending image alert to {recipient} via {image_endpoint}...")
            resp = requests.post(image_endpoint, json=payload, timeout=15)
            if resp.status_code == 200:
                res_data = resp.json()
                provider_id = res_data.get('messageId', 'sent')
                print(f"[WHATSAPP] Image alert delivered successfully! (ID: {provider_id})")
                record_alert_in_supabase(
                    detection_id=detection_id,
                    device_id=device_id,
                    recipient=recipient,
                    message=message_text,
                    status="sent",
                    provider_message_id=provider_id
                )
                return True, provider_id
            else:
                print(f"[WHATSAPP] Image send returned HTTP {resp.status_code}: {resp.text[:150]}")
        except Exception as ie:
            print(f"[WHATSAPP] Image send failed, falling back to text: {ie}")

    # Text message send
    try:
        msg_endpoint = f"{service_url}/send-message"
        payload = {
            "to": recipient,
            "message": message_text
        }
        print(f"[WHATSAPP] Sending text alert to {recipient} via {msg_endpoint}...")
        resp = requests.post(msg_endpoint, json=payload, timeout=12)
        if resp.status_code == 200:
            res_data = resp.json()
            provider_id = res_data.get('messageId', 'sent')
            print(f"[WHATSAPP] Text alert delivered successfully! (ID: {provider_id})")
            record_alert_in_supabase(
                detection_id=detection_id,
                device_id=device_id,
                recipient=recipient,
                message=message_text,
                status="sent",
                provider_message_id=provider_id
            )
            return True, provider_id
        else:
            err = f"WhatsApp service error (HTTP {resp.status_code}): {resp.text[:150]}"
            print(f"[WHATSAPP] {err}")
            record_alert_in_supabase(
                detection_id=detection_id,
                device_id=device_id,
                recipient=recipient,
                message=message_text,
                status="failed",
                error_message=err
            )
            return False, err
    except Exception as e:
        err = f"Failed to connect to local WhatsApp service at {service_url}: {str(e)}"
        print(f"[WHATSAPP] {err}")
        record_alert_in_supabase(
            detection_id=detection_id,
            device_id=device_id,
            recipient=recipient,
            message=message_text,
            status="failed",
            error_message=err
        )
        return False, err

# Legacy alias
send_evolution_whatsapp = send_local_baileys_whatsapp

def send_confirmed_elephant_whatsapp(detection_data):
    """
    Entry point for confirmed elephant detections:
    1. Validates ELEPHANT_DETECTED status
    2. Enforces idempotency via detection_id
    3. Sends customized WhatsApp to +917094528671
    """
    detection_type = detection_data.get('detection') or detection_data.get('event_type') or 'ELEPHANT_DETECTED'
    if detection_type not in ('ELEPHANT_DETECTED', 'ELEPHANT_CONFIRMED'):
        print("[WHATSAPP] Skipping notification - event is SAFE (no elephant confirmed)")
        return False, "Not an elephant detection"

    # 1. Idempotency check: exactly one WhatsApp message per detection_id
    if detection_id and is_detection_already_alerted(detection_id):
        print(f"[WHATSAPP] Blocked: Duplicate alert prevented for detection {detection_id}")
        return False, "Duplicate alert prevented"

    # 2. Cooldown block: Once a message is sent, block all subsequent alerts for cooldown period
    is_blocked, remaining = check_alert_cooldown()
    if is_blocked:
        print(f"[WHATSAPP] BLOCKED: Notification cooldown active ({remaining:.1f}s remaining). Suppressing duplicate WhatsApp spam.")
        return False, f"Alert blocked: Cooldown active ({remaining:.1f}s remaining)"

    # Format real detection message
    message = format_custom_elephant_message(detection_data)
    caption = format_custom_image_caption(detection_data)
    img_path = detection_data.get('image_path') or detection_data.get('image_name')
    dev_id = detection_data.get('device_id', 'ESP32-NODE-01')

    success, prov_id = send_local_baileys_whatsapp(
        message_text=message,
        image_path_or_filename=img_path,
        detection_id=detection_id,
        device_id=dev_id,
        caption=caption
    )

    if success:
        import time
        global LAST_ALERT_SENT_TIMESTAMP
        LAST_ALERT_SENT_TIMESTAMP = time.time()
        print(f"[WHATSAPP] Alert delivered. Blocking further alerts for {WHATSAPP_COOLDOWN_SECONDS}s.")

    return success, prov_id

def send_test_whatsapp():
    """
    Sends safe test message ONLY to +917094528671 without creating a fake elephant detection.
    """
    recipient = get_whatsapp_recipient()
    service_url = get_service_url()
    
    test_message = """🧪 TEST MESSAGE

Hello Varun,

This is a test message from the Elephant Monitoring System.

Your local WhatsApp notification service is working correctly.

— Elephant Monitoring System"""

    try:
        # Check /test-whatsapp first or /send-message
        test_endpoint = f"{service_url}/send-message"
        payload = {
            "to": recipient,
            "message": test_message
        }
        print(f"[WHATSAPP] Dispatching test notification to {recipient} via {test_endpoint}...")
        resp = requests.post(test_endpoint, json=payload, timeout=12)
        
        if resp.status_code == 200:
            res_json = resp.json()
            provider_id = res_json.get('messageId', 'sent')
            record_alert_in_supabase(
                detection_id=None,
                device_id="ESP32-NODE-01",
                recipient=recipient,
                message=test_message,
                status="sent",
                provider_message_id=provider_id
            )
            return True, f"Test WhatsApp sent successfully to {recipient} (ID: {provider_id})"
        else:
            err = f"Local WhatsApp service returned HTTP {resp.status_code}: {resp.text[:150]}"
            record_alert_in_supabase(
                detection_id=None,
                device_id="ESP32-NODE-01",
                recipient=recipient,
                message=test_message,
                status="failed",
                error_message=err
            )
            return False, err
    except Exception as e:
        err = f"Failed to connect to local WhatsApp service at {service_url}: {str(e)}"
        record_alert_in_supabase(
            detection_id=None,
            device_id="ESP32-NODE-01",
            recipient=recipient,
            message=test_message,
            status="failed",
            error_message=err
        )
        return False, err
