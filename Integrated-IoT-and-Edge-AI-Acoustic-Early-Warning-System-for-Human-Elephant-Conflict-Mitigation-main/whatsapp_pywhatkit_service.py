"""
WhatsApp Alert Service via PyWhatKit
Department of AI & ML, Sri Sairam College of Engineering

Provides asynchronous, non-blocking WhatsApp alert dispatching using PyWhatKit.
- Strict trilingual message content (English -> Kannada -> Tamil)
- Independent enable/disable control (WHATSAPP_ALERTS_ENABLED)
- Non-blocking background worker queue (never blocks camera/detection pipeline)
- Duplicate alert deduplication and configurable cooldown
- International phone normalization (+91...) and privacy masking
- Clear lifecycle states: QUEUED, SENDING, ATTEMPT_COMPLETED, FAILED
- Explicit limitations: WhatsApp Web browser automation requires active desktop session.
"""

import os
import re
import json
import time
import queue
import logging
import inspect
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from dotenv import load_dotenv
from trilingual_message_builder import build_trilingual_alert

load_dotenv()
logger = logging.getLogger("whatsapp_pywhatkit")


def normalize_phone_number(phone: str, default_prefix: str = "+91") -> Tuple[Optional[str], Optional[str]]:
    """
    Normalizes phone numbers to standard E.164 international format.
    Accepts '+917094528671', '7094528671', '07094528671', etc.
    Returns: (normalized_phone, error_message)
    """
    if not phone or not str(phone).strip():
        return None, "Phone number is empty or missing."

    raw = str(phone).strip()
    # Remove whitespace, dashes, brackets
    cleaned = re.sub(r"[\s\-\(\)]", "", raw)

    if cleaned.startswith("+"):
        digits = re.sub(r"[^\d]", "", cleaned[1:])
        if len(digits) < 10 or len(digits) > 15:
            return None, f"Invalid international phone length (+{digits})."
        return f"+{digits}", None
    elif cleaned.startswith("0") and len(cleaned) == 11:
        # Standard Indian 0-prefixed 10-digit number
        digits = cleaned[1:]
        return f"{default_prefix}{digits}", None
    elif len(cleaned) == 10 and cleaned.isdigit():
        return f"{default_prefix}{cleaned}", None
    elif len(cleaned) == 12 and cleaned.startswith("91") and cleaned.isdigit():
        return f"+{cleaned}", None
    else:
        # General numeric fallback
        digits = re.sub(r"[^\d]", "", cleaned)
        if len(digits) >= 10:
            return f"+{digits}", None
        return None, f"Unrecognized phone number format: {phone}"


def mask_phone_number(phone: Optional[str]) -> str:
    """Masks a phone number for safe display in logs and UI (e.g. +91 70••••671)."""
    if not phone:
        return "Not configured"
    s = str(phone).strip()
    digits = re.sub(r"[^\d]", "", s)
    if len(digits) >= 10:
        prefix = f"+{digits[:2]} " if len(digits) > 10 else ""
        local = digits[-10:]
        return f"{prefix}{local[:2]}••••{local[-3:]}"
    elif len(digits) > 4:
        return f"••••{digits[-4:]}"
    return "••••"


def safe_sendwhatmsg_instantly(
    phone_no: str,
    message: str,
    wait_time: int = 25,
    tab_close: bool = False,
    close_time: int = 3,
) -> None:
    """
    Enhanced sendwhatmsg_instantly that handles multilingual Unicode text and Windows URL limits.
    1. If the message URL exceeds ~1800 chars (like Indic Kannada/Tamil UTF-8), copies
       message to the system clipboard and opens a clean chat URL, then pastes using Ctrl+V.
    2. For short messages, falls back to standard URL query encoding.
    """
    import time
    import webbrowser
    import pyautogui as pg
    import pyperclip
    import pywhatkit.core.core as core
    import pywhatkit.core.exceptions as exceptions
    from urllib.parse import quote

    if not core.check_number(number=phone_no):
        raise exceptions.CountryCodeException("Country Code Missing in Phone Number!")

    test_url = f"https://web.whatsapp.com/send?phone={phone_no}&text={quote(message)}"

    if len(test_url) <= 1800:
        logger.info(f"[WHATSAPP] Dispatching standard short URL ({len(test_url)} chars)")
        webbrowser.open(test_url)
        time.sleep(4)
        pg.click(core.WIDTH / 2, core.HEIGHT / 2)
        time.sleep(max(1, wait_time - 4))
        pg.press("enter")
    else:
        logger.info(
            f"[WHATSAPP] Multilingual message produces {len(test_url)} encoded chars (exceeds Windows limit). "
            f"Using clipboard paste automation."
        )
        # Put full trilingual message onto clipboard
        pyperclip.copy(message)

        # Open clean WhatsApp Web URL for this recipient
        clean_url = f"https://web.whatsapp.com/send?phone={phone_no}"
        webbrowser.open(clean_url)

        # Allow browser to open and become active window
        time.sleep(5)
        pg.click(core.WIDTH / 2, core.HEIGHT / 2)

        # Wait remaining time for WhatsApp Web to load the conversation
        wait_remaining = max(8, wait_time - 5)
        time.sleep(wait_remaining)

        # Click the chat box area at the bottom of the conversation window
        # In WhatsApp Web, the input box is at the bottom of the screen
        chat_box_x = int(core.WIDTH * 0.6)
        chat_box_y = int(core.HEIGHT - 70)
        pg.click(chat_box_x, chat_box_y)
        time.sleep(1)

        # Paste message from clipboard
        pg.hotkey("ctrl", "v")
        time.sleep(1)

        # Press Enter to send
        pg.press("enter")

    time.sleep(2)
    if tab_close:
        core.close_tab(wait_time=close_time)


# Monkey-patch pywhatkit.sendwhatmsg_instantly so all standard callers benefit
try:
    import pywhatkit
    pywhatkit.sendwhatmsg_instantly = safe_sendwhatmsg_instantly
except Exception as _patch_err:
    logger.warning(f"[WHATSAPP] Could not monkey-patch pywhatkit: {_patch_err}")


class WhatsAppPyWhatKitService:
    """
    Dedicated WhatsApp notification service powered by PyWhatKit.
    Ensures safe, thread-safe, non-blocking execution via background queue.
    """

    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_config.json")
    HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_history.json")

    # Delivery status constants
    STATUS_QUEUED = "QUEUED"
    STATUS_SENDING = "SENDING"
    STATUS_ATTEMPT_COMPLETED = "ATTEMPT_COMPLETED"
    STATUS_FAILED = "FAILED"
    STATUS_SKIPPED = "SKIPPED"

    def __init__(self):
        self.lock = threading.Lock()
        self.config = self._load_config()
        self.history = self._load_history()

        # Cooldown state tracking
        self.last_alert_time: float = 0.0
        self.last_elephant_count: int = 0
        self.last_location: str = ""

        # Background worker queue to prevent blocking camera / detection pipeline
        self.queue: queue.Queue = queue.Queue(maxsize=30)
        self.is_sending: bool = False
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="WhatsAppQueueWorker")
        self.worker_thread.start()

    def _load_config(self) -> Dict[str, Any]:
        """Loads configuration from JSON file with environment variable fallbacks."""
        # Check environment variables
        env_enabled = os.getenv("WHATSAPP_ALERTS_ENABLED", "false").strip().lower() in ("true", "1", "yes")
        env_target = os.getenv("WHATSAPP_TARGET_PHONE") or os.getenv("WHATSAPP_RECIPIENT", "+917094528671")
        env_cooldown = int(os.getenv("ELEPHANT_ALERT_COOLDOWN_SECONDS", "120"))
        env_wait_time = int(os.getenv("WHATSAPP_WAIT_TIME", "30"))
        env_tab_close = os.getenv("WHATSAPP_TAB_CLOSE", "false").strip().lower() in ("true", "1", "yes")

        defaults = {
            "enabled": env_enabled,
            "wait_time": env_wait_time,
            "tab_close": env_tab_close,
            "close_time": 3,
            "cooldown_seconds": env_cooldown,
            "default_phone": env_target,
            "recipients": {
                "officers": [
                    {
                        "id": "officer_default",
                        "name": "Range Officer",
                        "phone": env_target,
                        "role": "officer",
                        "enabled": True
                    }
                ],
                "villagers": []
            }
        }

        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    defaults.update(saved)
            except Exception as e:
                logger.warning(f"[WHATSAPP] Failed to read {self.CONFIG_FILE}: {e}")

        return defaults

    def _save_config(self):
        """Persists configuration to disk."""
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.error(f"[WHATSAPP] Failed to save {self.CONFIG_FILE}: {e}")

    def _load_history(self) -> List[Dict[str, Any]]:
        """Loads recent alert dispatch history."""
        if os.path.exists(self.HISTORY_FILE):
            try:
                with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[-50:]
            except Exception:
                pass
        return []

    def _record_history(self, record: Dict[str, Any]):
        """Records dispatch result in memory and persists to history file."""
        with self.lock:
            self.history.append(record)
            if len(self.history) > 50:
                self.history.pop(0)

            try:
                with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.history, f, indent=2)
            except Exception:
                pass

    def get_history(self) -> List[Dict[str, Any]]:
        """Returns history sorted newest first."""
        with self.lock:
            return list(reversed(self.history))

    def is_enabled(self) -> bool:
        """Checks if WhatsApp alerts are currently enabled."""
        return bool(self.config.get("enabled", False))

    def set_enabled(self, enabled: bool):
        """Enables or disables WhatsApp alerts independently of Telegram."""
        with self.lock:
            self.config["enabled"] = bool(enabled)
            self._save_config()

    def get_cooldown_seconds(self) -> int:
        return int(self.config.get("cooldown_seconds", 120))

    def should_send_alert(self, current_count: int, location: str = "Monitoring Zone 1") -> Tuple[bool, str]:
        """
        Duplicate-alert prevention and cooldown check.
        Ensures alerts are not sent repeatedly for the same ongoing sighting.
        """
        if not self.is_enabled():
            return False, "WhatsApp alerts disabled (WHATSAPP_ALERTS_ENABLED=false)."

        if current_count <= 0:
            return False, "Elephant count is zero; no alert required."

        now = time.time()
        cooldown = self.get_cooldown_seconds()
        elapsed = now - self.last_alert_time

        with self.lock:
            # Active in-flight check: don't spawn overlapping browser tabs
            if self.is_sending:
                return False, "WhatsApp delivery already in progress in background."

            if self.last_alert_time > 0 and elapsed < cooldown:
                remaining = round(cooldown - elapsed, 1)
                return False, f"Cooldown active ({remaining}s remaining for {location})."

            return True, "Cooldown satisfied."

    def get_active_recipients(self, group: Optional[str] = None) -> List[str]:
        """
        Retrieves normalized, validated active recipient phone numbers.
        Avoids duplicates.
        """
        recipients_map = self.config.get("recipients", {})
        phones = []

        target_groups = [group] if group in ("officers", "villagers") else ["officers", "villagers"]
        for grp in target_groups:
            for item in recipients_map.get(grp, []):
                if item.get("enabled", True):
                    phone = item.get("phone")
                    norm, err = normalize_phone_number(phone)
                    if norm and norm not in phones:
                        phones.append(norm)

        # Fallback to default_phone if recipients list is empty
        if not phones:
            default_p = self.config.get("default_phone")
            norm, err = normalize_phone_number(default_p)
            if norm:
                phones.append(norm)

        return phones

    def queue_elephant_alert(self, elephant_count: int = 1,
                             location: str = "Monitoring Zone 1",
                             timestamp: Optional[Any] = None,
                             recipients: Optional[List[str]] = None,
                             force: bool = False) -> Dict[str, Any]:
        """
        Non-blocking: Enqueues an elephant alert to be sent to WhatsApp recipients.
        Returns immediately so camera detection is NEVER blocked.
        """
        try:
            count_int = max(1, int(float(elephant_count)))
        except (ValueError, TypeError):
            count_int = 1

        if not force:
            should_send, reason = self.should_send_alert(count_int, location)
            if not should_send:
                return {
                    "queued": False,
                    "reason": reason,
                    "status": self.STATUS_SKIPPED
                }

        target_phones = recipients or self.get_active_recipients()
        if not target_phones:
            return {
                "queued": False,
                "reason": "No valid WhatsApp recipients configured.",
                "status": self.STATUS_FAILED
            }

        # Build shared trilingual message
        message_text = build_trilingual_alert(
            elephant_count=count_int,
            location=location,
            timestamp=timestamp
        )

        task = {
            "event_id": f"wa_alert_{int(time.time()*1000)}",
            "elephant_count": count_int,
            "location": location,
            "message": message_text,
            "recipients": target_phones,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "force": force
        }

        try:
            self.queue.put_nowait(task)
            with self.lock:
                self.last_alert_time = time.time()
                self.last_elephant_count = count_int
                self.last_location = location

            return {
                "queued": True,
                "event_id": task["event_id"],
                "status": self.STATUS_QUEUED,
                "recipients_count": len(target_phones),
                "masked_recipients": [mask_phone_number(p) for p in target_phones]
            }
        except queue.Full:
            return {
                "queued": False,
                "reason": "WhatsApp worker queue is full.",
                "status": self.STATUS_FAILED
            }

    def _worker_loop(self):
        """Sequential background worker handling WhatsApp dispatch."""
        while True:
            try:
                task = self.queue.get()
                if task is None:
                    break
                self._execute_dispatch(task)
            except Exception as e:
                logger.error(f"[WHATSAPP-WORKER] Unexpected error: {e}")
            finally:
                self.queue.task_done()

    def _execute_dispatch(self, task: Dict[str, Any]):
        """Dispatches a single queued WhatsApp task using PyWhatKit."""
        recipients = task.get("recipients", [])
        message = task.get("message", "")
        event_id = task.get("event_id", "wa_unknown")
        count = task.get("elephant_count", 1)
        location = task.get("location", "Monitoring Zone 1")

        wait_time = int(self.config.get("wait_time", 30))
        tab_close = bool(self.config.get("tab_close", False))
        close_time = int(self.config.get("close_time", 3))

        with self.lock:
            self.is_sending = True

        for phone in recipients:
            start_ts = time.time()
            record = {
                "event_id": event_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elephant_count": count,
                "location": location,
                "recipient_masked": mask_phone_number(phone),
                "method": "whatsapp_pywhatkit",
                "status": self.STATUS_SENDING,
                "details": "Dispatching to WhatsApp Web via PyWhatKit...",
                "duration_s": 0.0
            }

            try:
                import pywhatkit

                sig = inspect.signature(pywhatkit.sendwhatmsg_instantly)
                kwargs = {
                    "phone_no": phone,
                    "message": message,
                    "wait_time": wait_time
                }
                if "tab_close" in sig.parameters:
                    kwargs["tab_close"] = tab_close
                if "close_time" in sig.parameters:
                    kwargs["close_time"] = close_time

                logger.info(f"[WHATSAPP] Sending alert to {mask_phone_number(phone)} (wait_time={wait_time}s)...")
                pywhatkit.sendwhatmsg_instantly(**kwargs)

                duration = round(time.time() - start_ts, 2)
                record["status"] = self.STATUS_ATTEMPT_COMPLETED
                record["duration_s"] = duration
                record["details"] = (
                    "Send keystroke completed via WhatsApp Web. "
                    "Notice: Actual cellular handset receipt depends on active WhatsApp Web desktop session."
                )
                logger.info(f"[WHATSAPP] Completed send attempt for {mask_phone_number(phone)} in {duration}s")

            except Exception as e:
                duration = round(time.time() - start_ts, 2)
                err_msg = str(e)
                record["status"] = self.STATUS_FAILED
                record["duration_s"] = duration
                record["details"] = f"PyWhatKit error: {err_msg}"
                logger.error(f"[WHATSAPP] Error sending to {mask_phone_number(phone)}: {err_msg}")

            self._record_history(record)

        with self.lock:
            self.is_sending = False

    def send_single_test_message(self, phone: str, count: int = 3,
                                 location: str = "Monitoring Zone 1",
                                 confirmed: bool = False) -> Dict[str, Any]:
        """
        Safe single test message dispatch.
        Requires confirmed=True to actually invoke PyWhatKit.
        """
        norm_phone, err = normalize_phone_number(phone)
        if err or not norm_phone:
            return {
                "success": False,
                "status": self.STATUS_FAILED,
                "error": err or "Invalid phone number."
            }

        preview_msg = build_trilingual_alert(
            elephant_count=count,
            location=location
        )

        masked_phone = mask_phone_number(norm_phone)

        if not confirmed:
            return {
                "success": True,
                "status": "DRY_RUN",
                "can_send": True,
                "masked_recipient": masked_phone,
                "preview_message": preview_msg,
                "notice": "Dry-run only. Pass confirmed=True or --confirm to execute via PyWhatKit."
            }

        # Confirmed execution
        wait_time = int(self.config.get("wait_time", 30))
        tab_close = bool(self.config.get("tab_close", False))
        close_time = int(self.config.get("close_time", 3))

        start_ts = time.time()
        try:
            import pywhatkit
            sig = inspect.signature(pywhatkit.sendwhatmsg_instantly)
            kwargs = {
                "phone_no": norm_phone,
                "message": preview_msg,
                "wait_time": wait_time
            }
            if "tab_close" in sig.parameters:
                kwargs["tab_close"] = tab_close
            if "close_time" in sig.parameters:
                kwargs["close_time"] = close_time

            pywhatkit.sendwhatmsg_instantly(**kwargs)
            dur = round(time.time() - start_ts, 2)

            record = {
                "event_id": f"test_wa_{int(time.time()*1000)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elephant_count": count,
                "location": location,
                "recipient_masked": masked_phone,
                "method": "whatsapp_pywhatkit",
                "status": self.STATUS_ATTEMPT_COMPLETED,
                "details": "Test message sent to WhatsApp Web. Requires logged-in browser session.",
                "duration_s": dur
            }
            self._record_history(record)

            return {
                "success": True,
                "status": self.STATUS_ATTEMPT_COMPLETED,
                "masked_recipient": masked_phone,
                "duration_s": dur,
                "details": record["details"]
            }

        except Exception as e:
            dur = round(time.time() - start_ts, 2)
            record = {
                "event_id": f"test_wa_{int(time.time()*1000)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elephant_count": count,
                "location": location,
                "recipient_masked": masked_phone,
                "method": "whatsapp_pywhatkit",
                "status": self.STATUS_FAILED,
                "details": f"Test send failed: {str(e)}",
                "duration_s": dur
            }
            self._record_history(record)

            return {
                "success": False,
                "status": self.STATUS_FAILED,
                "error": str(e),
                "masked_recipient": masked_phone,
                "duration_s": dur
            }

    def get_status_summary(self) -> Dict[str, Any]:
        """Provides status summary for dashboard and API."""
        recent_history = self.get_history()
        last_attempt = recent_history[0] if recent_history else None

        active_recipients = self.get_active_recipients()
        elapsed = time.time() - self.last_alert_time if self.last_alert_time > 0 else 9999
        cooldown = self.get_cooldown_seconds()
        in_cooldown = elapsed < cooldown

        return {
            "whatsapp_enabled": self.is_enabled(),
            "wait_time": self.config.get("wait_time", 15),
            "cooldown_seconds": cooldown,
            "in_cooldown": in_cooldown,
            "cooldown_remaining_s": max(0, round(cooldown - elapsed, 1)) if in_cooldown else 0,
            "recipients_count": len(active_recipients),
            "masked_recipients": [mask_phone_number(p) for p in active_recipients],
            "last_attempt": last_attempt,
            "is_sending": self.is_sending,
            "queue_size": self.queue.qsize(),
            "limitations_notice": "PyWhatKit depends on active desktop WhatsApp Web session. Delivery cannot be verified without handset acknowledgment."
        }


# Global Singleton Instance
_GLOBAL_WHATSAPP_SERVICE: Optional[WhatsAppPyWhatKitService] = None

def get_whatsapp_service() -> WhatsAppPyWhatKitService:
    global _GLOBAL_WHATSAPP_SERVICE
    if _GLOBAL_WHATSAPP_SERVICE is None:
        _GLOBAL_WHATSAPP_SERVICE = WhatsAppPyWhatKitService()
    return _GLOBAL_WHATSAPP_SERVICE
