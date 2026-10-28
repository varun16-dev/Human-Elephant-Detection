"""
Free Alert Service for Integrated IoT & Edge-AI Early Warning System
Department of AI & ML, Sri Sairam College of Engineering

ZERO THIRD-PARTY API COST NOTIFICATION ENGINE
- Option A: Telegram Bot API (Direct push notifications to Telegram app / groups / channels)
- Option B: Carrier Email-to-SMS Gateway (Free SMTP relay to mobile carrier email gateways)
- Redundant Dual Broadcast: Simultaneously dispatch across both pathways

Notice on Delivery Verification:
- Telegram: Returns whether Telegram Bot API accepted the payload for delivery.
- Carrier SMS: Returns whether the SMTP server accepted the email for carrier relay.
  Cellular handset receipt cannot be confirmed via SMTP alone without carrier SMS receipts.
"""

import os
import sys
import re
import json
import time
import html
import smtplib
import ssl
import threading
from email.mime.text import MIMEText
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# CARRIER EMAIL-TO-SMS GATEWAY REGISTRY (NORTH AMERICA)
# ==============================================================================
# Carriers provide free email-to-SMS / MMS gateways that translate an incoming
# email directly into a cellular SMS message delivered to the recipient's phone.
# NOTE: Indian telecom carriers (Airtel, Jio, Vi) discontinued open email-to-sms
# gateways following TRAI DLT regulations. Indian users must use Option A (Telegram).
CARRIER_GATEWAYS = {
    "verizon": {
        "name": "Verizon Wireless",
        "sms": "vtext.com",
        "mms": "vzwpix.com",
        "region": "US"
    },
    "att": {
        "name": "AT&T Mobility",
        "sms": "txt.att.net",
        "mms": "mms.att.net",
        "region": "US"
    },
    "tmobile": {
        "name": "T-Mobile",
        "sms": "tmomail.net",
        "mms": "tmomail.net",
        "region": "US"
    },
    "sprint": {
        "name": "Sprint (T-Mobile)",
        "sms": "messaging.sprintpcs.com",
        "mms": "pm.sprint.com",
        "region": "US"
    },
    "uscellular": {
        "name": "US Cellular",
        "sms": "email.uscc.net",
        "mms": "mms.uscc.net",
        "region": "US"
    },
    "boost": {
        "name": "Boost Mobile",
        "sms": "sms.myboostmobile.com",
        "mms": "myboostmobile.com",
        "region": "US"
    },
    "cricket": {
        "name": "Cricket Wireless",
        "sms": "mms.cricketwireless.net",
        "mms": "mms.cricketwireless.net",
        "region": "US"
    },
    "metropcs": {
        "name": "Metro by T-Mobile",
        "sms": "mymetropcs.com",
        "mms": "mymetropcs.com",
        "region": "US"
    },
    "rogers": {
        "name": "Rogers Wireless",
        "sms": "pcs.rogers.com",
        "mms": "mms.rogers.com",
        "region": "CA"
    },
    "bell": {
        "name": "Bell Mobility",
        "sms": "txt.bell.ca",
        "mms": "txt.bell.ca",
        "region": "CA"
    },
    "telus": {
        "name": "Telus",
        "sms": "msg.telus.com",
        "mms": "msg.telus.com",
        "region": "CA"
    },
    "custom": {
        "name": "Custom Carrier Domain",
        "sms": "",
        "mms": "",
        "region": "Custom"
    }
}


# ==============================================================================
# OPTION A: TELEGRAM BOT DISPATCHER
# ==============================================================================
class TelegramAlertDispatcher:
    """
    Dispatches alerts via the Telegram Bot API ($0 API tier).
    Supports individual chat IDs, channels, and group broadcasts.
    Includes input escaping, photo attachments, and bounded retries.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token=None, default_chat_id=None, timeout=10):
        self.bot_token = bot_token if bot_token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.default_chat_id = default_chat_id if default_chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.timeout = timeout or 10  # seconds

    def is_configured(self):
        """Check if minimum required credentials exist"""
        return bool(self.bot_token and self.default_chat_id)

    def test_connection(self, bot_token=None, chat_id=None):
        """
        Verify the bot token and attempt a handshake with Telegram servers.
        Returns (success: bool, info: dict)
        """
        token = (bot_token or self.bot_token or "").strip()
        target_chat = (chat_id or self.default_chat_id or "").strip()

        if not token:
            return False, {"error": "Telegram Bot Token is missing. Create one via @BotFather."}

        # Step 1: getMe (verify token validity)
        try:
            url = self.BASE_URL.format(token=token, method="getMe")
            resp = requests.get(url, timeout=self.timeout)
            data = resp.json()

            if not data.get("ok"):
                desc = data.get("description", "Unknown Telegram API error")
                return False, {"error": f"Invalid Bot Token: {desc}"}

            bot_info = data.get("result", {})
            bot_username = bot_info.get("username", "Unknown")
            bot_name = bot_info.get("first_name", "Bot")

            # Step 2: If chat_id provided, send a friendly test message
            if target_chat:
                raw_targets = [t.strip() for t in str(target_chat).split(",") if t.strip()]
                for t_chat in raw_targets:
                    test_text = (
                        "<b>System Diagnostic Ping</b>\n\n"
                        "Telegram alert integration is active and verified.\n"
                        f"<b>Bot:</b> @{html.escape(bot_username)} ({html.escape(bot_name)})\n"
                        f"<b>Chat ID:</b> <code>{html.escape(str(t_chat))}</code>\n"
                        f"<b>Timestamp:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        "Ready to broadcast real-time Wildlife & Elephant warnings."
                    )
                    send_url = self.BASE_URL.format(token=token, method="sendMessage")
                    send_payload = {
                        "chat_id": t_chat,
                        "text": test_text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True
                    }
                    send_resp = requests.post(send_url, json=send_payload, timeout=self.timeout)
                    send_data = send_resp.json()

                    if not send_data.get("ok"):
                        desc = send_data.get("description", "Message send failure")
                        if len(raw_targets) == 1:
                            return False, {
                                "error": f"Bot valid (@{bot_username}), but failed to message Chat ID {t_chat}: {desc}. Did the user start the bot?"
                            }

            return True, {
                "message": f"Verified successfully! Connected as @{bot_username} ({bot_name})",
                "bot_username": bot_username,
                "bot_name": bot_name,
                "chat_id": target_chat or "Not provided (handshake only)"
            }

        except requests.exceptions.Timeout:
            return False, {"error": "Telegram API request timed out after 10s. Check internet connection."}
        except Exception as e:
            return False, {"error": f"Connection error: {str(e)}"}

    @staticmethod
    def _format_multilingual_timestamps(dt_or_str=None):
        if dt_or_str is None:
            dt = datetime.now()
        elif isinstance(dt_or_str, datetime):
            dt = dt_or_str
        elif isinstance(dt_or_str, str):
            dt = None
            for fmt in (
                "%d %B %Y, %I:%M %p",
                "%d %b %Y, %I:%M %p",
                "%d/%m/%Y, %H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S"
            ):
                try:
                    dt = datetime.strptime(dt_or_str.strip(), fmt)
                    break
                except Exception:
                    pass
            if dt is None:
                dt = datetime.now()
        else:
            dt = datetime.now()

        months_kn = {
            1: "ಜನವರಿ", 2: "ಫೆಬ್ರವರಿ", 3: "ಮಾರ್ಚ್", 4: "ಏಪ್ರಿಲ್",
            5: "ಮೇ", 6: "ಜೂನ್", 7: "ಜುಲೈ", 8: "ಆಗಸ್ಟ್",
            9: "ಸೆಪ್ಟೆಂಬರ್", 10: "ಅಕ್ಟೋಬರ್", 11: "ನವೆಂಬರ್", 12: "ಡಿಸೆಂಬರ್"
        }
        months_ta = {
            1: "ஜனவரி", 2: "பிப்ரவரி", 3: "மார்ச்", 4: "ஏப்ரல்",
            5: "மே", 6: "ஜூன்", 7: "ஜூலை", 8: "ஆகஸ்ட்",
            9: "செப்டம்பர்", 10: "அக்டோபர்", 11: "நவம்பர்", 12: "டிசம்பர்"
        }

        day = dt.day
        year = dt.year
        hour_12 = int(dt.strftime("%I"))
        minute = dt.strftime("%M")
        am_pm = dt.strftime("%p")
        hour_24 = dt.hour

        month_en = dt.strftime("%B")
        month_kn = months_kn.get(dt.month, month_en)
        month_ta = months_ta.get(dt.month, month_en)

        if 0 <= hour_24 < 12:
            period_kn = "ಬೆಳಿಗ್ಗೆ"
            period_ta = "காலை"
        elif 12 <= hour_24 < 16:
            period_kn = "ಮಧ್ಯಾಹ್ನ"
            period_ta = "மதியம்"
        elif 16 <= hour_24 < 20:
            period_kn = "ಸಂಜೆ"
            period_ta = "மாலை"
        else:
            period_kn = "ರಾತ್ರಿ"
            period_ta = "இரவு"

        time_en = f"{day} {month_en} {year}, {hour_12}:{minute} {am_pm}"
        time_kn = f"{day} {month_kn} {year}, {period_kn} {hour_12}:{minute}"
        time_ta = f"{day} {month_ta} {year}, {period_ta} {hour_12}:{minute}"

        return time_en, time_kn, time_ta

    @staticmethod
    def _translate_locations(location="Monitoring Zone 1"):
        loc_str = str(location or "Monitoring Zone 1").strip()

        loc_kn = loc_str
        loc_kn = re.sub(r'Monitoring\s*Zone\s*(\d+)', r'ನಿಗಾ ವಲಯ \1', loc_kn, flags=re.I)
        loc_kn = re.sub(r'Zone\s*(\d+)', r'ವಲಯ \1', loc_kn, flags=re.I)
        loc_kn = re.sub(r'Corridor\s*(\d+)', r'ಕಾರಿಡಾರ್ \1', loc_kn, flags=re.I)
        if loc_kn == loc_str and "monitoring" in loc_str.lower():
            loc_kn = "ನಿಗಾ ವಲಯ"

        loc_ta = loc_str
        loc_ta = re.sub(r'Monitoring\s*Zone\s*(\d+)', r'கண்காணிப்பு பகுதி \1', loc_ta, flags=re.I)
        loc_ta = re.sub(r'Zone\s*(\d+)', r'பகுதி \1', loc_ta, flags=re.I)
        loc_ta = re.sub(r'Corridor\s*(\d+)', r'பாதை \1', loc_ta, flags=re.I)
        if loc_ta == loc_str and "monitoring" in loc_str.lower():
            loc_ta = "கண்காணிப்பு பகுதி"

        return loc_str, loc_kn, loc_ta

    @staticmethod
    def build_trilingual_alert(count=3, location="Monitoring Zone 1", dt_or_str=None):
        """
        Builds standardized trilingual (English, Kannada, Tamil) alert using shared builder.
        Preserves exact cross-platform compatibility across WhatsApp and Telegram.
        """
        from trilingual_message_builder import build_trilingual_alert as shared_builder
        return shared_builder(elephant_count=count, location=location, timestamp=dt_or_str)

    @staticmethod
    def build_bilingual_alert(count=1, location="Monitoring Zone 1", timestamp_str=None):
        """Backward-compatible alias pointing to the shared multilingual builder."""
        return TelegramAlertDispatcher.build_trilingual_alert(count=count, location=location, dt_or_str=timestamp_str)

    def _send_single_chat(self, token, single_chat, formatted_text, parse_mode, photo_path):
        """Dispatches payload to a single Telegram chat ID with retries"""
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                if photo_path and os.path.exists(photo_path):
                    url = self.BASE_URL.format(token=token, method="sendPhoto")
                    with open(photo_path, "rb") as photo_file:
                        payload = {
                            "chat_id": single_chat,
                            "caption": formatted_text,
                            "parse_mode": parse_mode
                        }
                        files = {"photo": photo_file}
                        resp = requests.post(url, data=payload, files=files, timeout=self.timeout + 5)
                else:
                    url = self.BASE_URL.format(token=token, method="sendMessage")
                    payload = {
                        "chat_id": single_chat,
                        "text": formatted_text,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": False
                    }
                    resp = requests.post(url, json=payload, timeout=self.timeout)

                data = resp.json()
                if data.get("ok"):
                    msg_id = data.get("result", {}).get("message_id")
                    return True, f"SENT_TO_PROVIDER (Message ID {msg_id} accepted by Telegram API)"

                desc = data.get("description", "Unknown error")
                error_code = data.get("error_code", 0)

                # Do not retry on client errors (4xx) like invalid token, chat not found, bot blocked
                if 400 <= error_code < 500:
                    return False, f"Telegram API Error ({error_code}): {desc}"

            except requests.exceptions.Timeout:
                if attempt == max_attempts:
                    return False, "Telegram API timeout (>10s)"
            except Exception as e:
                if attempt == max_attempts:
                    return False, f"Telegram Dispatch Exception: {str(e)}"

            time.sleep(attempt * 1.0)  # Backoff: 1s, 2s

        return False, "Failed to dispatch to Telegram after retries."

    def send_alert(self, text, chat_id=None, parse_mode="HTML", photo_path=None, severity="CRITICAL", raw=False):
        """
        Sends an alert message to a chat ID, group, or channel (or multiple comma-separated IDs).
        Uses HTML escaping (unless raw=True) and bounded retry with backoff.
        """
        token = self.bot_token
        target_chat = chat_id or self.default_chat_id

        if not token:
            return False, "Telegram Bot Token is not configured."
        if not target_chat:
            return False, "Target Telegram Chat ID is not configured."

        if raw or text.strip().startswith("🚨"):
            formatted_text = str(text)
        else:
            # Severity icons
            icons = {
                "CRITICAL": "🚨 ELEPHANT ALERT",
                "WARNING": "⚠️ EARLY WARNING",
                "INFO": "ℹ️ SYSTEM NOTICE",
                "TEST": "🧪 SYSTEM TEST"
            }
            header = icons.get(severity.upper(), "📢 NOTIFICATION")

            # HTML Escape user-supplied text
            safe_text = html.escape(str(text))
            formatted_text = f"<b>{header}</b>\n\n{safe_text}\n\n<i>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

        raw_targets = target_chat if isinstance(target_chat, (list, tuple)) else str(target_chat).split(",")
        targets = [t.strip() for t in raw_targets if t and str(t).strip()]
        if not targets:
            return False, "Target Telegram Chat ID is not configured."

        if len(targets) == 1:
            return self._send_single_chat(token, targets[0], formatted_text, parse_mode, photo_path)

        results = []
        overall_ok = False
        for single_chat in targets:
            ok, msg = self._send_single_chat(token, single_chat, formatted_text, parse_mode, photo_path)
            results.append(f"{single_chat}: {msg}")
            if ok:
                overall_ok = True

        return overall_ok, "; ".join(results)


# ==============================================================================
# OPTION B: CARRIER EMAIL-TO-SMS DISPATCHER (FREE SMTP GATEWAY ROUTE)
# ==============================================================================
class EmailSmsAlertDispatcher:
    """
    Dispatches direct SMS messages to cell phones by leveraging carrier email-to-SMS
    gateway domains (e.g. 1234567890@vtext.com) through a standard SMTP server
    (such as Gmail with a Google App Password).
    Notice: Relies on carrier email-to-sms gateways in North America.
    """

    def __init__(self, smtp_email=None, smtp_password=None, smtp_server=None, smtp_port=None):
        self.smtp_server = smtp_server or os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(smtp_port or os.getenv("SMTP_PORT", 587))
        self.smtp_email = smtp_email or os.getenv("SMTP_EMAIL", "").strip()
        raw_pass = smtp_password or os.getenv("SMTP_PASSWORD", "")
        self.smtp_password = raw_pass.replace(" ", "").strip()
        self.default_phone = os.getenv("SMS_TARGET_PHONE", "").strip()
        self.default_carrier = os.getenv("SMS_TARGET_CARRIER", "verizon").lower().strip()

    def is_configured(self):
        """Check if minimum required SMTP credentials exist"""
        return bool(self.smtp_email and self.smtp_password)

    @staticmethod
    def sanitize_phone_number(phone_str):
        """
        Strips non-digit characters and normalizes 10-digit number.
        Validates against non-North American country codes.
        """
        if not phone_str:
            return ""
        raw = str(phone_str).strip()
        digits = re.sub(r"\D", "", raw)

        # Check for Indian country code (+91)
        if raw.startswith("+91") or (len(digits) == 12 and digits.startswith("91")):
            return "INDIAN_NUMBER_NOT_SUPPORTED"

        # If 11 digits and starts with 1 (US/Canada country code), strip leading 1
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]

        return digits

    def get_gateway_address(self, phone_number, carrier_key="verizon", custom_domain=None):
        """
        Constructs destination email address for the carrier SMS gateway.
        """
        clean_phone = self.sanitize_phone_number(phone_number)
        if clean_phone == "INDIAN_NUMBER_NOT_SUPPORTED":
            return None, (
                "Indian mobile numbers (+91) do not support North American carrier email-to-sms gateways "
                "(discontinued by TRAI regulations). Please use Option A (Telegram Bot API) which works reliably in India."
            )
        if not clean_phone or len(clean_phone) != 10:
            return None, "Invalid phone number: Must be a 10-digit mobile number."

        if carrier_key == "custom":
            if not custom_domain:
                return None, "Custom carrier selected but domain was left empty."
            clean_domain = custom_domain.strip().lstrip("@")
            return f"{clean_phone}@{clean_domain}", None

        carrier_info = CARRIER_GATEWAYS.get(carrier_key.lower())
        if not carrier_info:
            return None, f"Unknown carrier '{carrier_key}'. Choose from: {', '.join(CARRIER_GATEWAYS.keys())}"

        sms_domain = carrier_info.get("sms") or carrier_info.get("mms")
        if not sms_domain:
            return None, f"No gateway domain available for {carrier_info.get('name')}"

        return f"{clean_phone}@{sms_domain}", None

    def test_connection(self, smtp_email=None, smtp_password=None, test_phone=None, test_carrier=None):
        """
        Tests SMTP handshake and authentication against the SMTP server.
        """
        user = (smtp_email or self.smtp_email or "").strip()
        raw_pass = smtp_password or self.smtp_password or ""
        pwd = raw_pass.replace(" ", "").strip()

        if not user:
            return False, {"error": "SMTP Sender Email is missing."}
        if not pwd:
            return False, {"error": "SMTP App Password is missing. For Gmail, generate a 16-character App Password."}

        try:
            context = ssl.create_default_context()
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=12)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(user, pwd)

            test_dispatched = False
            target_addr = None

            if test_phone and test_carrier:
                target_addr, err = self.get_gateway_address(test_phone, test_carrier)
                if err:
                    server.quit()
                    return False, {"error": err}

                msg = MIMEText("TEST ALERT: Elephant Early Warning SMS Gateway active! Time: " + datetime.now().strftime("%H:%M:%S"))
                msg["Subject"] = "TEST"
                msg["From"] = user
                msg["To"] = target_addr

                server.sendmail(user, target_addr, msg.as_string())
                test_dispatched = True

            server.quit()

            info = {
                "message": f"SMTP Authentication Succeeded ({self.smtp_server}:{self.smtp_port})",
                "smtp_user": user
            }
            if test_dispatched:
                info["test_sms_target"] = target_addr
                info["details"] = f"Test message relayed to SMTP server for {target_addr} via {test_carrier.upper()} gateway."

            return True, info

        except smtplib.SMTPAuthenticationError as auth_err:
            return False, {
                "error": f"Authentication Failed (Code {auth_err.smtp_code}). For Gmail, use an 'App Password' (16 chars), not your main account password."
            }
        except Exception as e:
            return False, {"error": f"SMTP Handshake Error: {str(e)}"}

    def send_sms(self, phone_number, carrier_key, message, subject="ELEPHANT ALERT", custom_domain=None):
        """
        Sends an SMS via the carrier email gateway.
        Keeps text concise (< 160 characters) to prevent multi-part SMS fragmentation.
        """
        user = self.smtp_email
        pwd = self.smtp_password

        if not user or not pwd:
            return False, "SMTP credentials not configured. Provide Gmail SMTP App Password."

        dest_email, err = self.get_gateway_address(phone_number, carrier_key, custom_domain)
        if err:
            return False, err

        try:
            clean_message = message.strip()[:155]
            msg = MIMEText(clean_message)
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = dest_email

            context = ssl.create_default_context()
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=12)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(user, pwd)
            server.sendmail(user, dest_email, msg.as_string())
            server.quit()

            return True, f"RELAYED_TO_SMTP_GATEWAY (Accepted by SMTP server for {carrier_key.upper()} gateway: {dest_email})"

        except smtplib.SMTPAuthenticationError:
            return False, "SMTP Auth Failed. Please verify your Gmail 16-character App Password."
        except Exception as e:
            return False, f"SMTP Send Exception: {str(e)}"


# ==============================================================================
# UNIFIED FREE ALERT MANAGER (COORDINATOR & PERSISTENT HISTORY RECORDER)
# ==============================================================================
class FreeAlertManager:
    """
    Central Manager coordinating:
    - Option A: Telegram Bot Dispatch
    - Option B: Carrier Email-to-SMS Dispatch
    - Dual Broadcast Mode
    - Persistent circular buffer of recent alert transmissions for live dashboard inspection
    - Persistent configuration storage in free_alert_config.json and free_alert_history.json
    """

    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "free_alert_config.json")
    HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "free_alert_history.json")

    def __init__(self):
        self.lock = threading.Lock()
        self.config = self._load_config()
        self.history = self._load_history()

        self.telegram = TelegramAlertDispatcher(
            bot_token=self.config.get("telegram_bot_token"),
            default_chat_id=self.config.get("telegram_chat_id")
        )
        self.email_sms = EmailSmsAlertDispatcher(
            smtp_email=self.config.get("smtp_email"),
            smtp_password=self.config.get("smtp_password"),
            smtp_server=self.config.get("smtp_server", "smtp.gmail.com"),
            smtp_port=self.config.get("smtp_port", 587)
        )

    def _load_config(self):
        """Loads configuration from JSON file with environment variable fallbacks"""
        defaults = {
            "telegram_enabled": True,
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            "email_sms_enabled": True,
            "smtp_email": os.getenv("SMTP_EMAIL", "").strip(),
            "smtp_password": os.getenv("SMTP_PASSWORD", "").strip(),
            "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com").strip(),
            "smtp_port": int(os.getenv("SMTP_PORT", 587)),
            "default_phone": os.getenv("SMS_TARGET_PHONE", "").strip(),
            "default_carrier": os.getenv("SMS_TARGET_CARRIER", "verizon").strip(),
            "broadcast_channel": "both"
        }

        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    # Filter out dummy/test values that may have leaked from test suites
                    if "FAKE" in str(saved.get("telegram_bot_token", "")) or "test" in str(saved.get("telegram_bot_token", "")).lower():
                        saved.pop("telegram_bot_token", None)
                    if str(saved.get("telegram_chat_id", "")).strip() in ("98765432", "12345678"):
                        saved.pop("telegram_chat_id", None)

                    # Ensure empty saved tokens don't override configured environment variables
                    if not saved.get("telegram_bot_token") and defaults["telegram_bot_token"]:
                        saved["telegram_bot_token"] = defaults["telegram_bot_token"]
                    if not saved.get("telegram_chat_id") and defaults["telegram_chat_id"]:
                        saved["telegram_chat_id"] = defaults["telegram_chat_id"]

                    defaults.update(saved)
            except Exception as e:
                print(f"[FREE_ALERT] Note: Failed to read {self.CONFIG_FILE}: {e}")

        return defaults

    def _load_history(self):
        """Loads recent alert history from JSON file"""
        if os.path.exists(self.HISTORY_FILE):
            try:
                with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[-50:]
            except Exception:
                pass
        return []

    def save_config(self, new_settings):
        """Persists updated configuration to JSON and refreshes runtime dispatchers"""
        with self.lock:
            for k, v in new_settings.items():
                if k == "smtp_password" and v and ("••••" in str(v) or "..." in str(v)):
                    continue
                if k == "telegram_bot_token" and v and ("••••" in str(v) or "..." in str(v)):
                    continue
                self.config[k] = v

            # Prevent writing fake test tokens or test execution from trashing disk config
            is_test_env = any(mod in sys.modules for mod in ("unittest", "pytest")) or os.getenv("TESTING") == "true"
            contains_fake = "FAKE" in str(self.config.get("telegram_bot_token", "")) or str(self.config.get("telegram_chat_id", "")).strip() in ("98765432", "12345678")

            if not (is_test_env or contains_fake):
                try:
                    with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                        json.dump(self.config, f, indent=2)
                except Exception as e:
                    print(f"[FREE_ALERT] Error saving {self.CONFIG_FILE}: {e}")

            self.telegram = TelegramAlertDispatcher(
                bot_token=self.config.get("telegram_bot_token"),
                default_chat_id=self.config.get("telegram_chat_id")
            )
            self.email_sms = EmailSmsAlertDispatcher(
                smtp_email=self.config.get("smtp_email"),
                smtp_password=self.config.get("smtp_password"),
                smtp_server=self.config.get("smtp_server", "smtp.gmail.com"),
                smtp_port=self.config.get("smtp_port", 587)
            )

        return True, "Configuration successfully saved."

    def reload_config(self):
        """Reloads configuration from JSON file / environment and updates dispatchers"""
        with self.lock:
            self.config = self._load_config()
            self.telegram = TelegramAlertDispatcher(
                bot_token=self.config.get("telegram_bot_token"),
                default_chat_id=self.config.get("telegram_chat_id")
            )
            self.email_sms = EmailSmsAlertDispatcher(
                smtp_email=self.config.get("smtp_email"),
                smtp_password=self.config.get("smtp_password"),
                smtp_server=self.config.get("smtp_server", "smtp.gmail.com"),
                smtp_port=self.config.get("smtp_port", 587)
            )
        return self.config

    def get_safe_config(self):
        """Returns configuration with sensitive tokens masked for dashboard display"""
        safe = dict(self.config)
        tok = safe.get("telegram_bot_token", "")
        if tok and len(tok) > 8:
            safe["telegram_bot_token"] = tok[:4] + "••••••••" + tok[-4:]

        pwd = safe.get("smtp_password", "")
        if pwd:
            safe["smtp_password"] = "••••••••••••••••"

        safe["supported_carriers"] = CARRIER_GATEWAYS
        return safe

    def _record_history(self, record):
        """Appends an event to the persistent history buffer"""
        with self.lock:
            self.history.append(record)
            if len(self.history) > 50:
                self.history.pop(0)

            try:
                with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.history, f, indent=2)
            except Exception:
                pass

    def get_history(self):
        """Returns recent alert logs sorted newest first"""
        with self.lock:
            return list(reversed(self.history))

    def dispatch_alert(self, channel="both", message="", severity="CRITICAL",
                       telegram_chat_id=None, phone_number=None, carrier_key=None,
                       photo_path=None, custom_carrier_domain=None):
        """
        Unified dispatch method.
        channel: 'telegram' (Option A), 'email_sms' (Option B), or 'both' (Dual Broadcast)
        """
        start_time = time.time()
        results = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "severity": severity,
            "channel_requested": channel,
            "message": message,
            "telegram": None,
            "email_sms": None,
            "overall_status": "PENDING"
        }

        run_telegram = channel in ("telegram", "both")
        run_sms = channel in ("email_sms", "both")

        success_count = 0
        total_attempted = 0

        # Option A: Telegram Bot
        if run_telegram:
            total_attempted += 1
            chat = telegram_chat_id or self.config.get("telegram_chat_id")
            ok, info = self.telegram.send_alert(
                text=message,
                chat_id=chat,
                photo_path=photo_path,
                severity=severity
            )
            results["telegram"] = {
                "success": ok,
                "status": "SENT_TO_PROVIDER" if ok else "FAILED",
                "target": str(chat or "default"),
                "details": info
            }
            if ok:
                success_count += 1

        # Option B: Carrier Email-to-SMS
        if run_sms:
            total_attempted += 1
            phone = phone_number or self.config.get("default_phone")
            carrier = (carrier_key or self.config.get("default_carrier", "verizon")).lower()
            subject = f"[{severity.upper()}] ELEPHANT ALERT"

            sms_text = f"ALERT ({severity}): {message}"
            if len(sms_text) > 155:
                sms_text = sms_text[:152] + "..."

            ok, info = self.email_sms.send_sms(
                phone_number=phone,
                carrier_key=carrier,
                message=sms_text,
                subject=subject,
                custom_domain=custom_carrier_domain
            )
            results["email_sms"] = {
                "success": ok,
                "status": "RELAYED_TO_SMTP_GATEWAY" if ok else "FAILED",
                "target": f"{phone} ({carrier.upper()})",
                "details": info
            }
            if ok:
                success_count += 1

        duration_ms = round((time.time() - start_time) * 1000)
        results["duration_ms"] = duration_ms

        if success_count == total_attempted and total_attempted > 0:
            results["overall_status"] = "SENT_TO_PROVIDERS"
        elif success_count > 0:
            results["overall_status"] = "PARTIAL"
        else:
            results["overall_status"] = "FAILED"

        self._record_history(results)
        return results

    def dispatch_async(self, **kwargs):
        """Fires dispatch in a daemon thread so caller does not block"""
        thread = threading.Thread(target=self.dispatch_alert, kwargs=kwargs, daemon=True)
        thread.start()
        return True

    def trigger_elephant_detection_event(self, location="Boundary Corridor Node 1",
                                         confidence=0.88, trigger_source="AI Acoustic + Camera",
                                         photo_path=None, elephant_count=1):
        """
        Helper for automated edge detection integration.
        Formats an emergency alert and dispatches to configured free channels.
        """
        msg = TelegramAlertDispatcher.build_trilingual_alert(
            count=elephant_count,
            location=location,
            dt_or_str=datetime.now()
        )
        pref_channel = "telegram"
        return self.dispatch_async(
            channel=pref_channel,
            message=msg,
            severity="CRITICAL",
            photo_path=photo_path
        )

    def dispatch_multichannel_alert(self, count=1, confidence=0.85, image_path=None,
                                    location_name="Monitoring Zone 1", device_id="CAMERA-01"):
        """
        Dispatches multi-channel trilingual alert across Telegram and configured free channels.
        Backward-compatible alias for camera stream detections.
        """
        return self.trigger_elephant_detection_event(
            location=location_name,
            confidence=confidence,
            trigger_source=f"Optical AI Detection ({device_id})",
            photo_path=image_path,
            elephant_count=count
        )

    # ==========================================================================
    # REAL DELIVERY VERIFICATION ENGINE
    # ==========================================================================
    STATUS_CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    STATUS_SEND_FAILED = "SEND_FAILED"
    STATUS_ACCEPTED_BY_PROVIDER = "ACCEPTED_BY_PROVIDER"
    STATUS_DELIVERY_CONFIRMED = "DELIVERY_CONFIRMED"
    STATUS_AWAITING_RECIPIENT_CONFIRMATION = "AWAITING_RECIPIENT_CONFIRMATION"

    TEST_ALERT_MESSAGE = "TEST ALERT: Human-Elephant Detection System message delivery verification."

    @staticmethod
    def mask_recipient(method, recipient, carrier=None):
        """Masks recipient phone number or Telegram chat ID for privacy & security."""
        if not recipient:
            return "Not configured"
        s = str(recipient).strip()
        carrier_label = f" ({carrier.upper()})" if carrier else ""
        if method == "telegram":
            if s.startswith("@"):
                return s[:4] + "****" if len(s) > 4 else "@***"
            elif s.startswith("-100"):
                return s[:6] + "****" + s[-2:] if len(s) > 8 else s[:4] + "****"
            elif s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                if len(s) > 5:
                    return s[:3] + "••••" + s[-2:]
                return s[:2] + "••••" if len(s) > 2 else "••••"
            return s[:3] + "••••" if len(s) > 3 else "••••"
        elif method in ("email_sms", "gsm_sim"):
            digits = re.sub(r"\D", "", s)
            if len(digits) >= 10:
                last4 = digits[-4:]
                first2 = digits[:2] if len(digits) > 10 else ""
                return f"+{first2} ***-***-{last4}{carrier_label}" if first2 else f"***-***-{last4}{carrier_label}"
            elif len(digits) > 4:
                return f"***-***-{digits[-4:]}{carrier_label}"
            return f"***{carrier_label}"
        return "••••"

    @staticmethod
    def mask_sender(method, identifier=None):
        """Masks sender credentials for display and logs without leaking secrets."""
        if not identifier:
            return "Not configured"
        s = str(identifier).strip()
        if method == "email_sms":
            if "@" in s:
                user_part, domain = s.split("@", 1)
                masked_user = user_part[:2] + "***" if len(user_part) > 2 else user_part[:1] + "***"
                return f"{masked_user}@{domain}"
            return s[:2] + "***"
        elif method == "telegram":
            if s.startswith("Bot:"):
                return s
            if ":" in s:
                bot_id = s.split(":", 1)[0]
                return f"Bot Token ID: {bot_id} (••••••••)"
            return "Bot: Configured"
        elif method == "gsm_sim":
            return "None (GSM/SIM Hardware Not Detected)"
        return "Configured"

    def validate_configuration(self, method, recipient=None, carrier_key=None, custom_domain=None):
        """
        Validates sender credentials, recipient format, and performs live authentication
        handshakes with official provider APIs before authorizing a test message.
        """
        method = (method or "telegram").strip().lower()

        # Method: GSM / SIM Hardware SMS
        if method == "gsm_sim":
            return {
                "status": self.STATUS_CONFIGURATION_INVALID,
                "method": "gsm_sim",
                "can_send": False,
                "masked_sender": "None (GSM/SIM Hardware Not Detected)",
                "masked_recipient": self.mask_recipient("gsm_sim", recipient),
                "error": "GSM/SIM hardware modem is not detected or supported in this codebase. Cellular SMS via SIM card requires a physical GSM modem (e.g., SIM800L / Quectel module) and serial AT command interface.",
                "details": "No GSM modem hardware driver or serial AT interface is present in this system."
            }

        # Method: Telegram Bot API
        if method == "telegram":
            cfg_token = self.config.get("telegram_bot_token")
            bot_token = (cfg_token if cfg_token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
            cfg_chat = self.config.get("telegram_chat_id")
            target_chat = (recipient if recipient is not None else (cfg_chat if cfg_chat is not None else os.getenv("TELEGRAM_CHAT_ID", ""))).strip()

            if not bot_token:
                return {
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "method": "telegram",
                    "can_send": False,
                    "masked_sender": "Not configured",
                    "masked_recipient": self.mask_recipient("telegram", target_chat),
                    "error": "Telegram Bot Token is not configured. Create a bot with @BotFather and configure TELEGRAM_BOT_TOKEN.",
                    "details": "Missing sender credentials: TELEGRAM_BOT_TOKEN"
                }

            if not target_chat:
                return {
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "method": "telegram",
                    "can_send": False,
                    "masked_sender": self.mask_sender("telegram", bot_token),
                    "masked_recipient": "Not provided",
                    "error": "Recipient Telegram Chat ID is required. Enter your numeric chat ID (e.g., from @userinfobot) or @channel.",
                    "details": "Missing recipient identifier"
                }

            # Verify Bot Authentication with official Telegram getMe API
            try:
                url = f"https://api.telegram.org/bot{bot_token}/getMe"
                resp = requests.get(url, timeout=8)
                data = resp.json()
                if not data.get("ok"):
                    desc = data.get("description", "Invalid bot token")
                    return {
                        "status": self.STATUS_CONFIGURATION_INVALID,
                        "method": "telegram",
                        "can_send": False,
                        "masked_sender": self.mask_sender("telegram", bot_token),
                        "masked_recipient": self.mask_recipient("telegram", target_chat),
                        "error": f"Telegram Bot Authentication Failed: {desc}",
                        "details": "Provider rejected bot credentials."
                    }

                bot_info = data.get("result", {})
                bot_user = bot_info.get("username", "UnknownBot")
                bot_name = bot_info.get("first_name", "Bot")
                masked_sender = f"Bot: @{bot_user} ({bot_name})"

                return {
                    "status": "READY",
                    "method": "telegram",
                    "can_send": True,
                    "masked_sender": masked_sender,
                    "masked_recipient": self.mask_recipient("telegram", target_chat),
                    "bot_username": bot_user,
                    "details": f"Telegram Bot authenticated successfully (@{bot_user}). Ready to dispatch real test alert."
                }
            except requests.exceptions.Timeout:
                return {
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "method": "telegram",
                    "can_send": False,
                    "masked_sender": self.mask_sender("telegram", bot_token),
                    "masked_recipient": self.mask_recipient("telegram", target_chat),
                    "error": "Telegram API request timed out (>8s). Check internet connectivity.",
                    "details": "Network timeout contacting api.telegram.org"
                }
            except Exception as e:
                return {
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "method": "telegram",
                    "can_send": False,
                    "masked_sender": self.mask_sender("telegram", bot_token),
                    "masked_recipient": self.mask_recipient("telegram", target_chat),
                    "error": f"Telegram Bot verification exception: {str(e)}",
                    "details": str(e)
                }

        # Method: Carrier Email-to-SMS via Free SMTP
        if method == "email_sms":
            smtp_email = (self.config.get("smtp_email") or os.getenv("SMTP_EMAIL", "")).strip()
            raw_pass = self.config.get("smtp_password") or os.getenv("SMTP_PASSWORD", "")
            smtp_pass = raw_pass.replace(" ", "").strip()
            target_phone = (recipient or self.config.get("default_phone", "")).strip()
            carrier = (carrier_key or self.config.get("default_carrier", "verizon")).strip().lower()

            if not smtp_email or not smtp_pass:
                return {
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "method": "email_sms",
                    "can_send": False,
                    "masked_sender": self.mask_sender("email_sms", smtp_email),
                    "masked_recipient": self.mask_recipient("email_sms", target_phone, carrier),
                    "error": "SMTP credentials not configured. Configure sender email and 16-character Google App Password.",
                    "details": "Missing SMTP sender credentials"
                }

            dest_addr, err = self.email_sms.get_gateway_address(target_phone, carrier, custom_domain)
            if err:
                return {
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "method": "email_sms",
                    "can_send": False,
                    "masked_sender": self.mask_sender("email_sms", smtp_email),
                    "masked_recipient": self.mask_recipient("email_sms", target_phone, carrier),
                    "error": err,
                    "details": "Recipient phone or carrier validation error"
                }

            # Verify SMTP Handshake & Login
            try:
                context = ssl.create_default_context()
                server = smtplib.SMTP(self.email_sms.smtp_server, self.email_sms.smtp_port, timeout=10)
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(smtp_email, smtp_pass)
                server.quit()
                return {
                    "status": "READY",
                    "method": "email_sms",
                    "can_send": True,
                    "masked_sender": self.mask_sender("email_sms", smtp_email),
                    "masked_recipient": self.mask_recipient("email_sms", target_phone, carrier),
                    "gateway_address": dest_addr,
                    "details": f"SMTP handshake and authentication succeeded ({self.email_sms.smtp_server}:{self.email_sms.smtp_port}). Ready to relay to {dest_addr}."
                }
            except smtplib.SMTPAuthenticationError as auth_err:
                return {
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "method": "email_sms",
                    "can_send": False,
                    "masked_sender": self.mask_sender("email_sms", smtp_email),
                    "masked_recipient": self.mask_recipient("email_sms", target_phone, carrier),
                    "error": f"SMTP Authentication Rejected (Code {auth_err.smtp_code}). For Gmail, ensure you are using a 16-character Google App Password (not your primary account password).",
                    "details": "Provider rejected SMTP credentials."
                }
            except Exception as e:
                return {
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "method": "email_sms",
                    "can_send": False,
                    "masked_sender": self.mask_sender("email_sms", smtp_email),
                    "masked_recipient": self.mask_recipient("email_sms", target_phone, carrier),
                    "error": f"SMTP Connection / Handshake error: {str(e)}",
                    "details": str(e)
                }

        return {
            "status": self.STATUS_CONFIGURATION_INVALID,
            "method": method,
            "can_send": False,
            "masked_sender": "Unknown",
            "masked_recipient": "Unknown",
            "error": f"Unsupported messaging method '{method}'. Supported methods: 'telegram', 'email_sms', 'gsm_sim'.",
            "details": "Unsupported method identifier"
        }

    def send_real_test_message(self, method, recipient=None, carrier_key=None, custom_domain=None, confirmed=False):
        """
        Sends exactly ONE real test message using local credentials after explicit confirmation.
        Returns one of 5 standardized delivery verification statuses:
        - CONFIGURATION_INVALID
        - SEND_FAILED
        - ACCEPTED_BY_PROVIDER
        - DELIVERY_CONFIRMED
        - AWAITING_RECIPIENT_CONFIRMATION
        """
        method = (method or "telegram").strip().lower()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        event_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"

        # Step 4: Strict explicit authorization check
        if not confirmed:
            return {
                "event_id": event_id,
                "timestamp": timestamp,
                "method": method,
                "status": self.STATUS_CONFIGURATION_INVALID,
                "error": "Explicit confirmation required. Real test messages cannot be dispatched without explicit authorization.",
                "details": "Dispatch aborted: confirmed=False"
            }

        # Method: GSM / SIM Hardware SMS (Unsupported)
        if method == "gsm_sim":
            record = {
                "event_id": event_id,
                "timestamp": timestamp,
                "type": "REAL_DELIVERY_TEST",
                "method": "gsm_sim",
                "masked_sender": "None (GSM/SIM Hardware Not Detected)",
                "masked_recipient": self.mask_recipient("gsm_sim", recipient),
                "message": self.TEST_ALERT_MESSAGE,
                "status": self.STATUS_CONFIGURATION_INVALID,
                "details": "GSM/SIM hardware modem is not detected or supported in this codebase. Cellular SMS via SIM card requires a physical GSM modem (e.g., SIM800L / Quectel module) and serial AT command interface.",
                "raw_response": {"error": "GSM/SIM hardware modem not found"},
                "confirmed_at": None
            }
            self._record_history(record)
            return record

        # Method: Telegram Bot API (Option A)
        if method == "telegram":
            cfg_token = self.config.get("telegram_bot_token")
            bot_token = (cfg_token if cfg_token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
            cfg_chat = self.config.get("telegram_chat_id")
            target_chat = (recipient if recipient is not None else (cfg_chat if cfg_chat is not None else os.getenv("TELEGRAM_CHAT_ID", ""))).strip()
            masked_sender = self.mask_sender("telegram", bot_token)
            masked_recipient = self.mask_recipient("telegram", target_chat)

            if not bot_token or not target_chat:
                record = {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "type": "REAL_DELIVERY_TEST",
                    "method": "telegram",
                    "masked_sender": masked_sender,
                    "masked_recipient": masked_recipient,
                    "message": self.TEST_ALERT_MESSAGE,
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "details": "Missing required Telegram credentials or recipient chat ID.",
                    "raw_response": {"error": "Missing credentials"},
                    "confirmed_at": None
                }
                self._record_history(record)
                return record

            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": target_chat,
                    "text": self.TEST_ALERT_MESSAGE,
                    "disable_web_page_preview": True
                }
                resp = requests.post(url, json=payload, timeout=10)
                data = resp.json()

                if not data.get("ok"):
                    desc = data.get("description", "Unknown Telegram error")
                    code = data.get("error_code", 400)
                    record = {
                        "event_id": event_id,
                        "timestamp": timestamp,
                        "type": "REAL_DELIVERY_TEST",
                        "method": "telegram",
                        "masked_sender": masked_sender,
                        "masked_recipient": masked_recipient,
                        "message": self.TEST_ALERT_MESSAGE,
                        "status": self.STATUS_SEND_FAILED,
                        "details": f"Telegram API rejected dispatch (Code {code}): {desc}. Ensure recipient has clicked /start on the bot.",
                        "raw_response": {"error_code": code, "description": desc},
                        "confirmed_at": None
                    }
                    self._record_history(record)
                    return record

                result_info = data.get("result", {})
                msg_id = result_info.get("message_id")
                chat_info = result_info.get("chat", {})

                # Telegram accepted the message into its delivery queue
                record = {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "type": "REAL_DELIVERY_TEST",
                    "method": "telegram",
                    "masked_sender": masked_sender,
                    "masked_recipient": masked_recipient,
                    "message": self.TEST_ALERT_MESSAGE,
                    "status": self.STATUS_AWAITING_RECIPIENT_CONFIRMATION,
                    "details": f"Telegram Bot API accepted message (Message ID {msg_id}). Awaiting recipient confirmation of handset arrival.",
                    "raw_response": {
                        "ok": True,
                        "message_id": msg_id,
                        "chat_type": chat_info.get("type"),
                        "date": result_info.get("date")
                    },
                    "confirmed_at": None
                }
                self._record_history(record)
                return record

            except requests.exceptions.Timeout:
                record = {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "type": "REAL_DELIVERY_TEST",
                    "method": "telegram",
                    "masked_sender": masked_sender,
                    "masked_recipient": masked_recipient,
                    "message": self.TEST_ALERT_MESSAGE,
                    "status": self.STATUS_SEND_FAILED,
                    "details": "Telegram API request timed out (>10s).",
                    "raw_response": {"error": "Timeout"},
                    "confirmed_at": None
                }
                self._record_history(record)
                return record
            except Exception as e:
                record = {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "type": "REAL_DELIVERY_TEST",
                    "method": "telegram",
                    "masked_sender": masked_sender,
                    "masked_recipient": masked_recipient,
                    "message": self.TEST_ALERT_MESSAGE,
                    "status": self.STATUS_SEND_FAILED,
                    "details": f"Telegram dispatch exception: {str(e)}",
                    "raw_response": {"error": str(e)},
                    "confirmed_at": None
                }
                self._record_history(record)
                return record

        # Method: Carrier Email-to-SMS via Free SMTP (Option B)
        if method == "email_sms":
            smtp_email = (self.config.get("smtp_email") or os.getenv("SMTP_EMAIL", "")).strip()
            raw_pass = self.config.get("smtp_password") or os.getenv("SMTP_PASSWORD", "")
            smtp_pass = raw_pass.replace(" ", "").strip()
            target_phone = (recipient or self.config.get("default_phone", "")).strip()
            carrier = (carrier_key or self.config.get("default_carrier", "verizon")).strip().lower()

            masked_sender = self.mask_sender("email_sms", smtp_email)
            masked_recipient = self.mask_recipient("email_sms", target_phone, carrier)

            if not smtp_email or not smtp_pass:
                record = {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "type": "REAL_DELIVERY_TEST",
                    "method": "email_sms",
                    "masked_sender": masked_sender,
                    "masked_recipient": masked_recipient,
                    "message": self.TEST_ALERT_MESSAGE,
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "details": "SMTP credentials not configured. Configure sender email and 16-character Google App Password.",
                    "raw_response": {"error": "Missing SMTP credentials"},
                    "confirmed_at": None
                }
                self._record_history(record)
                return record

            dest_email, err = self.email_sms.get_gateway_address(target_phone, carrier, custom_domain)
            if err:
                record = {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "type": "REAL_DELIVERY_TEST",
                    "method": "email_sms",
                    "masked_sender": masked_sender,
                    "masked_recipient": masked_recipient,
                    "message": self.TEST_ALERT_MESSAGE,
                    "status": self.STATUS_CONFIGURATION_INVALID,
                    "details": err,
                    "raw_response": {"error": err},
                    "confirmed_at": None
                }
                self._record_history(record)
                return record

            try:
                msg = MIMEText(self.TEST_ALERT_MESSAGE)
                msg["Subject"] = "TEST ALERT"
                msg["From"] = smtp_email
                msg["To"] = dest_email

                context = ssl.create_default_context()
                server = smtplib.SMTP(self.email_sms.smtp_server, self.email_sms.smtp_port, timeout=12)
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(smtp_email, smtp_pass)
                rejected_recipients = server.sendmail(smtp_email, dest_email, msg.as_string())
                server.quit()

                if rejected_recipients:
                    record = {
                        "event_id": event_id,
                        "timestamp": timestamp,
                        "type": "REAL_DELIVERY_TEST",
                        "method": "email_sms",
                        "masked_sender": masked_sender,
                        "masked_recipient": masked_recipient,
                        "message": self.TEST_ALERT_MESSAGE,
                        "status": self.STATUS_SEND_FAILED,
                        "details": f"SMTP server rejected destination address: {rejected_recipients}",
                        "raw_response": {"rejected": str(rejected_recipients)},
                        "confirmed_at": None
                    }
                    self._record_history(record)
                    return record

                record = {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "type": "REAL_DELIVERY_TEST",
                    "method": "email_sms",
                    "masked_sender": masked_sender,
                    "masked_recipient": masked_recipient,
                    "message": self.TEST_ALERT_MESSAGE,
                    "status": self.STATUS_ACCEPTED_BY_PROVIDER,
                    "details": f"SMTP mail server accepted message for carrier gateway relay ({dest_email}). Cellular handset delivery unconfirmed without carrier SMS DLR.",
                    "raw_response": {
                        "accepted": True,
                        "smtp_server": self.email_sms.smtp_server,
                        "gateway": dest_email,
                        "status_code": 250
                    },
                    "confirmed_at": None
                }
                self._record_history(record)
                return record

            except smtplib.SMTPAuthenticationError as auth_err:
                record = {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "type": "REAL_DELIVERY_TEST",
                    "method": "email_sms",
                    "masked_sender": masked_sender,
                    "masked_recipient": masked_recipient,
                    "message": self.TEST_ALERT_MESSAGE,
                    "status": self.STATUS_SEND_FAILED,
                    "details": f"SMTP Authentication Rejected (Code {auth_err.smtp_code}). Verify 16-character Google App Password.",
                    "raw_response": {"error_code": auth_err.smtp_code, "error": str(auth_err.smtp_error)},
                    "confirmed_at": None
                }
                self._record_history(record)
                return record
            except Exception as e:
                record = {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "type": "REAL_DELIVERY_TEST",
                    "method": "email_sms",
                    "masked_sender": masked_sender,
                    "masked_recipient": masked_recipient,
                    "message": self.TEST_ALERT_MESSAGE,
                    "status": self.STATUS_SEND_FAILED,
                    "details": f"SMTP relay exception: {str(e)}",
                    "raw_response": {"error": str(e)},
                    "confirmed_at": None
                }
                self._record_history(record)
                return record

        return {
            "event_id": event_id,
            "timestamp": timestamp,
            "method": method,
            "status": self.STATUS_CONFIGURATION_INVALID,
            "error": f"Unknown method: {method}",
            "details": "Unsupported method identifier"
        }

    def confirm_receipt(self, event_id):
        """
        Manually confirms that the recipient has seen/received the test message on their device,
        transitioning the delivery verification status to DELIVERY_CONFIRMED.
        """
        if not event_id:
            return False, {"error": "Missing event_id parameter."}

        with self.lock:
            found = None
            for item in self.history:
                if item.get("event_id") == event_id:
                    item["status"] = self.STATUS_DELIVERY_CONFIRMED
                    item["confirmed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    item["details"] += " [Handset receipt confirmed by recipient]"
                    found = dict(item)
                    break

            if found:
                try:
                    with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
                        json.dump(self.history, f, indent=2)
                except Exception as e:
                    print(f"[FREE_ALERT] Note: Failed to persist receipt update: {e}")
                return True, found

            return False, {"error": f"Verification event '{event_id}' not found in history."}

    def get_real_test_history(self):
        """Returns delivery verification test events sorted newest first."""
        with self.lock:
            return [
                dict(item) for item in reversed(self.history)
                if item.get("type") == "REAL_DELIVERY_TEST"
            ]


# ==============================================================================
# GLOBAL SINGLETON GETTER
# ==============================================================================
_GLOBAL_FREE_ALERT_MANAGER = None

def get_free_alert_manager():
    """Returns the singleton instance of FreeAlertManager"""
    global _GLOBAL_FREE_ALERT_MANAGER
    if _GLOBAL_FREE_ALERT_MANAGER is None:
        _GLOBAL_FREE_ALERT_MANAGER = FreeAlertManager()
    return _GLOBAL_FREE_ALERT_MANAGER
# Backward compatibility alias
FreeAlertService = FreeAlertManager

if __name__ == "__main__":
    mgr = get_free_alert_manager()
    print("FreeAlertManager ready. Config status:")
    print(json.dumps(mgr.get_safe_config(), indent=2))
