"""
Android-Based SIM SMS Gateway Integration (TextBee)
Department of AI & ML, Sri Sairam College of Engineering

Features:
- Free-tier Android SIM SMS Gateway via TextBee API (https://textbee.dev)
- Sends automated SMS directly from user's personal Android phone SIM card to recipient phone
- Dynamic elephant count from computer vision detection model (SSD MobileNet v3 / Edge-AI Camera)
- Location-based bilingual SMS messages:
    * Tamil Nadu: English + Tamil in same SMS
    * Karnataka: English + Kannada in same SMS
- Robust frame debouncing, configurable alert cooldown, and count-change policies
- Absence reset interval (event lifecycle management)
- Thread-safe, non-blocking asynchronous dispatch
- Strict credential masking and safe configuration endpoints
- Real delivery verification distinguishing gateway queueing from device transmission
"""

import os
import re
import json
import time
import uuid
import threading
import ipaddress
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List, Sequence
from urllib.parse import urlparse
import requests
from dotenv import load_dotenv

import smsgate_client
from smsgate_client import (
    SMSGateClient,
    GatewayError,
    GatewayUnavailable,
    GatewayTimeout,
    GatewayServerError,
    GatewayAuthError,
    GatewayRejected,
    call_with_retries,
)

load_dotenv()

# ==============================================================================
# PROVIDER DOCUMENTATION & SPECIFICATIONS
# ==============================================================================
# Primary Default Provider: SMSGate (SMS Gateway for Android, Local Server mode)
# Documentation: https://docs.sms-gate.app
# Transport: Local Android phone running SMS Gateway for Android app
#
# Secondary Provider (Legacy): TextBee (https://textbee.dev)
# Retained for backward compatibility; unreachable unless provider="textbee" set.
# ==============================================================================

TEXTBEE_BASE_URL = "https://api.textbee.dev/api/v1"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "android_sms_config.json")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "android_sms_history.json")


def validate_smsgate_url(url: Optional[str], allow_public: Optional[bool] = None) -> Tuple[bool, str]:
    """
    Validates that SMSGATE_BASE_URL is http(s) and points to a private/loopback/CGNAT
    or .local/.lan host unless allow_public is True.
    """
    if not url or not isinstance(url, str):
        return False, "Base URL is empty or not a string."

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False, f"Base URL scheme must be http or https, got '{parsed.scheme}'."

    hostname = parsed.hostname
    if not hostname:
        return False, "Base URL is missing a valid hostname or IP address."

    if allow_public is None:
        allow_public_env = os.getenv("SMSGATE_ALLOW_PUBLIC_HOST", "").lower().strip()
        allow_public = allow_public_env in ("true", "1", "yes")

    if allow_public:
        return True, "Public gateway host allowed by configuration."

    host_lower = hostname.lower()
    if host_lower == "localhost" or host_lower.endswith(".local") or host_lower.endswith(".lan"):
        return True, f"Local host '{hostname}' accepted."

    try:
        ip = ipaddress.ip_address(host_lower)
        if ip.is_loopback or ip.is_private:
            return True, f"Private/loopback IP '{ip}' accepted."
        cgnat = ipaddress.ip_network("100.64.0.0/10")
        if ip in cgnat:
            return True, f"CGNAT IP '{ip}' accepted."
        if ip.is_global:
            return False, f"Public IP address '{ip}' is rejected unless SMSGATE_ALLOW_PUBLIC_HOST=true."
    except ValueError:
        return False, f"Host '{hostname}' rejected: must be private IP, loopback, CGNAT, or .local/.lan domain unless SMSGATE_ALLOW_PUBLIC_HOST=true."

    return False, f"Host '{hostname}' is not a permitted private address."


def is_valid_e164(phone: Optional[str]) -> bool:
    """Checks if a phone number strictly conforms to E.164 format (+<country><national>)."""
    if not phone or not isinstance(phone, str):
        return False
    cleaned = re.sub(r"[\s\-()]", "", phone.strip())
    return bool(re.match(r"^\+[1-9]\d{6,14}$", cleaned))


def normalize_to_e164(phone: Optional[str]) -> Optional[str]:
    """Normalizes phone string to E.164 if possible, defaulting 10 digits to +91."""
    if not phone:
        return None
    cleaned = re.sub(r"[^\d+]", "", str(phone).strip())
    if not cleaned:
        return None
    if not cleaned.startswith("+"):
        if len(cleaned) == 10:
            cleaned = f"+91{cleaned}"
        else:
            cleaned = f"+{cleaned}"
    if is_valid_e164(cleaned):
        return cleaned
    return None



def mask_phone_number(phone_str: Optional[str]) -> str:
    """
    Masks a phone number for privacy in logs and UI.
    e.g. '+919876543210' -> '+91 98*** ***10'
    """
    if not phone_str:
        return "Not configured"
    cleaned = re.sub(r"[^\d+]", "", str(phone_str).strip())
    if not cleaned:
        return "Not configured"
    
    # Handle with country code
    has_plus = cleaned.startswith("+")
    digits = cleaned[1:] if has_plus else cleaned
    
    if len(digits) >= 10:
        cc = digits[:-10]
        core = digits[-10:]
        prefix = f"+{cc} " if cc else ("+" if has_plus else "")
        return f"{prefix}{core[:2]}*** ***{core[-2:]}"
    elif len(digits) > 4:
        return f"*** ***{digits[-2:]}"
    return "••••"


def mask_api_key(api_key: Optional[str]) -> str:
    """Masks secret API key for UI display."""
    if not api_key:
        return ""
    key = str(api_key).strip()
    if len(key) <= 8:
        return "••••••••"
    return key[:4] + "••••••••" + key[-4:]


class BilingualMessageBuilder:
    """
    Constructs high-priority bilingual SMS messages for human-elephant conflict mitigation.
    Supported states / languages:
      - 'tamil_nadu': English + Tamil in same SMS
      - 'karnataka': English + Kannada in same SMS
    """

    SUPPORTED_STATES = ["tamil_nadu", "karnataka"]

    @classmethod
    def format_timestamp(cls, dt: Optional[datetime] = None) -> str:
        """Formats timestamp into clean 12-hour format: '25-10-2026, 03:45 PM'"""
        if dt is None:
            dt = datetime.now()
        day = dt.strftime("%d-%m-%Y")
        hour_min = dt.strftime("%I:%M %p")
        return f"{day}, {hour_min}"

    @classmethod
    def calculate_segments(cls, message: str) -> Dict[str, Any]:
        """
        Calculates SMS character length and Unicode (UCS-2) segmentation.
        Standard GSM 7-bit: 160 chars for single segment (153 chars for concatenated parts).
        Unicode (UCS-2): 70 chars for single segment (67 chars for concatenated parts).
        """
        is_unicode = any(ord(char) > 127 for char in message)
        char_count = len(message)

        if is_unicode:
            encoding = "UCS-2 (Unicode)"
            if char_count <= 70:
                segments = 1
                chars_per_segment = 70
            else:
                segments = (char_count + 66) // 67
                chars_per_segment = 67
        else:
            encoding = "GSM-7"
            if char_count <= 160:
                segments = 1
                chars_per_segment = 160
            else:
                segments = (char_count + 152) // 153
                chars_per_segment = 153

        return {
            "is_unicode": is_unicode,
            "encoding": encoding,
            "char_count": char_count,
            "segments": segments,
            "chars_per_segment": chars_per_segment
        }

    @classmethod
    def build_bilingual_sms(
        cls,
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
        Includes all 8 required items when available:
        1. English elephant detection alert.
        2. Tamil or Kannada translation of the alert.
        3. Elephant count (when available).
        4. Detection location or zone.
        5. Date and time of detection.
        6. Detection confidence percentage (when available).
        7. Dashboard link (when available).
        8. Appropriate safety instructions in both languages.
        """
        normalized_state = (state or "").lower().strip()
        if normalized_state not in cls.SUPPORTED_STATES:
            if "tamil" in normalized_state or normalized_state == "tn":
                normalized_state = "tamil_nadu"
            else:
                normalized_state = "karnataka"

        clean_loc = (location or "Monitored Wildlife Corridor").strip()
        time_display = timestamp_str or cls.format_timestamp()

        # Handle count
        count_val = None
        if count is not None:
            try:
                count_val = int(count)
                if count_val <= 0:
                    count_val = None
            except (ValueError, TypeError):
                count_val = None

        # Handle confidence
        conf_pct = None
        if confidence is not None:
            try:
                conf_float = float(confidence)
                if 0.0 < conf_float <= 1.0:
                    conf_pct = int(round(conf_float * 100))
                elif conf_float > 1.0:
                    conf_pct = int(round(conf_float))
            except (ValueError, TypeError):
                conf_pct = None

        # Build English clauses
        if count_val is not None:
            if count_val == 1:
                en_alert = f"ELEPHANT ALERT! An elephant has been detected near {clean_loc}. Count: 1."
                en_safety = "Avoid approaching the elephant. Follow forest department instructions."
            else:
                en_alert = f"ELEPHANT ALERT! {count_val} elephants have been detected near {clean_loc}. Count: {count_val}."
                en_safety = "Avoid approaching elephants. Follow forest department instructions."
        else:
            en_alert = f"ELEPHANT ALERT! An elephant has been detected near {clean_loc}."
            en_safety = "Avoid approaching the elephant. Follow forest department instructions."

        en_conf = f" Confidence: {conf_pct}%." if conf_pct is not None else ""
        en_time = f" Time: {time_display}."
        en_dash = f" View details: {dashboard_url}" if dashboard_url else ""

        english_body = f"{en_alert}{en_conf}{en_time} {en_safety}{en_dash}".strip()

        # Build Regional Language clauses
        if normalized_state == "tamil_nadu":
            # Tamil Nadu: English + Tamil in same SMS
            if count_val is not None:
                if count_val == 1:
                    ta_alert = f"யானை எச்சரிக்கை! {clean_loc} அருகே 1 யானை கண்டறியப்பட்டுள்ளது."
                    ta_safety = "யானையை நெருங்க வேண்டாம். வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றவும்."
                else:
                    ta_alert = f"யானை எச்சரிக்கை! {clean_loc} அருகே {count_val} யானைகள் கண்டறியப்பட்டுள்ளன."
                    ta_safety = "யானைகளை நெருங்க வேண்டாம். வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றவும்."
            else:
                ta_alert = f"யானை எச்சரிக்கை! {clean_loc} அருகே யானை கண்டறியப்பட்டுள்ளது."
                ta_safety = "யானையை நெருங்க வேண்டாம். வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றவும்."

            ta_conf = f" கண்டறிதல் நம்பகத்தன்மை: {conf_pct}%." if conf_pct is not None else ""
            ta_time = f" நேரம்: {time_display}."
            ta_dash = f" மேலும் விவரங்கள்: {dashboard_url}" if dashboard_url else ""

            regional_body = f"{ta_alert}{ta_conf}{ta_time} {ta_safety}{ta_dash}".strip()
        else:
            # Karnataka: English + Kannada in same SMS
            if count_val is not None:
                if count_val == 1:
                    kn_alert = f"ಆನೆ ಎಚ್ಚರಿಕೆ! {clean_loc} ಸಮೀಪ 1 ಆನೆ ಪತ್ತೆಯಾಗಿದೆ."
                    kn_safety = "ಆನೆಯ ಹತ್ತಿರ ಹೋಗಬೇಡಿ. ಅರಣ್ಯ ಇಲಾಖೆಯ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ."
                else:
                    kn_alert = f"ಆನೆ ಎಚ್ಚರಿಕೆ! {clean_loc} ಸಮೀಪ {count_val} ಆನೆಗಳು ಪತ್ತೆಯಾಗಿವೆ."
                    kn_safety = "ಆನೆಗಳ ಹತ್ತಿರ ಹೋಗಬೇಡಿ. ಅರಣ್ಯ ಇಲಾಖೆಯ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ."
            else:
                kn_alert = f"ಆನೆ ಎಚ್ಚರಿಕೆ! {clean_loc} ಸಮೀಪ ಆನೆ ಪತ್ತೆಯಾಗಿದೆ."
                kn_safety = "ಆನೆಯ ಹತ್ತಿರ ಹೋಗಬೇಡಿ. ಅರಣ್ಯ ಇಲಾಖೆಯ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ."

            kn_conf = f" ಪತ್ತೆಹಚ್ಚುವಿಕೆಯ ವಿಶ್ವಾಸಾರ್ಹತೆ: {conf_pct}%." if conf_pct is not None else ""
            kn_time = f" ಸಮಯ: {time_display}."
            kn_dash = f" ಹೆಚ್ಚಿನ ವಿವರಗಳು: {dashboard_url}" if dashboard_url else ""

            regional_body = f"{kn_alert}{kn_conf}{kn_time} {kn_safety}{kn_dash}".strip()

        # Combine into ONE complete bilingual SMS
        return f"{english_body}\n\n{regional_body}"

    @classmethod
    def build_alert_message(
        cls,
        count: int,
        location: str,
        state: str,
        timestamp_str: Optional[str] = None
    ) -> str:
        """
        Builds a complete bilingual SMS message containing:
        1. Emergency alert heading
        2. Actual elephant count detected
        3. Configured monitoring location
        4. Date and time of detection
        5. Short safety instruction
        Maintained for exact backward compatibility with existing unit tests.
        """
        if not isinstance(count, int) or count <= 0:
            raise ValueError(f"Invalid elephant count: {count}. Count must be a positive integer.")

        normalized_state = (state or "").lower().strip()
        if normalized_state not in cls.SUPPORTED_STATES:
            normalized_state = "karnataka"  # Default fallback

        clean_loc = (location or "Monitored Wildlife Corridor").strip()
        time_display = timestamp_str or cls.format_timestamp()

        # Pluralization
        en_noun = "elephant" if count == 1 else "elephants"

        if normalized_state == "tamil_nadu":
            ta_noun = "யானை" if count == 1 else "யானைகள்"
            message = (
                f"🚨 ELEPHANT ALERT!\n"
                f"English: {count} {en_noun} detected at {clean_loc}. Time: {time_display}. "
                f"Please stay safe and inform the forest department.\n"
                f"தமிழ்: {clean_loc}-ல் {count} {ta_noun} கண்டறியப்பட்டுள்ளன. நேரம்: {time_display}. "
                f"பாதுகாப்பாக இருங்கள் மற்றும் வனத்துறைக்குத் தகவல் தெரிவிக்கவும்."
            )
        else:
            kn_noun = "ಆನೆ" if count == 1 else "ಆನೆಗಳು"
            message = (
                f"🚨 ELEPHANT ALERT!\n"
                f"English: {count} {en_noun} detected at {clean_loc}. Time: {time_display}. "
                f"Please stay safe and inform the forest department.\n"
                f"ಕನ್ನಡ: {clean_loc}ದಲ್ಲಿ {count} {kn_noun} ಪತ್ತೆಯಾಗಿವೆ. ಸಮಯ: {time_display}. "
                f"ಸುರಕ್ಷಿತವಾಗಿರಿ ಮತ್ತು ಅರಣ್ಯ ಇಲಾಖೆಗೆ ಮಾಹಿತಿ ನೀಡಿ."
            )

        return message

    @classmethod
    def build_test_message(cls, state: str, location: str) -> str:
        """Constructs an explicit bilingual verification test message."""
        normalized_state = (state or "").lower().strip()
        time_display = cls.format_timestamp()
        clean_loc = (location or "Monitored Corridor").strip()

        if normalized_state == "tamil_nadu":
            return (
                f"🚨 TEST ALERT: Human-Elephant Detection System SMS Gateway Test.\n"
                f"English: Test alert successfully dispatched via Android phone SIM card. Location: {clean_loc}. Time: {time_display}.\n"
                f"தமிழ்: உங்கள் ஆண்ட்ராய்டு சிம் வழியாக சோதனை எச்சரிக்கை வெற்றிகரமாக அனுப்பப்பட்டது. நேரம்: {time_display}."
            )
        else:
            return (
                f"🚨 TEST ALERT: Human-Elephant Detection System SMS Gateway Test.\n"
                f"English: Test alert successfully dispatched via Android phone SIM card. Location: {clean_loc}. Time: {time_display}.\n"
                f"ಕನ್ನಡ: ನಿಮ್ಮ ಆಂಡ್ರಾಯ್ಡ್ ಸಿಮ್ ಮೂಲಕ ಪರೀಕ್ಷಾ ಎಚ್ಚರಿಕೆಯನ್ನು ಯಶಸ್ವಿಯಾಗಿ ಕಳುಹಿಸಲಾಗಿದೆ. ಸಮಯ: {time_display}."
            )


class AndroidSmsGatewayManager:
    """
    Manages Android SIM SMS Gateway integrations (SMSGate primary, TextBee legacy).
    Handles configuration, deduplication, cooldowns, asynchronous dispatch,
    status polling, and history tracking.
    """

    COUNT_POLICIES = ["always", "increase_only", "cooldown"]
    SUPPORTED_PROVIDERS = ["smsgate", "textbee"]

    def __init__(
        self,
        config_file: Optional[str] = None,
        config_path: Optional[str] = None,
        history_file: Optional[str] = None,
        provider: Optional[str] = None,
        start_poller: bool = True
    ):
        self.config_file = config_path or config_file or CONFIG_FILE
        self.history_file = history_file or HISTORY_FILE
        self.lock = threading.RLock()
        self.config = self._load_config()
        self.history = self._load_history()

        # Provider determination: default is smsgate
        explicit_provider = (
            provider
            or os.getenv("SMS_GATEWAY_PROVIDER")
            or self.config.get("provider")
        )
        if explicit_provider and str(explicit_provider).lower().strip() == "textbee":
            self.provider = "textbee"
        else:
            self.provider = "smsgate"

        # Detection event & deduplication state tracking
        self.active_event = False
        self.last_sent_count = 0
        self.last_sent_time = 0.0
        self.last_detection_seen_time = 0.0
        self.last_alert_details = None

        # Failure throttling
        self.last_failure_time = 0.0
        self.consecutive_failures = 0

        # Background status poller for SMSGate delivery confirmation
        self._poller_thread = None
        self._poller_stop_event = threading.Event()
        if start_poller and self.provider == "smsgate":
            self._start_poller()

    def get_smsgate_env(self) -> Dict[str, Any]:
        """Reads SMSGate configuration ONLY from environment variables."""
        base_url = os.getenv("SMSGATE_BASE_URL", "").strip()
        username = os.getenv("SMSGATE_USERNAME", "").strip()
        password = os.getenv("SMSGATE_PASSWORD", "").strip()
        messages_path = os.getenv("SMSGATE_MESSAGES_PATH", "/messages").strip()
        try:
            timeout = float(os.getenv("SMSGATE_TIMEOUT", "8"))
        except ValueError:
            timeout = 8.0
        try:
            max_retries = int(os.getenv("SMSGATE_MAX_RETRIES", "3"))
        except ValueError:
            max_retries = 3
        try:
            backoff = float(os.getenv("SMSGATE_BACKOFF", "2"))
        except ValueError:
            backoff = 2.0
        try:
            ttl = int(os.getenv("SMS_TTL_SECONDS", "900"))
        except ValueError:
            ttl = 900
        try:
            priority = int(os.getenv("SMS_PRIORITY", "100"))
        except ValueError:
            priority = 100

        allow_public = os.getenv("SMSGATE_ALLOW_PUBLIC_HOST", "").lower().strip() in ("true", "1", "yes")

        return {
            "base_url": base_url,
            "username": username,
            "password": password,
            "messages_path": messages_path,
            "timeout": timeout,
            "max_retries": max_retries,
            "backoff": backoff,
            "ttl": ttl,
            "priority": priority,
            "allow_public": allow_public
        }

    def is_smsgate_configured(self) -> bool:
        """Checks if required SMSGate environment variables are populated."""
        env = self.get_smsgate_env()
        return bool(env["base_url"] and env["username"] and env["password"])

    def check_smsgate_configuration(self) -> Tuple[bool, str]:
        """Validates SMSGate environment variables and URL security constraint."""
        env = self.get_smsgate_env()
        if not (env["base_url"] and env["username"] and env["password"]):
            return False, "SMSGate is not configured (missing SMSGATE_BASE_URL, SMSGATE_USERNAME, or SMSGATE_PASSWORD)."
        valid_url, reason = validate_smsgate_url(env["base_url"], allow_public=env["allow_public"])
        if not valid_url:
            return False, f"Invalid SMSGate Base URL: {reason}"
        return True, "Configured"

    def _get_smsgate_client(self) -> SMSGateClient:
        """Instantiates SMSGateClient from validated environment variables."""
        env = self.get_smsgate_env()
        return SMSGateClient(
            base_url=env["base_url"],
            username=env["username"],
            password=env["password"],
            timeout=env["timeout"],
            messages_path=env["messages_path"]
        )

    def _sanitize_text(self, text: Optional[str]) -> str:
        """Sanitizes text by stripping passwords, masking phone numbers, and truncating."""
        if not text:
            return ""
        s = str(text)
        pw = os.getenv("SMSGATE_PASSWORD", "")
        if pw and len(pw) >= 3:
            s = s.replace(pw, "***")
        tb_key = self.config.get("api_key", "")
        if tb_key and len(tb_key) >= 4:
            s = s.replace(tb_key, "***")
        s = re.sub(r"\+?\d[\d\s\-]{7,}\d", "[number]", s)
        return s[:250]

    def get_failed_count_last_hour(self) -> int:
        """Calculates count of failed SMS alerts in the last 60 minutes."""
        now = time.time()
        cutoff = now - 3600
        failed = 0
        with self.lock:
            for rec in self.history:
                ts_str = rec.get("timestamp")
                if ts_str:
                    try:
                        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                        if dt.timestamp() >= cutoff:
                            if rec.get("status") in ("failed", "SEND_FAILED") or not rec.get("success", True):
                                failed += 1
                    except Exception:
                        pass
        return failed

    def _start_poller(self):
        """Starts background status poller thread if not already running."""
        with self.lock:
            if self._poller_thread is not None and self._poller_thread.is_alive():
                return
            self._poller_stop_event.clear()
            self._poller_thread = threading.Thread(
                target=self._status_poller_loop,
                daemon=True,
                name="SMSGate-StatusPoller"
            )
            self._poller_thread.start()

    def stop_poller(self, timeout: float = 2.0):
        """Signals and stops the background status poller."""
        self._poller_stop_event.set()
        if self._poller_thread and self._poller_thread.is_alive():
            self._poller_thread.join(timeout=timeout)

    def _status_poller_loop(self):
        """Periodic background poller loop (every ~15s)."""
        while not self._poller_stop_event.wait(15.0):
            try:
                self.poll_pending_statuses()
            except Exception:
                pass

    def poll_pending_statuses(self) -> int:
        """
        Polls SMSGate for delivery status updates on recent non-terminal messages.
        Status mapping:
          - 'Sent' -> 'sent_to_carrier'
          - 'Delivered' -> 'delivered'
          - 'Failed' / 'Cancelled' -> 'failed' (with sanitized reason)
          - 'Processed' beyond 5 minutes -> 'unknown' (never auto-retry)
        Returns number of updated records.
        """
        if self.provider != "smsgate" or not self.is_smsgate_configured():
            return 0

        now = time.time()
        updated_count = 0

        candidates = []
        with self.lock:
            for idx, rec in enumerate(self.history):
                status = str(rec.get("status", "")).lower()
                if status in ("delivered", "failed", "unknown"):
                    continue

                meta = rec.get("meta") or {}
                gw_id = meta.get("gateway_message_id")
                recip_ids = []
                for rr in meta.get("recipients_results", []):
                    r_status = str(rr.get("status", "")).lower()
                    r_id = rr.get("gateway_message_id")
                    if r_id and r_status not in ("delivered", "failed", "unknown"):
                        recip_ids.append((rr, r_id))

                if gw_id or recip_ids:
                    created_ts = None
                    ts_str = rec.get("timestamp")
                    if ts_str:
                        try:
                            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                            created_ts = dt.timestamp()
                        except Exception:
                            created_ts = now
                    else:
                        created_ts = now

                    age = now - created_ts
                    if age <= 1800:
                        candidates.append((idx, rec, gw_id, recip_ids, age))

        if not candidates:
            return 0

        try:
            client = self._get_smsgate_client()
        except Exception:
            return 0

        for idx, rec, gw_id, recip_ids, age in candidates:
            ids_to_poll = []
            if gw_id:
                ids_to_poll.append((None, gw_id))
            for rr, r_id in recip_ids:
                if r_id != gw_id:
                    ids_to_poll.append((rr, r_id))

            record_changed = False
            for target_recip, target_id in ids_to_poll:
                try:
                    status_data = client.get_status(target_id)
                except GatewayError:
                    continue
                except Exception:
                    continue

                if not isinstance(status_data, dict):
                    continue

                raw_state = str(status_data.get("state") or status_data.get("status") or "").strip().lower()
                mapped_status = None
                error_msg = None

                if raw_state == "delivered":
                    mapped_status = "delivered"
                elif raw_state == "sent":
                    mapped_status = "sent_to_carrier"
                elif raw_state in ("failed", "cancelled"):
                    mapped_status = "failed"
                    raw_err = status_data.get("error") or status_data.get("reason") or f"Gateway state: {raw_state}"
                    error_msg = self._sanitize_text(str(raw_err))
                elif raw_state in ("processed", "pending", ""):
                    if age > 300:
                        mapped_status = "unknown"
                    else:
                        if raw_state == "processed":
                            mapped_status = "Processed"

                if mapped_status:
                    with self.lock:
                        if target_recip is not None:
                            target_recip["status"] = mapped_status
                            if error_msg:
                                target_recip["error"] = error_msg
                        else:
                            rec["status"] = mapped_status
                            if error_msg:
                                rec["error"] = error_msg
                            rec["delivery_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        record_changed = True

            if record_changed:
                updated_count += 1

        if updated_count > 0:
            with self.lock:
                try:
                    target_file = getattr(self, 'history_file', None) or HISTORY_FILE
                    with open(target_file, "w", encoding="utf-8") as f:
                        json.dump(self.history, f, indent=2)
                except Exception as e:
                    print(f"[SMS-GATE] Error updating history file: {e}")

        return updated_count

    def _load_config(self) -> Dict[str, Any]:
        """Loads configuration from JSON file with environment variable fallbacks."""
        defaults = {
            "enabled": True,
            "provider": os.getenv("SMS_GATEWAY_PROVIDER", "smsgate").lower().strip(),
            "api_key": os.getenv("TEXTBEE_API_KEY", "").strip(),
            "device_id": os.getenv("TEXTBEE_DEVICE_ID", "").strip(),
            "recipient_phone": os.getenv("TEXTBEE_RECIPIENT_PHONE", os.getenv("WHATSAPP_RECIPIENT", "")).strip(),
            "state": os.getenv("ALERT_MONITORING_STATE", "karnataka").lower().strip(),
            "location_name": os.getenv("ALERT_MONITORING_LOCATION", "Bannerghatta Forest Corridor").strip(),
            "cooldown_seconds": int(os.getenv("ALERT_SMS_COOLDOWN_SECONDS", 300)),
            "count_change_policy": os.getenv("ALERT_COUNT_CHANGE_POLICY", "always").lower().strip(),
            "absence_reset_seconds": int(os.getenv("ALERT_ABSENCE_RESET_SECONDS", 120)),
            "max_daily_limit": 50,
            "daily_sent_count": 0,
            "last_sent_date": datetime.now().strftime("%Y-%m-%d"),
            "recipients": {
                "officers": [],
                "villagers": []
            }
        }

        target_path = getattr(self, 'config_file', None) or CONFIG_FILE
        if target_path and os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    defaults.update(saved)
            except Exception as e:
                print(f"[ANDROID-SMS] Notice: Could not read {target_path}: {e}")

        # Ensure recipients structure is present
        if not isinstance(defaults.get("recipients"), dict):
            defaults["recipients"] = {"officers": [], "villagers": []}
        if "officers" not in defaults["recipients"]:
            defaults["recipients"]["officers"] = []
        if "villagers" not in defaults["recipients"]:
            defaults["recipients"]["villagers"] = []

        # Seed primary officer if recipient_phone exists but officers list is empty
        if defaults.get("recipient_phone") and not defaults["recipients"]["officers"]:
            defaults["recipients"]["officers"].append({
                "id": "officer_default",
                "name": "Range Officer",
                "phone": defaults["recipient_phone"],
                "location": defaults.get("location_name", "Bannerghatta Forest Corridor"),
                "language": defaults.get("state", "karnataka"),
                "role": "officer",
                "enabled": True,
                "created_at": datetime.now().isoformat()
            })

        # Reset daily quota tracker if day rolled over
        today = datetime.now().strftime("%Y-%m-%d")
        if defaults.get("last_sent_date") != today:
            defaults["last_sent_date"] = today
            defaults["daily_sent_count"] = 0

        return defaults

    def _save_config(self) -> bool:
        """Persists current configuration to disk."""
        target_file = getattr(self, 'config_file', CONFIG_FILE)
        try:
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"[ANDROID-SMS] Error saving {target_file}: {e}")
            return False

    def _load_history(self) -> list:
        """Loads alert history from JSON file."""
        target = getattr(self, "history_file", None) or HISTORY_FILE
        if os.path.exists(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[-50:]
            except Exception:
                pass
        return []

    def _record_history(self, record: Dict[str, Any]):
        """Records an event in the persistent history log."""
        target = getattr(self, "history_file", None) or HISTORY_FILE
        with self.lock:
            self.history.append(record)
            if len(self.history) > 50:
                self.history.pop(0)
            try:
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(self.history, f, indent=2)
            except Exception as e:
                print(f"[ANDROID-SMS] Error writing history to {target}: {e}")

    # ==========================================================================
    # RECIPIENT MANAGEMENT METHODS (OFFICERS & VILLAGERS)
    # ==========================================================================
    def get_recipients(self, group: Optional[str] = None, masked: bool = False) -> Dict[str, Any]:
        """Returns configured recipients grouped by officers and villagers."""
        with self.lock:
            recips = self.config.get("recipients", {"officers": [], "villagers": []})
            def _format_list(items, role_name):
                formatted = []
                for r in items:
                    item = dict(r)
                    item["role"] = role_name
                    if masked:
                        item["phone_masked"] = mask_phone_number(r.get("phone"))
                    formatted.append(item)
                return formatted

            officers = _format_list(recips.get("officers", []), "officer")
            villagers = _format_list(recips.get("villagers", []), "villager")

            if group in ("officer", "officers"):
                return {"officers": officers}
            elif group in ("villager", "villagers"):
                return {"villagers": villagers}
            return {
                "officers": officers,
                "villagers": villagers
            }

    def add_recipient(
        self,
        group: str,
        name: str,
        phone: str,
        location: str = "",
        language: str = "karnataka",
        enabled: bool = True
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Adds a new recipient to the specified group (officers or villagers)."""
        clean_group = "officers" if "officer" in str(group).lower() else "villagers"
        clean_phone = re.sub(r"[^\d+]", "", str(phone).strip())
        if not clean_phone or len(re.sub(r"\D", "", clean_phone)) < 10:
            return False, f"Invalid phone number: '{phone}'. Must be at least 10 digits.", {}

        if not clean_phone.startswith("+"):
            clean_phone = f"+91{clean_phone}" if len(clean_phone) == 10 else f"+{clean_phone}"

        norm_lang = (language or "karnataka").lower().strip()
        if norm_lang not in BilingualMessageBuilder.SUPPORTED_STATES:
            norm_lang = "tamil_nadu" if "tamil" in norm_lang else "karnataka"

        recip = {
            "id": f"recip_{str(uuid.uuid4())[:8]}",
            "name": str(name).strip() or ("Forest Officer" if clean_group == "officers" else "Local Villager"),
            "phone": clean_phone,
            "location": str(location).strip() or self.config.get("location_name", "Forest Zone"),
            "language": norm_lang,
            "role": "officer" if clean_group == "officers" else "villager",
            "enabled": bool(enabled),
            "created_at": datetime.now().isoformat()
        }

        with self.lock:
            if "recipients" not in self.config:
                self.config["recipients"] = {"officers": [], "villagers": []}
            if clean_group not in self.config["recipients"]:
                self.config["recipients"][clean_group] = []

            for existing in self.config["recipients"][clean_group]:
                if existing.get("phone") == clean_phone:
                    return False, f"Phone number {mask_phone_number(clean_phone)} already exists in {clean_group}.", existing

            self.config["recipients"][clean_group].append(recip)
            self._save_config()

        return True, f"Recipient '{recip['name']}' added successfully to {clean_group}.", recip

    def update_recipient(self, recipient_id: str, updates: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """Updates attributes of an existing recipient."""
        with self.lock:
            recips = self.config.get("recipients", {"officers": [], "villagers": []})
            target = None
            for grp in ["officers", "villagers"]:
                for r in recips.get(grp, []):
                    if r.get("id") == recipient_id:
                        target = r
                        break
                if target:
                    break

            if not target:
                return False, f"Recipient with ID '{recipient_id}' not found.", {}

            if "name" in updates:
                target["name"] = str(updates["name"]).strip()
            if "location" in updates:
                target["location"] = str(updates["location"]).strip()
            if "language" in updates:
                lang = str(updates["language"]).lower().strip()
                if lang in BilingualMessageBuilder.SUPPORTED_STATES:
                    target["language"] = lang
            if "enabled" in updates:
                target["enabled"] = bool(updates["enabled"])
            if "phone" in updates:
                ph = re.sub(r"[^\d+]", "", str(updates["phone"]).strip())
                if ph and len(re.sub(r"\D", "", ph)) >= 10:
                    if not ph.startswith("+"):
                        ph = f"+91{ph}" if len(ph) == 10 else f"+{ph}"
                    target["phone"] = ph

            self._save_config()
            return True, f"Recipient '{target['name']}' updated successfully.", target

    def delete_recipient(self, recipient_id: str) -> Tuple[bool, str]:
        """Deletes a recipient by ID."""
        with self.lock:
            recips = self.config.get("recipients", {"officers": [], "villagers": []})
            found = False
            for grp in ["officers", "villagers"]:
                orig_len = len(recips.get(grp, []))
                recips[grp] = [r for r in recips.get(grp, []) if r.get("id") != recipient_id]
                if len(recips[grp]) < orig_len:
                    found = True
                    break

            if not found:
                return False, f"Recipient with ID '{recipient_id}' not found."

            self._save_config()
            return True, "Recipient deleted successfully."

    def toggle_recipient(self, recipient_id: str, enabled: Optional[bool] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """Toggles or sets the enabled status of a recipient."""
        with self.lock:
            recips = self.config.get("recipients", {"officers": [], "villagers": []})
            target = None
            for grp in ["officers", "villagers"]:
                for r in recips.get(grp, []):
                    if r.get("id") == recipient_id:
                        target = r
                        break
                if target:
                    break

            if not target:
                return False, f"Recipient with ID '{recipient_id}' not found.", {}

            if enabled is not None:
                target["enabled"] = bool(enabled)
            else:
                target["enabled"] = not target.get("enabled", True)

            self._save_config()
            status_str = "enabled" if target["enabled"] else "disabled"
            return True, f"Recipient '{target['name']}' is now {status_str}.", target

    def update_config(self, new_settings: Dict[str, Any]) -> Tuple[bool, str]:
        """Updates and validates configuration settings from the dashboard."""
        with self.lock:
            # Handle API key: keep existing if masked placeholder provided
            if "api_key" in new_settings:
                val = str(new_settings["api_key"]).strip()
                if val and not val.startswith("••••"):
                    self.config["api_key"] = val

            if "device_id" in new_settings:
                self.config["device_id"] = str(new_settings["device_id"]).strip()

            if "recipient_phone" in new_settings:
                rec = str(new_settings["recipient_phone"]).strip()
                if rec:
                    cleaned = re.sub(r"[^\d+]", "", rec)
                    self.config["recipient_phone"] = cleaned

            if "state" in new_settings:
                st = str(new_settings["state"]).lower().strip()
                if st in BilingualMessageBuilder.SUPPORTED_STATES:
                    self.config["state"] = st

            if "location_name" in new_settings:
                loc = str(new_settings["location_name"]).strip()
                if loc:
                    self.config["location_name"] = loc

            if "cooldown_seconds" in new_settings:
                try:
                    cd = int(new_settings["cooldown_seconds"])
                    if cd >= 10:
                        self.config["cooldown_seconds"] = cd
                except (ValueError, TypeError):
                    pass

            if "count_change_policy" in new_settings:
                pol = str(new_settings["count_change_policy"]).lower().strip()
                if pol in self.COUNT_POLICIES:
                    self.config["count_change_policy"] = pol

            if "absence_reset_seconds" in new_settings:
                try:
                    abs_sec = int(new_settings["absence_reset_seconds"])
                    if abs_sec >= 10:
                        self.config["absence_reset_seconds"] = abs_sec
                except (ValueError, TypeError):
                    pass

            if "enabled" in new_settings:
                self.config["enabled"] = bool(new_settings["enabled"])

            if "provider" in new_settings:
                prov = str(new_settings["provider"]).lower().strip()
                if prov in self.SUPPORTED_PROVIDERS:
                    self.config["provider"] = prov
                    self.provider = prov

            if "recipients" in new_settings and isinstance(new_settings["recipients"], dict):
                self.config["recipients"] = new_settings["recipients"]

            self._save_config()

        return True, "SMS Gateway configuration updated successfully."

    def get_safe_config(self) -> Dict[str, Any]:
        """Returns sanitized configuration for UI display without leaking credentials."""
        with self.lock:
            safe = dict(self.config)
            safe["provider"] = self.provider
            safe["supported_providers"] = self.SUPPORTED_PROVIDERS
            safe["smsgate_configured"] = self.is_smsgate_configured()

            env = self.get_smsgate_env()
            if env["base_url"]:
                try:
                    p = urlparse(env["base_url"])
                    port_str = f":{p.port}" if p.port else ""
                    safe["smsgate_base_url"] = f"{p.scheme}://{p.hostname}{port_str}"
                except Exception:
                    safe["smsgate_base_url"] = "[configured]"
            else:
                safe["smsgate_base_url"] = ""

            safe["failed_last_hour"] = self.get_failed_count_last_hour()
            safe["api_key_masked"] = mask_api_key(self.config.get("api_key"))
            safe["has_api_key"] = bool(self.config.get("api_key"))
            safe["recipient_masked"] = mask_phone_number(self.config.get("recipient_phone"))
            safe["supported_states"] = BilingualMessageBuilder.SUPPORTED_STATES
            safe["count_policies"] = self.COUNT_POLICIES

            recips = self.config.get("recipients", {"officers": [], "villagers": []})
            masked_officers = []
            for o in recips.get("officers", []):
                item = dict(o)
                item["phone_masked"] = mask_phone_number(o.get("phone"))
                masked_officers.append(item)

            masked_villagers = []
            for v in recips.get("villagers", []):
                item = dict(v)
                item["phone_masked"] = mask_phone_number(v.get("phone"))
                masked_villagers.append(item)

            safe["recipients"] = {
                "officers": masked_officers,
                "villagers": masked_villagers
            }
            safe["officers_count"] = len(masked_officers)
            safe["villagers_count"] = len(masked_villagers)
            safe["active_recipients_count"] = sum(1 for r in (masked_officers + masked_villagers) if r.get("enabled", True))
            safe["last_alert"] = self.last_alert_details
            safe["active_event"] = self.active_event
            safe["last_sent_count"] = self.last_sent_count

            if self.provider == "smsgate":
                safe["free_tier_limits"] = {
                    "provider": "SMSGate (Local Server)",
                    "monthly_limit": "Unlimited (Carrier dependent)",
                    "daily_limit": "SIM Card Plan Quota",
                    "device_limit": 1,
                    "daily_sent_today": self.config.get("daily_sent_count", 0)
                }
            else:
                safe["free_tier_limits"] = {
                    "provider": "TextBee (Android Gateway)",
                    "monthly_limit": 300,
                    "daily_limit": 50,
                    "device_limit": 1,
                    "daily_sent_today": self.config.get("daily_sent_count", 0)
                }

            # Remove raw secrets
            safe.pop("api_key", None)
            safe.pop("password", None)
            safe.pop("smsgate_password", None)
            return safe

    def get_history(self) -> list:
        """Returns dispatch history sorted newest first."""
        with self.lock:
            return list(reversed(self.history))

    # ==========================================================================
    # GATEWAY CONNECTION & DEVICE HEALTH VALIDATION
    # ==========================================================================
    def validate_connection(self) -> Dict[str, Any]:
        """
        Validates connection to the active gateway provider.
        When provider is 'textbee', queries TextBee /gateway/devices.
        When provider is 'smsgate', queries SMSGate /health.
        """
        if self.provider == "textbee":
            api_key = self.config.get("api_key")
            if not api_key:
                return {
                    "valid": False,
                    "status": "MISSING_CREDENTIALS",
                    "message": "TextBee API Key is not configured. Add it in dashboard or .env."
                }

            headers = {
                "x-api-key": api_key,
                "Content-Type": "application/json"
            }

            try:
                resp = requests.get(
                    f"{TEXTBEE_BASE_URL}/gateway/devices",
                    headers=headers,
                    timeout=10
                )

                if resp.status_code in (401, 403):
                    return {
                        "valid": False,
                        "status": "AUTHENTICATION_FAILED",
                        "message": "TextBee API key rejected (401/403 Unauthorized). Check your API key."
                    }

                if resp.status_code == 200:
                    data = resp.json()
                    devices = data if isinstance(data, list) else data.get("data", [])
                    device_count = len(devices) if isinstance(devices, list) else 0

                    active_device = None
                    configured_device_id = self.config.get("device_id")

                    if isinstance(devices, list) and devices:
                        if configured_device_id:
                            for d in devices:
                                if str(d.get("id") or d.get("deviceId")) == configured_device_id:
                                    active_device = d
                                    break
                        if not active_device:
                            active_device = devices[0]

                    return {
                        "valid": True,
                        "status": "CONNECTED",
                        "message": f"Successfully connected to TextBee Gateway. {device_count} device(s) registered.",
                        "device_count": device_count,
                        "active_device": active_device,
                        "provider": "TextBee Cloud API (api.textbee.dev)"
                    }

                return {
                    "valid": False,
                    "status": "GATEWAY_ERROR",
                    "message": f"TextBee API returned HTTP {resp.status_code}: {resp.text[:150]}"
                }

            except requests.exceptions.Timeout:
                return {
                    "valid": False,
                    "status": "TIMEOUT",
                    "message": "Connection to TextBee API timed out (>10s)."
                }
            except Exception as e:
                return {
                    "valid": False,
                    "status": "CONNECTION_ERROR",
                    "message": f"Failed to connect to TextBee gateway: {str(e)}"
                }

        # Provider is SMSGate
        ok, reason = self.check_smsgate_configuration()
        if not ok:
            return {
                "valid": False,
                "status": "NOT_CONFIGURED",
                "message": reason,
                "provider": "SMSGate (Local Server)",
                "reachable": False
            }

        env = self.get_smsgate_env()
        try:
            client = self._get_smsgate_client()
            health = client.health()
            if not isinstance(health, dict):
                health = {}

            app_status = health.get("status") or "OK"
            battery_pct = health.get("battery")
            phone_internet = health.get("internet", True)

            return {
                "valid": True,
                "status": "CONNECTED",
                "message": f"Successfully connected to SMSGate Local Server on {env['base_url']}.",
                "provider": "SMSGate (Local Server)",
                "reachable": True,
                "app_status": app_status,
                "battery_pct": battery_pct,
                "phone_internet": phone_internet,
                "failed_last_hour": self.get_failed_count_last_hour(),
                "health_data": health
            }
        except GatewayAuthError:
            return {
                "valid": False,
                "status": "AUTHENTICATION_FAILED",
                "message": "SMSGate rejected credentials (HTTP 401/403). Verify SMSGATE_USERNAME and SMSGATE_PASSWORD.",
                "provider": "SMSGate (Local Server)",
                "reachable": True
            }
        except GatewayTimeout:
            return {
                "valid": False,
                "status": "TIMEOUT",
                "message": f"SMSGate did not answer within {env['timeout']}s.",
                "provider": "SMSGate (Local Server)",
                "reachable": False
            }
        except GatewayUnavailable as exc:
            return {
                "valid": False,
                "status": "UNAVAILABLE",
                "message": self._sanitize_text(str(exc)),
                "provider": "SMSGate (Local Server)",
                "reachable": False
            }
        except Exception as e:
            return {
                "valid": False,
                "status": "GATEWAY_ERROR",
                "message": self._sanitize_text(str(e)),
                "provider": "SMSGate (Local Server)",
                "reachable": False
            }

    # ==========================================================================
    # CORE DISPATCH ENGINE
    # ==========================================================================
    def _send_sms_textbee(
        self,
        recipient: str,
        message: str,
        event_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Low-level send via TextBee Android SMS Gateway (legacy provider).
        POST /gateway/send-sms
        Requires recipient in E.164 format.
        """
        api_key = self.config.get("api_key")
        if not api_key:
            return False, "TextBee API Key is missing. Configure it in settings.", {}

        clean_recipient = re.sub(r"[^\d+]", "", str(recipient).strip())
        if not clean_recipient or len(re.sub(r"\D", "", clean_recipient)) < 10:
            return False, f"Invalid recipient phone number: '{recipient}'. Must be valid E.164 format.", {}

        if not clean_recipient.startswith("+"):
            if len(clean_recipient) == 10:
                clean_recipient = f"+91{clean_recipient}"
            else:
                clean_recipient = f"+{clean_recipient}"

        payload = {
            "recipients": [clean_recipient],
            "message": message
        }

        device_id = self.config.get("device_id")
        if device_id:
            payload["deviceId"] = device_id

        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json"
        }

        today = datetime.now().strftime("%Y-%m-%d")
        if self.config.get("last_sent_date") != today:
            self.config["last_sent_date"] = today
            self.config["daily_sent_count"] = 0

        daily_count = self.config.get("daily_sent_count", 0)
        daily_limit = self.config.get("max_daily_limit", 50)
        if daily_count >= daily_limit:
            return False, f"Free-tier daily limit reached ({daily_count}/{daily_limit} messages today).", {}

        max_attempts = 2
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.post(
                    f"{TEXTBEE_BASE_URL}/gateway/send-sms",
                    json=payload,
                    headers=headers,
                    timeout=12
                )

                if resp.status_code in (200, 201):
                    res_json = resp.json()
                    msg_id = ""
                    if isinstance(res_json, dict):
                        data_part = res_json.get("data", res_json)
                        if isinstance(data_part, dict):
                            msg_id = data_part.get("id") or data_part.get("messageId") or ""
                        elif isinstance(data_part, list) and data_part:
                            msg_id = data_part[0].get("id", "")

                    self.config["daily_sent_count"] = daily_count + 1
                    self._save_config()

                    details = {
                        "gateway_message_id": msg_id,
                        "raw_response": res_json,
                        "recipient_masked": mask_phone_number(clean_recipient),
                        "status": "ACCEPTED_BY_GATEWAY",
                        "delivery_channel": "Android Phone SIM Card (TextBee)",
                        "provider": "textbee"
                    }
                    if event_metadata:
                        details.update(event_metadata)

                    return True, f"ACCEPTED_BY_GATEWAY (Message ID: {msg_id or 'queued'}). Android phone SIM will dispatch.", details

                elif resp.status_code in (400, 401, 403, 404):
                    err_msg = f"TextBee API Error ({resp.status_code}): {resp.text[:150]}"
                    return False, err_msg, {"status": "SEND_FAILED", "error": err_msg}

                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"

            except requests.exceptions.Timeout:
                last_error = "TextBee API request timed out (>12s)"
            except Exception as e:
                last_error = f"Gateway communication error: {str(e)}"

            if attempt < max_attempts:
                time.sleep(1.5)

        return False, f"SMS dispatch failed after {max_attempts} attempts: {last_error}", {"status": "SEND_FAILED", "error": last_error}

    def _send_sms_smsgate(
        self,
        recipient: str,
        message: str,
        event_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Sends SMS via SMSGate (SMS Gateway for Android, Local Server mode).
        Dispatches one request per recipient using a stable message ID across retries.
        HTTP 2xx is recorded as 'gateway_accepted' (NEVER 'delivered').
        """
        ok, reason = self.check_smsgate_configuration()
        if not ok:
            err_details = {
                "status": "not configured",
                "error": reason,
                "provider": "smsgate"
            }
            if event_metadata:
                err_details.update(event_metadata)
            return False, reason, err_details

        clean_recipient = normalize_to_e164(recipient)
        if not clean_recipient:
            err_details = {
                "status": "INVALID_RECIPIENT",
                "error": f"Recipient '{recipient}' is not a valid E.164 phone number.",
                "provider": "smsgate"
            }
            if event_metadata:
                err_details.update(event_metadata)
            return False, f"Invalid recipient phone number: '{recipient}'. Must be valid E.164 format.", err_details

        env = self.get_smsgate_env()
        client = self._get_smsgate_client()

        # Stable message id across retries: f"evt{history_id}-{epoch}"
        epoch = int(time.time())
        evt_token = uuid.uuid4().hex[:8]
        msg_id = f"evt{evt_token}-{epoch}"

        def _do_send():
            return client.send(
                text=message,
                phone_numbers=[clean_recipient],
                message_id=msg_id,
                ttl=env["ttl"],
                priority=env["priority"]
            )

        try:
            resp, attempts = call_with_retries(
                _do_send,
                max_retries=env["max_retries"],
                backoff=env["backoff"]
            )
        except GatewayError as exc:
            attempts = getattr(exc, 'attempts', 1)
            sanitized_err = self._sanitize_text(str(exc))
            err_details = {
                "status": "failed",
                "attempts": attempts,
                "error": sanitized_err,
                "gateway_message_id": msg_id,
                "recipient_masked": mask_phone_number(clean_recipient),
                "provider": "smsgate"
            }
            if event_metadata:
                err_details.update(event_metadata)
            return False, f"SMS dispatch failed ({sanitized_err})", err_details
        except Exception as exc:
            sanitized_err = self._sanitize_text(str(exc))
            err_details = {
                "status": "failed",
                "attempts": 1,
                "error": sanitized_err,
                "gateway_message_id": msg_id,
                "recipient_masked": mask_phone_number(clean_recipient),
                "provider": "smsgate"
            }
            if event_metadata:
                err_details.update(event_metadata)
            return False, f"SMS dispatch failed ({sanitized_err})", err_details

        # HTTP 2xx returned: gateway_accepted (NOT delivered)
        resp_msg_id = ""
        if isinstance(resp, dict):
            resp_msg_id = resp.get("id") or ""
        final_msg_id = resp_msg_id or msg_id

        # Update daily sent count
        today = datetime.now().strftime("%Y-%m-%d")
        if self.config.get("last_sent_date") != today:
            self.config["last_sent_date"] = today
            self.config["daily_sent_count"] = 0
        self.config["daily_sent_count"] = self.config.get("daily_sent_count", 0) + 1
        self._save_config()

        details = {
            "status": "gateway_accepted",
            "gateway_message_id": final_msg_id,
            "raw_response": resp,
            "recipient_masked": mask_phone_number(clean_recipient),
            "attempts": attempts,
            "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "delivery_channel": "Android Phone SIM Card (SMSGate)",
            "provider": "smsgate"
        }
        if event_metadata:
            details.update(event_metadata)

        return True, f"gateway_accepted (Message ID: {final_msg_id}). Android phone SIM will dispatch.", details

    def send_sms(
        self,
        recipient: str,
        message: str,
        event_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Routes SMS dispatch to the active provider ('smsgate' default, 'textbee' legacy).
        """
        if self.provider == "textbee":
            return self._send_sms_textbee(recipient, message, event_metadata)
        return self._send_sms_smsgate(recipient, message, event_metadata)

    # ==========================================================================
    # AUTOMATED DETECTION EVENT HANDLER & DEBOUNCING
    # ==========================================================================
    def should_send_alert(self, current_count: int) -> Tuple[bool, str]:
        """
        Determines whether an SMS should be dispatched based on:
        - Current detection count
        - Active incident lifecycle
        - Configured cooldown window
        - Configured count change policy ('always', 'increase_only', 'cooldown')
        - Absence interval reset
        """
        now = time.time()
        cooldown = self.config.get("cooldown_seconds", 300)
        policy = self.config.get("count_change_policy", "always")
        absence_timeout = self.config.get("absence_reset_seconds", 120)

        # 1. No elephants detected (count <= 0)
        if current_count <= 0:
            if self.active_event:
                # Check if absent longer than absence timeout
                if (now - self.last_detection_seen_time) > absence_timeout:
                    print(f"[ANDROID-SMS] Incident closed: No elephants detected for >{absence_timeout}s.")
                    self.active_event = False
                    self.last_sent_count = 0
            return False, "No elephants detected in current frame."

        # Elephants are present!
        self.last_detection_seen_time = now

        # 2. First detection event
        if not self.active_event:
            return True, f"New detection incident started ({current_count} elephant(s) detected)."

        # 3. Ongoing incident with SAME count
        if current_count == self.last_sent_count:
            elapsed = now - self.last_sent_time
            if elapsed < cooldown:
                remaining = int(cooldown - elapsed)
                return False, f"Suppressed duplicate alert: Same count ({current_count}) within cooldown window ({remaining}s remaining)."
            else:
                return True, f"Cooldown expired ({cooldown}s). Re-alerting active elephant herd."

        # 4. Ongoing incident with CHANGED count
        elapsed = now - self.last_sent_time
        if policy == "always":
            return True, f"Herd count changed from {self.last_sent_count} to {current_count} (Policy: Always send)."

        elif policy == "increase_only":
            if current_count > self.last_sent_count:
                return True, f"Herd count increased from {self.last_sent_count} to {current_count} (Policy: Increase only)."
            else:
                if elapsed < cooldown:
                    return False, f"Count decreased ({self.last_sent_count} -> {current_count}). Suppressed until cooldown."
                return True, f"Cooldown expired after count decrease."

        elif policy == "cooldown":
            if elapsed < cooldown:
                remaining = int(cooldown - elapsed)
                return False, f"Count changed ({self.last_sent_count} -> {current_count}), but cooldown active ({remaining}s remaining)."
            return True, f"Cooldown expired with count change."

        return False, "Policy suppression."

    def process_detection(
        self,
        elephant_count: int,
        location: Optional[str] = None,
        timestamp_str: Optional[str] = None,
        confidence: Optional[float] = None,
        dashboard_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Core detection event hook.
        Evaluates deduplication logic and dispatches full bilingual SMS to all enabled
        recipients (Forest Officers and Local Villagers) in their configured language preference.
        Non-blocking and safe to invoke inside detection loop.
        """
        if not self.config.get("enabled", True):
            return {"status": "DISABLED", "message": "Android SMS Gateway is disabled in settings."}

        # Fail-safe throttle: if consecutive errors, wait 30s before trying again
        if self.consecutive_failures >= 3 and (time.time() - self.last_failure_time) < 30:
            return {
                "status": "THROTTLED",
                "message": "Gateway temporarily throttled due to repeated failures. Cooling down."
            }

        with self.lock:
            should_send, reason = self.should_send_alert(elephant_count)

        if not should_send:
            return {
                "status": "SKIPPED",
                "reason": reason,
                "elephant_count": elephant_count
            }

        # Find enabled recipients from both groups
        recips = self.config.get("recipients", {"officers": [], "villagers": []})
        active_officers = [r for r in recips.get("officers", []) if r.get("enabled", True)]
        active_villagers = [r for r in recips.get("villagers", []) if r.get("enabled", True)]
        all_targets: List[Dict[str, Any]] = []

        for o in active_officers:
            item = dict(o)
            item["group"] = "officer"
            all_targets.append(item)

        for v in active_villagers:
            item = dict(v)
            item["group"] = "villager"
            all_targets.append(item)

        # Fallback to legacy recipient_phone if no recipients are in groups
        if not all_targets and self.config.get("recipient_phone"):
            all_targets.append({
                "id": "legacy_primary",
                "name": "Configured Recipient",
                "phone": self.config.get("recipient_phone"),
                "location": location or self.config.get("location_name", "Bannerghatta Forest Corridor"),
                "language": self.config.get("state", "karnataka"),
                "group": "officer",
                "enabled": True
            })

        if not all_targets:
            return {
                "status": "RECIPIENT_NOT_CONFIGURED",
                "message": "No active recipients configured for SMS alerts."
            }

        # Update event tracking state immediately to prevent duplicate sends
        with self.lock:
            self.active_event = True
            self.last_sent_count = elephant_count
            self.last_sent_time = time.time()

        dash_link = dashboard_url or os.getenv("DASHBOARD_URL", "http://127.0.0.1:5000/dashboard")
        default_loc = location or self.config.get("location_name", "Bannerghatta Forest Corridor")
        results = []
        overall_success = False
        last_sms_text = ""

        for target in all_targets:
            recip_lang = target.get("language") or self.config.get("state", "karnataka")
            recip_loc = target.get("location") or default_loc
            recip_group = target.get("group", "officer")
            recip_phone = target.get("phone")

            try:
                sms_text = BilingualMessageBuilder.build_bilingual_sms(
                    count=elephant_count,
                    location=recip_loc,
                    state=recip_lang,
                    confidence=confidence,
                    timestamp_str=timestamp_str,
                    dashboard_url=dash_link,
                    group=recip_group
                )
            except Exception:
                # Fallback to standard builder if any error
                sms_text = BilingualMessageBuilder.build_alert_message(
                    count=max(1, elephant_count),
                    location=recip_loc,
                    state=recip_lang,
                    timestamp_str=timestamp_str
                )

            last_sms_text = sms_text
            seg_info = BilingualMessageBuilder.calculate_segments(sms_text)

            meta = {
                "type": "AUTOMATED_DETECTION",
                "elephant_count": elephant_count,
                "location": recip_loc,
                "state": recip_lang,
                "group": recip_group,
                "recipient_name": target.get("name"),
                "confidence": confidence,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "segment_info": seg_info
            }

            ok, details_msg, result_meta = self.send_sms(recip_phone, sms_text, meta)
            if ok:
                overall_success = True

            results.append({
                "recipient_id": target.get("id"),
                "recipient_name": target.get("name"),
                "recipient_masked": mask_phone_number(recip_phone),
                "language": recip_lang,
                "group": recip_group,
                "success": ok,
                "status": result_meta.get("status", "gateway_accepted" if ok else "failed"),
                "gateway_message_id": result_meta.get("gateway_message_id"),
                "details": details_msg,
                "segment_info": seg_info
            })

        status_str = "gateway_accepted" if overall_success else "failed"
        if self.provider == "textbee":
            status_str = "ACCEPTED_BY_GATEWAY" if overall_success else "SEND_FAILED"

        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": "AUTOMATED_DETECTION",
            "elephant_count": elephant_count,
            "location": default_loc,
            "state": self.config.get("state", "karnataka"),
            "recipient_masked": f"{len(results)} recipient(s) ({len(active_officers)} officers, {len(active_villagers)} villagers)",
            "message": last_sms_text,
            "success": overall_success,
            "status": status_str,
            "provider": self.provider,
            "details": f"Dispatched to {len(results)} recipient(s).",
            "meta": {
                "recipients_dispatched": len(results),
                "recipients_results": results
            }
        }

        with self.lock:
            if overall_success:
                self.consecutive_failures = 0
            else:
                self.consecutive_failures += 1
                self.last_failure_time = time.time()
            self.last_alert_details = record

        self._record_history(record)
        return record

    def process_detection_async(
        self,
        elephant_count: int,
        location: Optional[str] = None,
        timestamp_str: Optional[str] = None,
        confidence: Optional[float] = None,
        dashboard_url: Optional[str] = None
    ):
        """Dispatches detection processing in a detached background thread."""
        thread = threading.Thread(
            target=self.process_detection,
            args=(elephant_count, location, timestamp_str, confidence, dashboard_url),
            daemon=True
        )
        thread.start()
        return True

    # ==========================================================================
    # REAL TEST SMS WITH EXPLICIT CONFIRMATION
    # ==========================================================================
    def send_real_test_sms(
        self,
        recipient: Optional[str] = None,
        confirmed: bool = False,
        state: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Sends an explicit bilingual test SMS from the Android SIM card.
        Requires confirmed=True. Sends no elephant count (elephant_count=0).
        """
        if not confirmed:
            return False, "Explicit confirmation required (confirmed=True) before sending real SMS.", {
                "status": "CONFIRMATION_REQUIRED"
            }

        target = recipient or self.config.get("recipient_phone")
        if not target:
            # Check if any officer configured
            recips = self.config.get("recipients", {}).get("officers", [])
            if recips:
                target = recips[0].get("phone")

        if not target:
            return False, "Recipient phone number is not configured.", {
                "status": "MISSING_RECIPIENT"
            }

        test_state = (state or self.config.get("state", "karnataka")).lower().strip()
        loc = self.config.get("location_name", "Bannerghatta Corridor")

        test_msg = BilingualMessageBuilder.build_test_message(state=test_state, location=loc)
        seg_info = BilingualMessageBuilder.calculate_segments(test_msg)

        meta = {
            "type": "MANUAL_TEST",
            "state": test_state,
            "location": loc,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "segment_info": seg_info
        }

        ok, info_msg, result_meta = self.send_sms(target, test_msg, meta)

        status_str = "gateway_accepted" if ok else "failed"
        if self.provider == "textbee":
            status_str = "ACCEPTED_BY_GATEWAY" if ok else "SEND_FAILED"

        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": "MANUAL_TEST",
            "elephant_count": 0,
            "location": loc,
            "state": test_state,
            "recipient_masked": mask_phone_number(target),
            "message": test_msg,
            "success": ok,
            "status": status_str,
            "provider": self.provider,
            "details": info_msg,
            "meta": result_meta
        }

        with self.lock:
            self.last_alert_details = record

        self._record_history(record)
        return ok, info_msg, record

    # ==========================================================================
    # WEBHOOK STATUS RECEIVER
    # ==========================================================================
    def handle_webhook_status_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Receives delivery callbacks from gateway webhooks:
        e.g. MESSAGE_SENT, MESSAGE_DELIVERED, MESSAGE_FAILED
        """
        event_type = payload.get("event") or payload.get("status")
        message_id = payload.get("messageId") or payload.get("id")

        with self.lock:
            # Update matching record in history
            for rec in self.history:
                rec_meta = rec.get("meta") or {}
                if rec_meta.get("gateway_message_id") == message_id:
                    rec["delivery_status"] = event_type
                    rec["delivery_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    break

            target_file = getattr(self, 'history_file', None) or HISTORY_FILE
            try:
                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(self.history, f, indent=2)
            except Exception:
                pass

        return {"status": "ok", "message_id": message_id, "event": event_type}


# Global singleton instance
_GLOBAL_ANDROID_SMS_MANAGER = None


def get_android_sms_manager(reset: bool = False, **kwargs) -> AndroidSmsGatewayManager:
    """Returns the singleton instance of AndroidSmsGatewayManager."""
    global _GLOBAL_ANDROID_SMS_MANAGER
    if _GLOBAL_ANDROID_SMS_MANAGER is None or reset:
        _GLOBAL_ANDROID_SMS_MANAGER = AndroidSmsGatewayManager(**kwargs)
    return _GLOBAL_ANDROID_SMS_MANAGER

