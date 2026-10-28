"""
Twilio Programmable Messaging Integration for Human-Elephant Conflict Mitigation System
Department of AI & ML, Sri Sairam College of Engineering

Features:
- Twilio Programmable SMS API client using the official Twilio Python SDK
- Location-based bilingual SMS messages (English + Tamil / English + Kannada)
- Dynamic elephant count from computer vision model
- Non-blocking asynchronous alert dispatching
- Frame debouncing, configurable cooldown, and count-change policies
- Absence reset interval (event lifecycle management)
- Bounded retries for transient failures (ConnectionError, Timeout)
- Secure credential masking and safe configuration endpoints
- Delivery-status callback handling (StatusCallback webhook)
"""

import os
import re
import json
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "twilio_sms_config.json")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "twilio_sms_history.json")


def mask_phone_number(phone_str: Optional[str]) -> str:
    """
    Masks a phone number for privacy in logs and UI.
    e.g. '+917094528671' -> '+91 70*** ***71'
    """
    if not phone_str:
        return "Not configured"
    cleaned = re.sub(r"[^\d+]", "", str(phone_str).strip())
    if len(cleaned) < 8:
        return cleaned[:2] + "***" + cleaned[-2:] if len(cleaned) >= 4 else "***"
    prefix = cleaned[:5]
    suffix = cleaned[-2:]
    return f"{prefix}*** ***{suffix}"


def mask_credential(cred_str: Optional[str], show_prefix: int = 4, show_suffix: int = 4) -> str:
    """
    Masks an API secret or SID for safe display in UI/logs.
    e.g. 'mock_account_sid_12345678' -> 'mock...5678'
    """
    if not cred_str:
        return "Not configured"
    s = str(cred_str).strip()
    if len(s) <= (show_prefix + show_suffix):
        return "***"
    return f"{s[:show_prefix]}...{s[-show_suffix:]}"


class BilingualTwilioMessageBuilder:
    """
    Builds location-aware bilingual emergency SMS alerts.
    - Tamil Nadu: English + Tamil
    - Karnataka: English + Kannada
    """

    @staticmethod
    def build_alert_message(
        count: int,
        location: Optional[str] = None,
        state: str = "tamil_nadu",
        timestamp_str: Optional[str] = None,
        format_type: Optional[str] = None
    ) -> str:
        """
        Constructs the exact bilingual alert message containing:
        - Emergency heading
        - Actual elephant count
        - Monitoring location
        - Detection timestamp
        - Safety instruction
        """
        format_key = (format_type or os.getenv("TWILIO_MESSAGE_FORMAT", "standard")).strip().lower()

        count_int = max(1, int(count)) if str(count).isdigit() or isinstance(count, (int, float)) else 1
        loc_str = str(location or "").strip()
        state_key = str(state or "tamil_nadu").strip().lower()

        # Format Option A: Concise Format (English + Tamil prompt-compliant)
        if format_key == "concise":
            noun_en_phrase = "Elephant" if count_int == 1 else f"{count_int} elephants"
            noun_ta_phrase = "யானை" if count_int == 1 else f"{count_int} யானைகள்"

            if loc_str and loc_str.lower() not in ("monitored area", "the monitored area", "forest border zone", "monitoring zone 1"):
                area_en = f"near {loc_str}"
                area_ta = f"{loc_str} பகுதியில்"
            else:
                area_en = "near the monitored area"
                area_ta = "கண்காணிக்கப்படும் பகுதியில்"

            time_en = f" Time: {timestamp_str}." if timestamp_str else ""
            time_ta = f" நேரம்: {timestamp_str}." if timestamp_str else ""

            return (
                f"ALERT: {noun_en_phrase} detected {area_en}.{time_en} "
                f"Please maintain a safe distance and follow local forest department instructions.\n\n"
                f"எச்சரிக்கை: {area_ta} {noun_ta_phrase} கண்டறியப்பட்டுள்ளது.{time_ta} "
                f"பாதுகாப்பான தூரத்தில் இருங்கள் மற்றும் வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றுங்கள்."
            )

        # Format Option B: Standard Structured Format (Default)
        if not timestamp_str:
            timestamp_str = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")

        display_loc = loc_str or "Forest Border Zone"
        noun_en = "elephant" if count_int == 1 else "elephants"

        if state_key in ("karnataka", "ka"):
            # Karnataka: English + Kannada
            noun_kn = "ಆನೆ" if count_int == 1 else "ಆನೆಗಳು"
            body = (
                f"🚨 ELEPHANT ALERT!\n"
                f"English: {count_int} {noun_en} detected at {display_loc}. Time: {timestamp_str}. "
                f"Please stay safe and inform the forest department.\n"
                f"ಕನ್ನಡ: {display_loc}ನಲ್ಲಿ {count_int} {noun_kn} ಪತ್ತೆಯಾಗಿವೆ. ಸಮಯ: {timestamp_str}. "
                f"ಸುರಕ್ಷಿತವಾಗಿರಿ ಮತ್ತು ಅರಣ್ಯ ಇಲಾಖೆಗೆ ಮಾಹಿತಿ ನೀಡಿ."
            )
        else:
            # Tamil Nadu (Default): English + Tamil
            noun_ta = "யானை" if count_int == 1 else "யானைகள்"
            body = (
                f"🚨 ELEPHANT ALERT!\n"
                f"English: {count_int} {noun_en} detected at {display_loc}. Time: {timestamp_str}. "
                f"Please stay safe and inform the forest department.\n"
                f"தமிழ்: {display_loc}-ல் {count_int} {noun_ta} கண்டறியப்பட்டுள்ளன. நேரம்: {timestamp_str}. "
                f"பாதுகாப்பாக இருங்கள் மற்றும் வனத்துறைக்குத் தகவல் தெரிவிக்கவும்."
            )

        return body

    @staticmethod
    def build_bilingual_sms(
        count: Optional[int] = None,
        location: Optional[str] = None,
        state: Optional[str] = "karnataka",
        confidence: Optional[float] = None,
        timestamp_str: Optional[str] = None,
        dashboard_url: Optional[str] = None,
        group: Optional[str] = "officer"
    ) -> str:
        """
        Builds one complete bilingual SMS containing English + regional language (Tamil or Kannada).
        Includes all 8 required items when available.
        """
        from android_sms_gateway import BilingualMessageBuilder
        return BilingualMessageBuilder.build_bilingual_sms(
            count=count,
            location=location,
            state=state,
            confidence=confidence,
            timestamp_str=timestamp_str,
            dashboard_url=dashboard_url,
            group=group
        )

    @staticmethod
    def calculate_segments(message: str) -> Dict[str, Any]:
        """
        Calculates SMS character length and Unicode (UCS-2) segmentation.
        Standard GSM 7-bit: 160 chars / single segment (153 chars for concatenated parts).
        Unicode (UCS-2): 70 chars / single segment (67 chars for concatenated parts).
        """
        is_unicode = any(ord(char) > 127 for char in message)
        char_count = len(message)

        if is_unicode:
            encoding = "UCS-2 (Unicode)"
            if char_count <= 70:
                segments = 1
            else:
                segments = (char_count + 66) // 67
        else:
            encoding = "GSM-7"
            if char_count <= 160:
                segments = 1
            else:
                segments = (char_count + 152) // 153

        return {
            "is_unicode": is_unicode,
            "char_count": char_count,
            "segment_count": max(1, segments),
            "encoding": encoding
        }


class TwilioSmsManager:
    """
    Manages Twilio Programmable Messaging dispatching, credentials,
    debouncing, cooldowns, and delivery-status callbacks.
    """

    def __init__(self, config_path: str = CONFIG_FILE, history_path: str = HISTORY_FILE):
        self.config_path = config_path
        self.history_path = history_path
        # Use re-entrant lock to prevent deadlocks in nested status calls
        self.lock = threading.RLock()

        # Runtime Alert State Machine
        self.incident_active = False
        self.current_count = 0
        self.last_alert_time = 0.0
        self.last_detection_time = 0.0
        self.last_message_sid = None
        self.last_message_status = "IDLE"
        self.last_error_message = None

        # Load Configuration
        self.config: Dict[str, Any] = {}
        self.history: list = []
        self._load_config()
        self._load_history()

    # --------------------------------------------------------------------------
    # Configuration & History Persistence
    # --------------------------------------------------------------------------

    def _load_config(self) -> None:
        """Loads configuration from environment variables and local JSON override"""
        # 1. Defaults from environment variables
        env_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        env_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        env_from = os.getenv("TWILIO_FROM_NUMBER", "").strip()
        env_messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID", "").strip()
        env_to = os.getenv("TWILIO_TO_NUMBER", "").strip()
        env_format = os.getenv("TWILIO_MESSAGE_FORMAT", "standard").strip().lower()
        env_callback = os.getenv("TWILIO_STATUS_CALLBACK_URL", "").strip()

        env_state = os.getenv("ALERT_MONITORING_STATE", "tamil_nadu").strip()
        env_location = os.getenv("ALERT_MONITORING_LOCATION", "Monitoring Zone 1").strip()
        env_cooldown = int(os.getenv("ALERT_SMS_COOLDOWN_SECONDS", "300"))
        env_policy = os.getenv("ALERT_COUNT_CHANGE_POLICY", "increase_only").strip()
        env_absence = int(os.getenv("ALERT_ABSENCE_RESET_SECONDS", "120"))

        self.config = {
            "enabled": True,
            "account_sid": env_sid,
            "auth_token": env_token,
            "from_number": env_from,
            "messaging_service_sid": env_messaging_service_sid,
            "to_number": env_to,
            "message_format": env_format,
            "status_callback_url": env_callback,
            "state": env_state,
            "location_name": env_location,
            "cooldown_seconds": env_cooldown,
            "count_change_policy": env_policy,
            "absence_reset_seconds": env_absence
        }

        # 2. Local JSON overrides (persists UI adjustments without committing secrets)
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    local_conf = json.load(f)
                    for k, v in local_conf.items():
                        if v is not None:
                            self.config[k] = v
            except Exception as e:
                print(f"[TWILIO-SMS] Notice: Could not read local config file: {e}")

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Saves configuration updates to local JSON file safely"""
        with self.lock:
            for k in [
                "enabled", "account_sid", "auth_token", "from_number", "messaging_service_sid",
                "to_number", "message_format", "status_callback_url", "state", "location_name",
                "cooldown_seconds", "count_change_policy", "absence_reset_seconds"
            ]:
                if k in updates and updates[k] is not None:
                    # Type sanitization
                    if k in ("cooldown_seconds", "absence_reset_seconds"):
                        try:
                            self.config[k] = max(10, int(updates[k]))
                        except (ValueError, TypeError):
                            pass
                    elif k == "enabled":
                        self.config[k] = bool(updates[k])
                    else:
                        val = str(updates[k]).strip()
                        if val or k in ("status_callback_url", "messaging_service_sid", "from_number"):
                            self.config[k] = val

            try:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2)
            except Exception as e:
                print(f"[TWILIO-SMS] Error saving config: {e}")

            return self.get_safe_status()

    def _load_history(self) -> None:
        """Loads alert dispatch history from local file"""
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
        else:
            self.history = []

    def _record_history(self, record: Dict[str, Any]) -> None:
        """Appends a dispatch record to history (bounded to last 150 items)"""
        with self.lock:
            self.history.append(record)
            if len(self.history) > 150:
                self.history = self.history[-150:]
            try:
                with open(self.history_path, "w", encoding="utf-8") as f:
                    json.dump(self.history, f, indent=2)
            except Exception as e:
                print(f"[TWILIO-SMS] Error writing history: {e}")

    # --------------------------------------------------------------------------
    # Twilio Client Factory & Validation
    # --------------------------------------------------------------------------

    def _get_twilio_client(self, sid: Optional[str] = None, token: Optional[str] = None):
        """
        Creates and returns an official Twilio REST Client instance.
        Separated for clean dependency injection and unit test mocking.
        """
        from twilio.rest import Client
        sid_val = sid or self.config.get("account_sid")
        token_val = token or self.config.get("auth_token")
        if not sid_val or not token_val:
            raise ValueError("Twilio Account SID and Auth Token must be configured")
        return Client(sid_val, token_val)

    def validate_credentials(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates Twilio credentials by making a lightweight API call to fetch account details.
        Never sends an SMS during credential validation.
        """
        sid = self.config.get("account_sid", "").strip()
        token = self.config.get("auth_token", "").strip()
        from_num = self.config.get("from_number", "").strip()
        msg_srv_sid = self.config.get("messaging_service_sid", "").strip()
        to_num = self.config.get("to_number", "").strip()

        if not sid or not token:
            return False, "Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN", {}

        if not sid.startswith("AC") or len(sid) < 30:
            return False, f"Invalid Twilio Account SID format ('{mask_credential(sid)}'). Expected starting with 'AC'", {}

        sender_configured = bool(from_num or msg_srv_sid)
        sender_warning = "" if sender_configured else " (Warning: Neither From Phone Number nor Messaging Service SID configured)"

        try:
            client = self._get_twilio_client(sid, token)
            account = client.api.accounts(sid).fetch()
            info = {
                "friendly_name": getattr(account, "friendly_name", "Twilio Account"),
                "status": getattr(account, "status", "active"),
                "type": getattr(account, "type", "Trial" if "trial" in getattr(account, "type", "").lower() else "Full"),
                "account_sid_masked": mask_credential(sid),
                "from_number_masked": mask_phone_number(from_num),
                "messaging_service_sid_masked": mask_credential(msg_srv_sid) if msg_srv_sid else "Not configured",
                "to_number_masked": mask_phone_number(to_num),
                "sender_configured": sender_configured,
                "sender_type": "messaging_service" if msg_srv_sid else ("phone_number" if from_num else "none")
            }
            return True, f"Connected to Twilio Account: {info['friendly_name']} ({info['status'].upper()}){sender_warning}", info
        except Exception as e:
            err_msg = str(e)
            # Check for common Twilio error codes
            if "20003" in err_msg or "Authenticate" in err_msg or "Authentication Error" in err_msg:
                clean_err = "Authentication Failed (Invalid Account SID or Auth Token)"
            elif "ConnectionError" in err_msg or "getaddrinfo failed" in err_msg:
                clean_err = "Twilio API Unreachable (Network / DNS error)"
            else:
                clean_err = f"Twilio API Error: {err_msg}"
            return False, clean_err, {"raw_error": err_msg}

    # --------------------------------------------------------------------------
    # Core SMS Dispatch Engine
    # --------------------------------------------------------------------------

    def send_sms(
        self,
        to_number: str,
        body: str,
        status_callback: Optional[str] = None,
        max_retries: int = 2
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Sends an SMS alert via Twilio Programmable Messaging API.
        Supports either from_number (phone number) or messaging_service_sid.
        Includes bounded retries for transient network issues.
        Never retries on client errors (HTTP 4xx / Twilio 2xxxx).
        """
        sid = self.config.get("account_sid", "").strip()
        token = self.config.get("auth_token", "").strip()
        from_number = self.config.get("from_number", "").strip()
        messaging_service_sid = self.config.get("messaging_service_sid", "").strip()
        callback_url = status_callback or self.config.get("status_callback_url", "").strip() or None

        # Clean recipient phone number
        cleaned_to = re.sub(r"[^\d+]", "", str(to_number or "").strip())
        if not cleaned_to:
            return False, "Recipient phone number is missing", {}

        if not sid or not token:
            return False, "Twilio configuration incomplete (SID or Token missing)", {}

        if not from_number and not messaging_service_sid:
            return False, "Twilio configuration incomplete: Neither From Phone Number nor Messaging Service SID is configured", {}

        # Pre-calculate segmentation metrics
        seg_info = BilingualTwilioMessageBuilder.calculate_segments(body)

        sender_display = mask_credential(messaging_service_sid) if messaging_service_sid else mask_phone_number(from_number)
        sender_type = "messaging_service" if messaging_service_sid else "phone_number"

        record = {
            "timestamp": datetime.now().isoformat(),
            "to": mask_phone_number(cleaned_to),
            "from": sender_display,
            "sender_type": sender_type,
            "body_snippet": body[:80] + "..." if len(body) > 80 else body,
            "char_count": seg_info["char_count"],
            "segment_count": seg_info["segment_count"],
            "encoding": seg_info["encoding"],
            "status": "QUEUED",
            "message_sid": None,
            "error_message": None,
            "attempts": 0
        }

        # Bounded retry loop for transient failures
        attempt = 0
        last_exception = None

        while attempt <= max_retries:
            attempt += 1
            record["attempts"] = attempt
            try:
                client = self._get_twilio_client(sid, token)
                params: Dict[str, Any] = {
                    "body": body,
                    "to": cleaned_to
                }
                if messaging_service_sid:
                    params["messaging_service_sid"] = messaging_service_sid
                elif from_number:
                    params["from_"] = from_number

                if callback_url:
                    params["status_callback"] = callback_url

                # Twilio SDK call
                msg_resource = client.messages.create(**params)

                msg_sid = getattr(msg_resource, "sid", "SM_UNKNOWN")
                msg_status = getattr(msg_resource, "status", "queued")

                record["message_sid"] = msg_sid
                record["status"] = msg_status.upper()
                self.last_message_sid = msg_sid
                self.last_message_status = msg_status.upper()
                self.last_error_message = None

                self._record_history(record)
                return True, f"Message submitted to Twilio (SID: {msg_sid}, Status: {msg_status.upper()})", record

            except Exception as e:
                last_exception = e
                err_str = str(e)

                # Check if it's a non-retryable Twilio client error
                is_client_error = any(code in err_str for code in [
                    "21608",  # Unverified trial number
                    "21211",  # Invalid phone number
                    "21614",  # Not a mobile number
                    "20003",  # Authentication error
                    "20429",  # Rate limit
                    "21604",  # Tracking/carrier restriction
                    "21612",  # Cannot send to regional destination
                    "21703",  # Messaging Service SID not found
                    "21704",  # Messaging Service has no phone numbers
                    "21603",  # From number not a valid Twilio number
                    "21606"   # From number not SMS capable
                ])

                if is_client_error or attempt > max_retries:
                    break

                # Exponential backoff for transient network errors
                time.sleep(1.0 * attempt)

        # Handle failure
        fail_msg = str(last_exception)
        if "21608" in fail_msg:
            friendly_err = "Twilio Trial Restriction: Recipient number is not verified in Twilio Console (twilio.com/console/phone-numbers/verified)"
        elif "21211" in fail_msg:
            friendly_err = f"Invalid 'To' phone number format: {mask_phone_number(cleaned_to)}"
        elif "21614" in fail_msg:
            friendly_err = f"Recipient phone number cannot receive SMS (Landline or invalid type): {mask_phone_number(cleaned_to)}"
        elif "20003" in fail_msg:
            friendly_err = "Authentication Error: Invalid Twilio Account SID or Auth Token"
        elif "20429" in fail_msg:
            friendly_err = "Twilio Rate Limit Exceeded (Too many requests)"
        elif "21703" in fail_msg:
            friendly_err = f"Twilio Messaging Service Error: Messaging Service SID '{mask_credential(messaging_service_sid)}' not found or invalid"
        elif "21704" in fail_msg:
            friendly_err = "Twilio Messaging Service Error: No phone numbers or senders in Messaging Service pool"
        elif "21603" in fail_msg:
            friendly_err = f"Twilio Sender Error: From number '{mask_phone_number(from_number)}' is not a valid Twilio phone number on this account"
        elif "21606" in fail_msg:
            friendly_err = f"Twilio Sender Error: From number '{mask_phone_number(from_number)}' is not SMS-capable"
        else:
            friendly_err = f"Twilio API Error: {fail_msg}"

        record["status"] = "FAILED"
        record["error_message"] = friendly_err
        self.last_message_status = "FAILED"
        self.last_error_message = friendly_err

        self._record_history(record)
        return False, friendly_err, record

    # --------------------------------------------------------------------------
    # Detection Pipeline Integration & State Machine
    # --------------------------------------------------------------------------

    def process_detection_sync(
        self,
        elephant_count: int,
        confidence: float = 0.0,
        location: Optional[str] = None,
        timestamp: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Evaluates an elephant detection against cooldown and policy state machine.
        Dispatches SMS alert if criteria are satisfied.
        """
        if not self.config.get("enabled", True):
            return False, "Twilio SMS alerting is disabled in settings"

        sid = self.config.get("account_sid", "").strip()
        token = self.config.get("auth_token", "").strip()
        from_num = self.config.get("from_number", "").strip()
        msg_srv_sid = self.config.get("messaging_service_sid", "").strip()
        to_number = self.config.get("to_number", "").strip()

        if not sid or not token or not to_number:
            return False, "Twilio credentials or recipient number not configured"

        if not from_num and not msg_srv_sid:
            return False, "Twilio sender not configured (neither from_number nor messaging_service_sid)"

        count = 0
        try:
            if elephant_count is not None:
                count = int(float(elephant_count))
        except (ValueError, TypeError):
            count = 0

        now = time.time()
        cooldown = self.config.get("cooldown_seconds", 300)
        policy = self.config.get("count_change_policy", "increase_only")
        absence_reset = self.config.get("absence_reset_seconds", 120)

        with self.lock:
            # 1. No Elephants Detected
            if count <= 0:
                if self.incident_active:
                    time_since_detection = now - self.last_detection_time
                    if time_since_detection >= absence_reset:
                        self.incident_active = False
                        self.current_count = 0
                        print(f"[TWILIO-SMS] Incident closed: No elephants detected for >{absence_reset}s.")
                return False, "No elephants detected"

            # 2. Elephants Detected
            self.last_detection_time = now
            elapsed_since_last_alert = now - self.last_alert_time

            # Case A: Brand New Incident
            if not self.incident_active:
                self.incident_active = True
                self.current_count = count
                should_alert = True
                trigger_reason = f"Initial incident detection ({count} elephants)"

            # Case B: Ongoing Incident within Cooldown Window
            elif elapsed_since_last_alert < cooldown:
                if policy == "increase_only" and count > self.current_count:
                    should_alert = True
                    trigger_reason = f"Elephant count increased ({self.current_count} -> {count})"
                    self.current_count = count
                elif policy == "always" and count != self.current_count:
                    should_alert = True
                    trigger_reason = f"Elephant count changed ({self.current_count} -> {count})"
                    self.current_count = count
                else:
                    return False, f"Duplicate suppressed (Cooldown active: {int(cooldown - elapsed_since_last_alert)}s remaining)"

            # Case C: Ongoing Incident after Cooldown Expired
            else:
                should_alert = True
                trigger_reason = f"Periodic alert after cooldown expired ({count} elephants)"
                self.current_count = count

            if not should_alert:
                return False, "Suppressed by state machine"

            self.last_alert_time = now

        # Build bilingual message
        loc_name = location or self.config.get("location_name", "Monitoring Zone 1")
        state_name = self.config.get("state", "tamil_nadu")
        format_type = self.config.get("message_format", "standard")
        body = BilingualTwilioMessageBuilder.build_alert_message(
            count=count,
            location=loc_name,
            state=state_name,
            timestamp_str=timestamp,
            format_type=format_type
        )

        print(f"[TWILIO-SMS] Triggering SMS dispatch: {trigger_reason}")
        success, msg, record = self.send_sms(to_number=to_number, body=body)
        return success, msg

    def process_detection_async(
        self,
        elephant_count: int,
        confidence: float = 0.0,
        location: Optional[str] = None,
        timestamp: Optional[str] = None
    ) -> None:
        """Dispatches SMS evaluation in a non-blocking background daemon thread"""
        t = threading.Thread(
            target=self.process_detection_sync,
            args=(elephant_count, confidence, location, timestamp),
            daemon=True
        )
        t.start()

    # --------------------------------------------------------------------------
    # Status Callback Webhook
    # --------------------------------------------------------------------------

    def handle_status_callback(self, form_data: Dict[str, Any]) -> bool:
        """
        Processes Twilio delivery status callback webhooks.
        Updates status ('delivered', 'undelivered', 'failed', 'sent') in history.
        """
        msg_sid = form_data.get("MessageSid") or form_data.get("SmsSid")
        msg_status = form_data.get("MessageStatus") or form_data.get("SmsStatus")
        error_code = form_data.get("ErrorCode")

        if not msg_sid or not msg_status:
            return False

        with self.lock:
            updated = False
            for rec in reversed(self.history):
                if rec.get("message_sid") == msg_sid:
                    rec["status"] = msg_status.upper()
                    if error_code:
                        rec["error_code"] = error_code
                    rec["callback_received_at"] = datetime.now().isoformat()
                    updated = True
                    break

            if msg_sid == self.last_message_sid:
                self.last_message_status = msg_status.upper()
                if error_code:
                    self.last_error_message = f"Delivery Error Code: {error_code}"

            if updated:
                try:
                    with open(self.history_path, "w", encoding="utf-8") as f:
                        json.dump(self.history, f, indent=2)
                except Exception as e:
                    print(f"[TWILIO-SMS] Error updating history from webhook: {e}")

        return True

    # --------------------------------------------------------------------------
    # Safe Dashboard Status Representation
    # --------------------------------------------------------------------------

    def get_safe_status(self) -> Dict[str, Any]:
        """
        Returns full configuration and status with strict masking of secrets.
        Never exposes Account SID or Auth Token in plain text.
        """
        sid = self.config.get("account_sid", "")
        token = self.config.get("auth_token", "")
        from_num = self.config.get("from_number", "")
        msg_srv_sid = self.config.get("messaging_service_sid", "")
        to_num = self.config.get("to_number", "")

        sender_configured = bool(from_num or msg_srv_sid)
        is_configured = bool(sid and token and sender_configured and to_num)

        return {
            "enabled": self.config.get("enabled", True),
            "is_configured": is_configured,
            "sender_configured": sender_configured,
            "account_sid_masked": mask_credential(sid, 4, 4),
            "auth_token_masked": "••••••••••••••••" if token else "Not configured",
            "from_number_masked": mask_phone_number(from_num),
            "messaging_service_sid_masked": mask_credential(msg_srv_sid, 4, 4) if msg_srv_sid else "Not configured",
            "to_number_masked": mask_phone_number(to_num),
            "from_number_raw": from_num,  # Needed for sender selection / display
            "messaging_service_sid_raw": msg_srv_sid,
            "message_format": self.config.get("message_format", "standard"),
            "state": self.config.get("state", "tamil_nadu"),
            "location_name": self.config.get("location_name", "Monitoring Zone 1"),
            "cooldown_seconds": self.config.get("cooldown_seconds", 300),
            "count_change_policy": self.config.get("count_change_policy", "increase_only"),
            "absence_reset_seconds": self.config.get("absence_reset_seconds", 120),
            "status_callback_url": self.config.get("status_callback_url", ""),
            "incident_active": self.incident_active,
            "current_count": self.current_count,
            "last_message_sid": self.last_message_sid,
            "last_message_status": self.last_message_status,
            "last_error_message": self.last_error_message
        }


# Global Singleton
_TWILIO_SMS_MANAGER_INSTANCE = None

def get_twilio_sms_manager() -> TwilioSmsManager:
    global _TWILIO_SMS_MANAGER_INSTANCE
    if _TWILIO_SMS_MANAGER_INSTANCE is None:
        _TWILIO_SMS_MANAGER_INSTANCE = TwilioSmsManager()
    return _TWILIO_SMS_MANAGER_INSTANCE
