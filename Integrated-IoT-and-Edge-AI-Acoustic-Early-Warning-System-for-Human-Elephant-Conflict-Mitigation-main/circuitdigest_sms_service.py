"""
CircuitDigest Cloud SMS Integration for Human-Elephant Conflict Mitigation System
Department of AI & ML, Sri Sairam College of Engineering

Features:
- Cloud REST API integration via CircuitDigest Cloud (https://www.circuitdigest.cloud/sms)
- Pre-approved IoT notification templates (e.g. Template 103 Motion Alert & Template 101 Status)
- Dual recipient groups: Forest Officers & Local Villagers
- Phone number validation and country-code normalization
- Location-based bilingual message preview and audit logging (Tamil Nadu: English + Tamil, Karnataka: English + Kannada)
- Strict 30-character ASCII dynamic variable mapping for CircuitDigest DLT template compliance
- Non-blocking asynchronous alert dispatching with frame debouncing and incident lifecycle tracking
- Cooldown policies, absence reset interval, and daily quota awareness
- Atomic JSON persistence and secure credential masking
"""

import os
import re
import json
import time
import uuid
import tempfile
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# PROVIDER CONSTANTS & LIMITATIONS (CIRCUITDIGEST CLOUD)
# ==============================================================================
# Base URL: https://www.circuitdigest.cloud/api/v1/send_sms
# Method: POST
# Query Param: ID={template_id}
# Headers:
#   Authorization: <API_KEY>
#   Content-Type: application/json
# Body:
#   {"mobiles": "919876543210", "var1": "...", "var2": "..."}
#
# Known Provider Limitations:
# 1. Template-based: SMS can only be sent using pre-approved template IDs (e.g., 101, 102, 103, 104, 105, 106).
# 2. Dynamic Variables: Templates accept var1 and var2 (max 30 alphanumeric/ASCII chars each).
# 3. Unicode / Language: CircuitDigest pre-approved templates are strictly English GSM-7.
#    Non-ASCII regional scripts (Tamil/Kannada) cannot be injected into DLT templates.
#    The system maintains the full bilingual text in local logs and previews,
#    while mapping ASCII descriptors into the CircuitDigest template variables.
# 4. Phone Verification: On developer/free tiers, recipient phones must be linked/verified
#    at https://www.circuitdigest.cloud/sms/link-phone.
# ==============================================================================

CIRCUITDIGEST_API_ENDPOINT = "https://www.circuitdigest.cloud/api/v1/send_sms"
DEFAULT_TEMPLATE_ID = 103  # Template 103: "Motion detected by {#var#} in the {#var#}. Investigate immediately."

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "circuitdigest_sms_config.json")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "circuitdigest_sms_history.json")


def mask_phone_number(phone_str: Optional[str]) -> str:
    """Masks phone number for privacy in UI and logs (e.g. '+91 70*** ***71')."""
    if not phone_str:
        return "Not configured"
    cleaned = re.sub(r"[^\d+]", "", str(phone_str).strip())
    if len(cleaned) < 8:
        return cleaned[:2] + "***" + cleaned[-2:] if len(cleaned) >= 4 else "***"
    has_plus = cleaned.startswith("+")
    digits = cleaned[1:] if has_plus else cleaned
    if len(digits) >= 10:
        cc = digits[:-10]
        core = digits[-10:]
        prefix = f"+{cc} " if cc else ("+" if has_plus else "")
        return f"{prefix}{core[:2]}*** ***{core[-2:]}"
    return f"{cleaned[:3]}***{cleaned[-2:]}"


def mask_credential(cred_str: Optional[str], show_prefix: int = 4, show_suffix: int = 4) -> str:
    """Masks secret API key or tokens (e.g. 'cd_12••••••••cdef')."""
    if not cred_str:
        return "Not configured"
    s = str(cred_str).strip()
    if len(s) <= (show_prefix + show_suffix):
        return "••••••••"
    return f"{s[:show_prefix]}••••••••{s[-show_suffix:]}"


def normalize_phone_number(raw_phone: str, default_country_code: str = "91") -> Optional[str]:
    """
    Normalizes phone numbers to standard format for CircuitDigest (e.g. '919876543210').
    Removes '+', dashes, spaces, and leading zeroes.
    """
    if not raw_phone:
        return None
    cleaned = re.sub(r"[^\d]", "", str(raw_phone).strip())
    if not cleaned:
        return None
    # 10-digit Indian number: prepend country code
    if len(cleaned) == 10:
        return f"{default_country_code}{cleaned}"
    # 11-digit with leading 0 (e.g. 09876543210)
    if len(cleaned) == 11 and cleaned.startswith("0"):
        return f"{default_country_code}{cleaned[1:]}"
    # 12-digit already with 91
    if len(cleaned) == 12 and cleaned.startswith("91"):
        return cleaned
    # Other international numbers (between 10 and 15 digits)
    if 10 <= len(cleaned) <= 15:
        return cleaned
    return None


def sanitize_variable(val: Any, max_len: int = 30) -> str:
    """
    Sanitizes variable value for CircuitDigest Cloud template variables:
    1. Truncates to max 30 characters (provider limit).
    2. Strips newlines, tabs, and non-printable characters.
    3. Retains clean ASCII alphanumeric and basic punctuation.
    """
    s = str(val or "").strip()
    s = re.sub(r"[\r\n\t]+", " ", s)
    # Filter to ASCII printable characters
    clean_ascii = "".join(ch for ch in s if 32 <= ord(ch) <= 126)
    return clean_ascii[:max_len].strip()


class CircuitDigestMessageBuilder:
    """
    Generates location-aware bilingual messages and maps detection parameters
    into pre-approved CircuitDigest Cloud template variables.
    """

    @staticmethod
    def format_timestamp(dt: Optional[datetime] = None) -> str:
        if dt is None:
            dt = datetime.now()
        return dt.strftime("%d/%m/%Y, %H:%M:%S")

    @classmethod
    def build_bilingual_audit_text(
        cls,
        count: int,
        location: str,
        state: str = "tamil_nadu",
        group: str = "officer",
        confidence: float = 0.85,
        timestamp_str: Optional[str] = None,
        dashboard_url: str = "https://sairam-elephant-alert.in"
    ) -> str:
        """
        Builds the complete bilingual notification text for local logging, dashboard display,
        and officer/villager inspection.
        Tamil Nadu: English + Tamil
        Karnataka: English + Kannada
        """
        time_display = timestamp_str or cls.format_timestamp()
        count_int = max(1, int(count))
        loc_str = str(location or "Monitoring Zone 1").strip()
        state_key = str(state or "tamil_nadu").strip().lower()
        conf_pct = int(confidence * 100) if 0 < confidence <= 1.0 else int(confidence)

        en_noun = "elephant" if count_int == 1 else "elephants"

        if group == "officer":
            # Officer alert: includes count, location, time, AI confidence, model disclaimer, and link
            if state_key in ("karnataka", "ka"):
                noun_kn = "ಆನೆ" if count_int == 1 else "ಆನೆಗಳು"
                return (
                    f"🚨 [OFFICER ALERT] AI Elephant Detection\n"
                    f"English: AI Camera model detected {count_int} {en_noun} at {loc_str}. "
                    f"Time: {time_display} | AI Confidence: {conf_pct}% (Model prediction, unverified by field staff). "
                    f"Dashboard: {dashboard_url}\n"
                    f"ಕನ್ನಡ: ಕೃತಕ ಬುದ್ಧಿಮತ್ತೆ (AI) ಕ್ಯಾಮೆರಾ {loc_str}ನಲ್ಲಿ {count_int} {noun_kn} ಪತ್ತೆ ಮಾಡಿದೆ. "
                    f"ಸಮಯ: {time_display}. ದಯವಿಟ್ಟು ಪರಿಶೀಲಿಸಿ."
                )
            else:
                noun_ta = "யானை" if count_int == 1 else "யானைகள்"
                return (
                    f"🚨 [OFFICER ALERT] AI Elephant Detection\n"
                    f"English: AI Camera model detected {count_int} {en_noun} at {loc_str}. "
                    f"Time: {time_display} | AI Confidence: {conf_pct}% (Model prediction, unverified by field staff). "
                    f"Dashboard: {dashboard_url}\n"
                    f"தமிழ்: செயற்கை நுண்ணறிவு (AI) கேமரா {loc_str}-ல் {count_int} {noun_ta} கண்டறிந்துள்ளது. "
                    f"நேரம்: {time_display}. கள அலுவலர்கள் உடனடி நடவடிக்கை எடுக்கவும்."
                )
        else:
            # Villager alert: emergency warning, count, location, time, concise safety instructions
            if state_key in ("karnataka", "ka"):
                noun_kn = "ಆನೆ" if count_int == 1 else "ಆನೆಗಳು"
                return (
                    f"🚨 ELEPHANT ALERT!\n"
                    f"English: WARNING: {count_int} {en_noun} detected near {loc_str} at {time_display}. "
                    f"Stay indoors and avoid forest border paths.\n"
                    f"ಕನ್ನಡ: ಎಚ್ಚರಿಕೆ: {loc_str} ಬಳಿ {count_int} {noun_kn} ಪತ್ತೆಯಾಗಿವೆ ({time_display}). "
                    f"ಮನೆಗಳಲ್ಲೇ ಇರಿ ಮತ್ತು ಅರಣ್ಯ ರಸ್ತೆಗಳಿಗೆ ಹೋಗಬೇಡಿ."
                )
            else:
                noun_ta = "யானை" if count_int == 1 else "யானைகள்"
                return (
                    f"🚨 ELEPHANT ALERT!\n"
                    f"English: WARNING: {count_int} {en_noun} detected near {loc_str} at {time_display}. "
                    f"Stay indoors and avoid forest border paths.\n"
                    f"தமிழ்: எச்சரிக்கை: {loc_str} அருகே {count_int} {noun_ta} நடமாட்டம் கண்டறியப்பட்டுள்ளது ({time_display}). "
                    f"வீட்டிலேயே பாதுகாப்பாக இருங்கள்; வன எல்லைக்குச் செல்ல வேண்டாம்."
                )

    @classmethod
    def map_template_variables(
        cls,
        template_id: int,
        count: int,
        location: str,
        group: str = "officer",
        confidence: float = 0.85
    ) -> Tuple[str, str]:
        """
        Maps detection information into the 2 variables supported by CircuitDigest templates.
        Both variables are strictly clamped to max 30 printable ASCII characters.

        Template 103 (Motion Detected):
          "Motion detected by {#var1#} in the {#var2#}. Investigate immediately."
        Template 101 (Device Status):
          "Your {#var1#} is currently at {#var2#}."
        """
        count_int = max(1, int(count))
        noun = "Elephant" if count_int == 1 else "Elephants"
        conf_pct = int(confidence * 100) if 0 < confidence <= 1.0 else int(confidence)
        loc_clean = sanitize_variable(location, max_len=24)

        if template_id == 103:
            if group == "officer":
                # var1: "AI Cam: 2 Elephants (85%)" -> 25 chars
                var1 = sanitize_variable(f"AI Cam: {count_int} {noun} ({conf_pct}%)", 30)
                # var2: "Zone 1 Perimeter" -> <= 30 chars
                var2 = sanitize_variable(f"{loc_clean}", 30)
            else:
                # var1: "AI Early Warning (2 Elephants)" -> <= 30 chars
                var1 = sanitize_variable(f"AI Alert: {count_int} {noun}", 30)
                # var2: "Zone 1 (Stay Indoors)" -> <= 30 chars
                var2 = sanitize_variable(f"{loc_clean} (Stay Safe)", 30)
            return var1, var2

        elif template_id == 101:
            var1 = sanitize_variable("Elephant Warning System", 30)
            if group == "officer":
                var2 = sanitize_variable(f"{count_int} {noun} at {loc_clean}", 30)
            else:
                var2 = sanitize_variable(f"ALERT: {count_int} {noun} {loc_clean}", 30)
            return var1, var2

        else:
            # Fallback for generic templates
            var1 = sanitize_variable(f"Elephant Alert: {count_int} {noun}", 30)
            var2 = sanitize_variable(f"{loc_clean}", 30)
            return var1, var2


class CircuitDigestSmsManager:
    """
    Production-grade manager for CircuitDigest Cloud SMS API:
    - Thread-safe recipient group management (Officers & Villagers)
    - Robust debouncing, cooldown, and count-change policies
    - Absence reset interval (automatic incident closure)
    - Safe masked configuration and audit history
    - Explicit network timeouts and error classification
    """

    COUNT_POLICIES = ["always", "increase_only", "cooldown"]

    def __init__(self, config_path: str = CONFIG_FILE, history_path: str = HISTORY_FILE):
        self.config_path = config_path
        self.history_path = history_path
        self.lock = threading.Lock()

        # Incident Lifecycle Tracking
        self.incident_active = False
        self.current_count = 0
        self.last_alert_time = 0.0
        self.last_detection_time = 0.0
        self.last_alert_details: Optional[Dict[str, Any]] = None

        # Failure throttling
        self.last_failure_time = 0.0
        self.consecutive_failures = 0

        # Load persisted config and history
        self.config = self._load_config()
        self.history = self._load_history()

    # --------------------------------------------------------------------------
    # Persistence Helpers (Atomic File Writes)
    # --------------------------------------------------------------------------

    def _load_config(self) -> Dict[str, Any]:
        """Loads configuration from JSON file with environment variable defaults."""
        defaults: Dict[str, Any] = {
            "enabled": True,
            "api_key": os.getenv("CIRCUITDIGEST_API_KEY", "").strip(),
            "template_id": int(os.getenv("CIRCUITDIGEST_TEMPLATE_ID", str(DEFAULT_TEMPLATE_ID))),
            "state": os.getenv("ALERT_MONITORING_STATE", "tamil_nadu").lower().strip(),
            "location_name": os.getenv("ALERT_MONITORING_LOCATION", "Monitoring Zone 1").strip(),
            "cooldown_seconds": int(os.getenv("ALERT_SMS_COOLDOWN_SECONDS", "300")),
            "count_change_policy": os.getenv("ALERT_COUNT_CHANGE_POLICY", "increase_only").lower().strip(),
            "absence_reset_seconds": int(os.getenv("ALERT_ABSENCE_RESET_SECONDS", "120")),
            "max_daily_limit": 50,
            "recipients": {
                "officers": [],
                "villagers": []
            }
        }

        # Seed initial recipients from environment if provided
        env_officers = os.getenv("CIRCUITDIGEST_OFFICER_PHONES", "").strip()
        if env_officers:
            for num in env_officers.split(","):
                norm = normalize_phone_number(num.strip())
                if norm:
                    defaults["recipients"]["officers"].append({
                        "id": str(uuid.uuid4())[:8],
                        "name": "Range Officer",
                        "phone": norm,
                        "enabled": True,
                        "created_at": datetime.now().isoformat()
                    })

        env_villagers = os.getenv("CIRCUITDIGEST_VILLAGER_PHONES", "").strip()
        if env_villagers:
            for num in env_villagers.split(","):
                norm = normalize_phone_number(num.strip())
                if norm:
                    defaults["recipients"]["villagers"].append({
                        "id": str(uuid.uuid4())[:8],
                        "name": "Village Representative",
                        "phone": norm,
                        "enabled": True,
                        "created_at": datetime.now().isoformat()
                    })

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    defaults.update(saved)
            except Exception as e:
                print(f"[CIRCUITDIGEST-SMS] Notice: Could not read local config ({e}). Using defaults.")

        return defaults

    def _save_config(self) -> bool:
        """Atomically saves configuration to local JSON file to prevent corruption."""
        try:
            dir_name = os.path.dirname(os.path.abspath(self.config_path))
            os.makedirs(dir_name, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
                json.dump(self.config, tf, indent=2)
                temp_name = tf.name
            os.replace(temp_name, self.config_path)
            return True
        except Exception as e:
            print(f"[CIRCUITDIGEST-SMS] Error saving config file: {e}")
            return False

    def _load_history(self) -> List[Dict[str, Any]]:
        """Loads alert history log from file."""
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[CIRCUITDIGEST-SMS] Notice: Could not read history ({e}).")
        return []

    def _append_history(self, record: Dict[str, Any]) -> None:
        """Appends a new dispatch record to in-memory history and atomically writes to file."""
        self.history.append(record)
        # Cap local history to latest 200 records
        if len(self.history) > 200:
            self.history = self.history[-200:]
        try:
            dir_name = os.path.dirname(os.path.abspath(self.history_path))
            os.makedirs(dir_name, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
                json.dump(self.history, tf, indent=2)
                temp_name = tf.name
            os.replace(temp_name, self.history_path)
        except Exception as e:
            print(f"[CIRCUITDIGEST-SMS] Error updating history file: {e}")

    # --------------------------------------------------------------------------
    # Recipient Management API
    # --------------------------------------------------------------------------

    def get_recipients(self) -> Dict[str, List[Dict[str, Any]]]:
        """Returns safe recipient lists with masked phone numbers for UI display."""
        with self.lock:
            recipients = self.config.get("recipients", {"officers": [], "villagers": []})
            masked = {"officers": [], "villagers": []}
            for group in ["officers", "villagers"]:
                for item in recipients.get(group, []):
                    masked[group].append({
                        "id": item.get("id"),
                        "name": item.get("name", "Unknown"),
                        "phone": item.get("phone", ""),
                        "phone_masked": mask_phone_number(item.get("phone")),
                        "enabled": item.get("enabled", True),
                        "created_at": item.get("created_at")
                    })
            return masked

    def add_recipient(self, group: str, name: str, phone: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Adds a new recipient to the specified group (officers or villagers)."""
        if group not in ["officers", "villagers"]:
            return False, f"Invalid recipient group '{group}'. Must be 'officers' or 'villagers'.", None

        normalized = normalize_phone_number(phone)
        if not normalized:
            return False, f"Invalid phone number format: '{phone}'. Expected standard phone number.", None

        clean_name = str(name or "Recipient").strip()[:50]

        with self.lock:
            recipients = self.config.setdefault("recipients", {"officers": [], "villagers": []})
            group_list = recipients.setdefault(group, [])

            # Check duplicate phone
            for item in group_list:
                if item.get("phone") == normalized:
                    return False, f"Phone number {mask_phone_number(normalized)} is already registered in {group}.", None

            new_entry = {
                "id": str(uuid.uuid4())[:8],
                "name": clean_name,
                "phone": normalized,
                "enabled": True,
                "created_at": datetime.now().isoformat()
            }
            group_list.append(new_entry)
            self._save_config()
            return True, f"Successfully added {clean_name} to {group}.", new_entry

    def update_recipient(
        self,
        group: str,
        recipient_id: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Updates an existing recipient's details or toggle active status."""
        if group not in ["officers", "villagers"]:
            return False, f"Invalid group '{group}'.", None

        with self.lock:
            recipients = self.config.get("recipients", {})
            group_list = recipients.get(group, [])

            for item in group_list:
                if item.get("id") == recipient_id:
                    if name is not None:
                        item["name"] = str(name).strip()[:50]
                    if phone is not None:
                        norm = normalize_phone_number(phone)
                        if not norm:
                            return False, f"Invalid phone format: '{phone}'.", None
                        item["phone"] = norm
                    if enabled is not None:
                        item["enabled"] = bool(enabled)
                    self._save_config()
                    return True, "Recipient updated successfully.", item

            return False, f"Recipient with ID '{recipient_id}' not found in {group}.", None

    def delete_recipient(self, group: str, recipient_id: str) -> Tuple[bool, str]:
        """Deletes a recipient from a group."""
        if group not in ["officers", "villagers"]:
            return False, f"Invalid group '{group}'."

        with self.lock:
            recipients = self.config.get("recipients", {})
            group_list = recipients.get(group, [])
            initial_len = len(group_list)
            recipients[group] = [item for item in group_list if item.get("id") != recipient_id]

            if len(recipients[group]) == initial_len:
                return False, f"Recipient with ID '{recipient_id}' not found."

            self._save_config()
            return True, "Recipient removed successfully."

    # --------------------------------------------------------------------------
    # Settings and Safe Status
    # --------------------------------------------------------------------------

    def get_safe_status(self) -> Dict[str, Any]:
        """Returns sanitised status and masked settings for the frontend dashboard."""
        with self.lock:
            api_key = self.config.get("api_key") or os.getenv("CIRCUITDIGEST_API_KEY", "")
            recipients = self.config.get("recipients", {"officers": [], "villagers": []})
            active_officers = sum(1 for o in recipients.get("officers", []) if o.get("enabled", True))
            active_villagers = sum(1 for v in recipients.get("villagers", []) if v.get("enabled", True))

            # Count SMS sent today
            today_str = datetime.now().strftime("%Y-%m-%d")
            today_count = sum(
                1 for h in self.history
                if h.get("timestamp", "").startswith(today_str) and h.get("success")
            )

            return {
                "enabled": self.config.get("enabled", True),
                "is_configured": bool(api_key),
                "api_key_masked": mask_credential(api_key, 4, 4),
                "template_id": self.config.get("template_id", DEFAULT_TEMPLATE_ID),
                "state": self.config.get("state", "tamil_nadu"),
                "location_name": self.config.get("location_name", "Monitoring Zone 1"),
                "cooldown_seconds": self.config.get("cooldown_seconds", 300),
                "count_change_policy": self.config.get("count_change_policy", "increase_only"),
                "absence_reset_seconds": self.config.get("absence_reset_seconds", 120),
                "incident_active": self.incident_active,
                "current_count": self.current_count,
                "last_alert_time": self.last_alert_time,
                "last_alert_details": self.last_alert_details,
                "today_sms_sent": today_count,
                "max_daily_limit": self.config.get("max_daily_limit", 50),
                "active_officers_count": active_officers,
                "active_villagers_count": active_villagers,
                "total_recipients_count": active_officers + active_villagers
            }

    def save_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Safely updates settings, ignoring None values and sanitizing inputs."""
        with self.lock:
            if "enabled" in updates:
                self.config["enabled"] = bool(updates["enabled"])
            if "api_key" in updates and str(updates["api_key"]).strip():
                self.config["api_key"] = str(updates["api_key"]).strip()
            if "template_id" in updates:
                try:
                    self.config["template_id"] = int(updates["template_id"])
                except (ValueError, TypeError):
                    pass
            if "state" in updates:
                self.config["state"] = str(updates["state"]).lower().strip()
            if "location_name" in updates:
                self.config["location_name"] = str(updates["location_name"]).strip()
            if "cooldown_seconds" in updates:
                self.config["cooldown_seconds"] = max(30, int(updates["cooldown_seconds"]))
            if "count_change_policy" in updates:
                pol = str(updates["count_change_policy"]).lower().strip()
                if pol in self.COUNT_POLICIES:
                    self.config["count_change_policy"] = pol
            if "absence_reset_seconds" in updates:
                self.config["absence_reset_seconds"] = max(10, int(updates["absence_reset_seconds"]))

            self._save_config()
            return self.get_safe_status()

    # --------------------------------------------------------------------------
    # Core HTTP Dispatch Engine
    # --------------------------------------------------------------------------

    def send_single_sms(
        self,
        mobile: str,
        var1: str,
        var2: str,
        template_id: Optional[int] = None,
        audit_note: str = ""
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes a single HTTP POST request to CircuitDigest Cloud SMS API.
        Endpoint: POST https://www.circuitdigest.cloud/api/v1/send_sms?ID={template_id}
        Headers:
          Authorization: <API_KEY>
          Content-Type: application/json
        Body:
          {"mobiles": "91...", "var1": "...", "var2": "..."}
        """
        api_key = self.config.get("api_key") or os.getenv("CIRCUITDIGEST_API_KEY", "").strip()
        if not api_key:
            return False, "CircuitDigest API key is not configured.", {}

        normalized_mobile = normalize_phone_number(mobile)
        if not normalized_mobile:
            return False, f"Invalid recipient mobile number: '{mobile}'.", {}

        tid = template_id or self.config.get("template_id", DEFAULT_TEMPLATE_ID)
        v1 = sanitize_variable(var1, max_len=30)
        v2 = sanitize_variable(var2, max_len=30)

        url = f"{CIRCUITDIGEST_API_ENDPOINT}?ID={tid}"
        headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "mobiles": normalized_mobile,
            "var1": v1,
            "var2": v2
        }

        # Structured audit record
        record: Dict[str, Any] = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(),
            "provider": "circuitdigest",
            "template_id": tid,
            "recipient_mobile": normalized_mobile,
            "recipient_masked": mask_phone_number(normalized_mobile),
            "var1": v1,
            "var2": v2,
            "audit_note": audit_note,
            "success": False,
            "response_status": 0,
            "error": None
        }

        try:
            # Explicit connection timeout (5s) and read timeout (10s)
            resp = requests.post(url, headers=headers, json=payload, timeout=(5.0, 10.0))
            record["response_status"] = resp.status_code

            try:
                resp_json = resp.json()
                if isinstance(resp_json, (dict, list, str, int, float, bool)):
                    record["response_body"] = resp_json
                else:
                    record["response_body"] = str(resp_json)
            except Exception:
                record["response_body"] = str(getattr(resp, "text", ""))[:200]

            if resp.status_code == 200:
                record["success"] = True
                self.consecutive_failures = 0
                self._append_history(record)
                return True, "SMS dispatched successfully via CircuitDigest Cloud.", record
            elif resp.status_code == 401:
                msg = "Authentication failure: Invalid or expired CircuitDigest API key."
                record["error"] = msg
                self.consecutive_failures += 1
                self._append_history(record)
                return False, msg, record
            elif resp.status_code == 429:
                msg = "CircuitDigest Cloud daily or rate limit exceeded. Please wait before retrying."
                record["error"] = msg
                self._append_history(record)
                return False, msg, record
            else:
                msg = f"CircuitDigest API returned HTTP {resp.status_code}: {resp.text[:120]}"
                record["error"] = msg
                self.consecutive_failures += 1
                self._append_history(record)
                return False, msg, record

        except requests.exceptions.Timeout:
            msg = "Connection timed out while communicating with CircuitDigest Cloud."
            record["error"] = msg
            self.consecutive_failures += 1
            self._append_history(record)
            return False, msg, record
        except requests.exceptions.RequestException as e:
            msg = f"Network connection error to CircuitDigest: {e}"
            record["error"] = msg
            self.consecutive_failures += 1
            self._append_history(record)
            return False, msg, record
        except Exception as e:
            msg = f"Unexpected error during dispatch: {e}"
            record["error"] = msg
            self._append_history(record)
            return False, msg, record

    def validate_api_key(self, api_key_override: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates API key format without sending an unauthorized SMS.
        """
        key = (api_key_override or self.config.get("api_key") or os.getenv("CIRCUITDIGEST_API_KEY", "")).strip()
        if not key:
            return False, "API key is missing or empty.", {"configured": False}

        if len(key) < 8:
            return False, "API key appears too short to be a valid CircuitDigest token.", {"configured": False}

        # Check format
        return True, "CircuitDigest API key syntax is valid.", {
            "configured": True,
            "masked_key": mask_credential(key),
            "endpoint": CIRCUITDIGEST_API_ENDPOINT,
            "template_id": self.config.get("template_id", DEFAULT_TEMPLATE_ID)
        }

    # --------------------------------------------------------------------------
    # Detection Evaluation & Alert Dispatch Engine
    # --------------------------------------------------------------------------

    def evaluate_and_dispatch(
        self,
        elephant_count: int,
        confidence: float,
        location: str,
        timestamp: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Evaluates detection against debouncing policies and dispatches alerts to
        configured Officer and Villager groups.
        """
        if not self.config.get("enabled", True):
            return False, "CircuitDigest SMS alerting is disabled in configuration.", {}

        api_key = self.config.get("api_key") or os.getenv("CIRCUITDIGEST_API_KEY", "").strip()
        if not api_key:
            return False, "CircuitDigest API key is not configured.", {}

        now = time.time()
        self.last_detection_time = now
        count_int = max(0, int(elephant_count))

        # Check absence reset interval
        absence_reset = self.config.get("absence_reset_seconds", 120)
        if self.incident_active and (now - self.last_alert_time) > absence_reset:
            if count_int == 0:
                print(f"[CIRCUITDIGEST-SMS] Incident lifecycle closed: No elephants detected for >{absence_reset}s.")
                self.incident_active = False
                self.current_count = 0
                return False, "Incident closed: Absence threshold passed.", {}

        if count_int == 0:
            return False, "No elephants present in detection frame.", {}

        # Debounce and policy evaluation
        should_send = False
        trigger_reason = ""
        cooldown = self.config.get("cooldown_seconds", 300)
        policy = self.config.get("count_change_policy", "increase_only")

        if not self.incident_active:
            should_send = True
            trigger_reason = f"Initial incident detection ({count_int} elephants)"
        else:
            time_since_last = now - self.last_alert_time
            if policy == "always":
                if time_since_last >= cooldown:
                    should_send = True
                    trigger_reason = f"Periodic alert after cooldown ({int(time_since_last)}s)"
            elif policy == "increase_only":
                if count_int > self.current_count:
                    should_send = True
                    trigger_reason = f"Elephant count increased ({self.current_count} -> {count_int})"
                elif time_since_last >= cooldown:
                    should_send = True
                    trigger_reason = f"Cooldown reminder for active incident ({count_int} elephants)"
            elif policy == "cooldown":
                if time_since_last >= cooldown:
                    should_send = True
                    trigger_reason = f"Cooldown interval reached ({int(time_since_last)}s)"

        if not should_send:
            return False, f"Alert suppressed by policy '{policy}' (Last alert: {int(now - self.last_alert_time)}s ago).", {}

        # Update state machine
        self.incident_active = True
        self.current_count = count_int
        self.last_alert_time = now

        # Prepare variables
        template_id = self.config.get("template_id", DEFAULT_TEMPLATE_ID)
        state = self.config.get("state", "tamil_nadu")
        loc_name = location or self.config.get("location_name", "Monitoring Zone 1")

        recipients = self.config.get("recipients", {"officers": [], "villagers": []})
        dispatched_count = 0
        results: List[Dict[str, Any]] = []

        # 1. Dispatch to Forest Officers
        officer_v1, officer_v2 = CircuitDigestMessageBuilder.map_template_variables(
            template_id=template_id,
            count=count_int,
            location=loc_name,
            group="officer",
            confidence=confidence
        )
        for officer in recipients.get("officers", []):
            if officer.get("enabled", True):
                phone = officer.get("phone")
                ok, msg, rec = self.send_single_sms(
                    mobile=phone,
                    var1=officer_v1,
                    var2=officer_v2,
                    template_id=template_id,
                    audit_note=f"Officer Alert: {trigger_reason}"
                )
                results.append({"group": "officer", "recipient": mask_phone_number(phone), "success": ok, "message": msg})
                if ok:
                    dispatched_count += 1

        # 2. Dispatch to Local Villagers
        villager_v1, villager_v2 = CircuitDigestMessageBuilder.map_template_variables(
            template_id=template_id,
            count=count_int,
            location=loc_name,
            group="villager",
            confidence=confidence
        )
        for villager in recipients.get("villagers", []):
            if villager.get("enabled", True):
                phone = villager.get("phone")
                ok, msg, rec = self.send_single_sms(
                    mobile=phone,
                    var1=villager_v1,
                    var2=villager_v2,
                    template_id=template_id,
                    audit_note=f"Villager Alert: {trigger_reason}"
                )
                results.append({"group": "villager", "recipient": mask_phone_number(phone), "success": ok, "message": msg})
                if ok:
                    dispatched_count += 1

        self.last_alert_details = {
            "timestamp": datetime.now().isoformat(),
            "count": count_int,
            "location": loc_name,
            "reason": trigger_reason,
            "dispatched_count": dispatched_count,
            "recipients_total": len(results)
        }

        return True, f"Dispatched alerts to {dispatched_count} active recipients ({trigger_reason}).", {
            "dispatched_count": dispatched_count,
            "results": results
        }

    def process_detection_async(
        self,
        elephant_count: int,
        confidence: float = 0.85,
        location: str = "Monitoring Zone 1",
        timestamp: Optional[str] = None
    ) -> None:
        """Non-blocking background thread worker to evaluate and dispatch detection alerts."""
        def _worker():
            try:
                self.evaluate_and_dispatch(
                    elephant_count=elephant_count,
                    confidence=confidence,
                    location=location,
                    timestamp=timestamp
                )
            except Exception as e:
                print(f"[CIRCUITDIGEST-SMS] Background dispatch error: {e}")

        thread = threading.Thread(target=_worker, daemon=True, name="CircuitDigestSmsDispatcher")
        thread.start()


# ==============================================================================
# SINGLETON INSTANCE ACCESS
# ==============================================================================

_CIRCUITDIGEST_SMS_MANAGER_INSTANCE: Optional[CircuitDigestSmsManager] = None


def get_circuitdigest_sms_manager() -> CircuitDigestSmsManager:
    """Returns the singleton instance of CircuitDigestSmsManager."""
    global _CIRCUITDIGEST_SMS_MANAGER_INSTANCE
    if _CIRCUITDIGEST_SMS_MANAGER_INSTANCE is None:
        _CIRCUITDIGEST_SMS_MANAGER_INSTANCE = CircuitDigestSmsManager()
    return _CIRCUITDIGEST_SMS_MANAGER_INSTANCE
