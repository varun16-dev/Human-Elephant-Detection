"""
Automated Unit and Integration Tests for WhatsApp (PyWhatKit) & Telegram Alert Integration
Department of AI & ML, Sri Sairam College of Engineering

Covers all 16 required test cases from Section 10:
1. Message contains all three languages (English, Kannada, Tamil).
2. Language order is strictly English -> Kannada -> Tamil.
3. Actual elephant count is correctly inserted (both singular and plural).
4. Monitoring location is correctly inserted and translated.
5. Timestamp is formatted correctly using local timezone.
6. Unicode Kannada and Tamil text is strictly preserved.
7. WhatsApp and Telegram receive identical message content.
8. WhatsApp-disabled mode does not invoke PyWhatKit.
9. Telegram-disabled mode does not send Telegram messages.
10. A WhatsApp exception does not crash the detection pipeline.
11. A Telegram failure does not prevent an independent WhatsApp attempt.
12. Duplicate detections within cooldown period do not trigger alerts.
13. A new detection event can generate an alert after the cooldown.
14. Missing / invalid recipient numbers are handled safely.
15. Browser failures produce an informative error without false delivery claims.
16. Status distinctions: QUEUED, SENDING, ATTEMPT_COMPLETED, FAILED.
"""

import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trilingual_message_builder import (
    build_trilingual_alert,
    format_multilingual_timestamps,
    translate_locations,
    DIVIDER
)
from whatsapp_pywhatkit_service import (
    WhatsAppPyWhatKitService,
    normalize_phone_number,
    mask_phone_number,
    get_whatsapp_service
)
from free_alert_service import TelegramAlertDispatcher, FreeAlertManager


class TestTrilingualMessageBuilder(unittest.TestCase):
    """Verifies format, language ordering, and dynamic values in trilingual alert."""

    def test_message_contains_all_three_languages(self):
        """1. Message contains English, Kannada, and Tamil sections."""
        msg = build_trilingual_alert(elephant_count=2, location="Monitoring Zone 1")
        self.assertIn("1. ENGLISH", msg)
        self.assertIn("2. ಕನ್ನಡ", msg)
        self.assertIn("3. தமிழ்", msg)

    def test_strict_language_order_english_kannada_tamil(self):
        """2. Language order must always be: 1. English, 2. Kannada, 3. Tamil."""
        msg = build_trilingual_alert(elephant_count=3, location="Monitoring Zone 1")
        pos_en = msg.find("1. ENGLISH")
        pos_kn = msg.find("2. ಕನ್ನಡ")
        pos_ta = msg.find("3. தமிழ்")

        self.assertTrue(pos_en != -1 and pos_kn != -1 and pos_ta != -1)
        self.assertLess(pos_en, pos_kn, "English must appear before Kannada")
        self.assertLess(pos_kn, pos_ta, "Kannada must appear before Tamil")

    def test_elephant_count_insertion_plural_and_singular(self):
        """3. Actual elephant count is correctly inserted with grammatical agreement."""
        # Plural count (3)
        msg_3 = build_trilingual_alert(elephant_count=3, location="Monitoring Zone 1")
        self.assertIn("Elephant Count: 3", msg_3)
        self.assertIn("Do not approach the elephants", msg_3)
        self.assertIn("ಆನೆಗಳ ಸಂಖ್ಯೆ: 3", msg_3)
        self.assertIn("ಆನೆಗಳ ಹತ್ತಿರ ಹೋಗಬೇಡಿ", msg_3)
        self.assertIn("யானைகளின் எண்ணிக்கை: 3", msg_3)
        self.assertIn("யானைகளின் அருகில் செல்ல வேண்டாம்", msg_3)

        # Singular count (1)
        msg_1 = build_trilingual_alert(elephant_count=1, location="Monitoring Zone 1")
        self.assertIn("Elephant Count: 1", msg_1)
        self.assertIn("Do not approach the elephant.", msg_1)
        self.assertIn("ಆನೆಗಳ ಸಂಖ್ಯೆ: 1", msg_1)
        self.assertIn("ಆನೆಯ ಹತ್ತಿರ ಹೋಗಬೇಡಿ", msg_1)
        self.assertIn("யானையின் எண்ணிக்கை: 1", msg_1)
        self.assertIn("யானையின் அருகில் செல்ல வேண்டாம்", msg_1)

    def test_monitoring_location_inserted_and_translated(self):
        """4. Monitoring location is inserted and properly localized."""
        msg = build_trilingual_alert(elephant_count=2, location="Monitoring Zone 2")
        self.assertIn("Location: Monitoring Zone 2", msg)
        self.assertIn("ಸ್ಥಳ: ನಿಗಾ ವಲಯ 2", msg)
        self.assertIn("இடம்: கண்காணிப்பு பகுதி 2", msg)

    def test_timestamp_formatted_correctly(self):
        """5. Timestamp generated automatically with day, month, year, time."""
        fixed_dt = datetime(2026, 10, 26, 9, 15)
        msg = build_trilingual_alert(elephant_count=1, location="Monitoring Zone 1", timestamp=fixed_dt)
        self.assertIn("26 October 2026, 9:15 AM", msg)
        self.assertIn("26 ಅಕ್ಟೋಬರ್ 2026, ಬೆಳಿಗ್ಗೆ 9:15", msg)
        self.assertIn("26 அக்டோபர் 2026, காலை 9:15", msg)

    def test_unicode_kannada_and_tamil_preserved(self):
        """6. Unicode characters in Kannada and Tamil are fully preserved without corruption."""
        msg = build_trilingual_alert(elephant_count=2, location="Monitoring Zone 1")
        # Kannada unicode sample
        self.assertIn("ಸುರಕ್ಷಿತ ಅಂತರವನ್ನು ಕಾಯ್ದುಕೊಳ್ಳಿ", msg)
        self.assertIn("ಅರಣ್ಯ ಇಲಾಖೆಯ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ", msg)
        # Tamil unicode sample
        self.assertIn("பாதுகாப்பான தூரத்தில் இருங்கள்", msg)
        self.assertIn("வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றுங்கள்", msg)

    def test_whatsapp_and_telegram_receive_identical_message_content(self):
        """7. WhatsApp and Telegram receive the exact same generated message text."""
        shared_text = build_trilingual_alert(elephant_count=4, location="Monitoring Zone 1")
        tg_text = TelegramAlertDispatcher.build_trilingual_alert(count=4, location="Monitoring Zone 1")
        # Ensure exact match
        self.assertEqual(shared_text, tg_text)
        self.assertNotIn("<b>", shared_text, "No HTML tags in cross-platform text")
        self.assertNotIn("</b>", shared_text, "No HTML tags in cross-platform text")


class TestWhatsAppServiceAndCooldown(unittest.TestCase):
    """Verifies WhatsApp PyWhatKit service, worker queue, phone normalization, and cooldown."""

    def setUp(self):
        self.service = WhatsAppPyWhatKitService()
        self.service.config["enabled"] = False
        self.service.config["cooldown_seconds"] = 10
        self.service.last_alert_time = 0.0

    def test_phone_normalization_and_validation(self):
        """14. Recipient phone numbers normalized to +91 E.164 format and validated."""
        valid_1, err1 = normalize_phone_number("+917094528671")
        self.assertEqual(valid_1, "+917094528671")
        self.assertIsNone(err1)

        valid_2, err2 = normalize_phone_number("7094528671")
        self.assertEqual(valid_2, "+917094528671")
        self.assertIsNone(err2)

        valid_3, err3 = normalize_phone_number("07094528671")
        self.assertEqual(valid_3, "+917094528671")
        self.assertIsNone(err3)

        invalid, err4 = normalize_phone_number("12345")
        self.assertIsNone(invalid)
        self.assertIsNotNone(err4)

    def test_phone_number_masking(self):
        """Ensures phone numbers are masked for security and privacy."""
        masked = mask_phone_number("+917094528671")
        self.assertEqual(masked, "+91 70••••671")
        self.assertEqual(mask_phone_number(None), "Not configured")

    @patch('pywhatkit.sendwhatmsg_instantly')
    def test_whatsapp_disabled_mode_does_not_invoke_pywhatkit(self, mock_pywhatkit):
        """8. When WhatsApp alerts are disabled, PyWhatKit is NEVER called."""
        self.service.config["enabled"] = False
        res = self.service.queue_elephant_alert(elephant_count=2, location="Monitoring Zone 1")

        self.assertFalse(res["queued"])
        self.assertEqual(res["status"], WhatsAppPyWhatKitService.STATUS_SKIPPED)
        self.assertIn("disabled", res["reason"])
        mock_pywhatkit.assert_not_called()

    @patch('pywhatkit.sendwhatmsg_instantly')
    def test_cooldown_prevents_duplicate_alerts(self, mock_pywhatkit):
        """12. Duplicate detections within cooldown period do not trigger alerts."""
        self.service.config["enabled"] = True
        self.service.config["cooldown_seconds"] = 60
        self.service.last_alert_time = time.time()  # Recent alert

        res = self.service.queue_elephant_alert(elephant_count=3, location="Monitoring Zone 1")
        self.assertFalse(res["queued"])
        self.assertEqual(res["status"], WhatsAppPyWhatKitService.STATUS_SKIPPED)
        self.assertIn("Cooldown active", res["reason"])
        mock_pywhatkit.assert_not_called()

    @patch('pywhatkit.sendwhatmsg_instantly')
    def test_new_detection_triggers_alert_after_cooldown(self, mock_pywhatkit):
        """13. A new detection event after cooldown period is permitted."""
        self.service.config["enabled"] = True
        self.service.config["cooldown_seconds"] = 60
        self.service.last_alert_time = time.time() - 100  # Elapsed cooldown

        res = self.service.queue_elephant_alert(elephant_count=3, location="Monitoring Zone 1")
        self.assertTrue(res["queued"])
        self.assertEqual(res["status"], WhatsAppPyWhatKitService.STATUS_QUEUED)

    @patch('pywhatkit.sendwhatmsg_instantly')
    def test_pywhatkit_invocation_success_reports_attempt_completed(self, mock_pywhatkit):
        """15 & 16. PyWhatKit execution completes and records ATTEMPT_COMPLETED without false handset claims."""
        res = self.service.send_single_test_message(
            phone="+917094528671",
            count=3,
            location="Monitoring Zone 1",
            confirmed=True
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], WhatsAppPyWhatKitService.STATUS_ATTEMPT_COMPLETED)
        self.assertIn("Requires logged-in browser session", res["details"])
        mock_pywhatkit.assert_called_once()

    @patch('pywhatkit.sendwhatmsg_instantly', side_effect=RuntimeError("Browser window failed to open"))
    def test_pywhatkit_browser_failure_handled_gracefully(self, mock_pywhatkit):
        """15. Browser failures produce informative error without crashing."""
        res = self.service.send_single_test_message(
            phone="+917094528671",
            count=2,
            location="Monitoring Zone 1",
            confirmed=True
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], WhatsAppPyWhatKitService.STATUS_FAILED)
        self.assertIn("Browser window failed to open", res["error"])


class TestDetectionPipelineIntegration(unittest.TestCase):
    """Verifies non-blocking pipeline dispatch, independent failure isolation, and toggle controls."""

    @patch('free_alert_service.FreeAlertManager.trigger_elephant_detection_event')
    @patch('whatsapp_pywhatkit_service.WhatsAppPyWhatKitService.queue_elephant_alert')
    def test_telegram_disabled_mode_does_not_send_telegram(self, mock_wa_queue, mock_tg_trigger):
        """9. When TELEGRAM_ALERTS_ENABLED=false, Telegram messages are not sent."""
        from server import sync_detection_record
        with patch.dict(os.environ, {"TELEGRAM_ALERTS_ENABLED": "false", "WHATSAPP_ALERTS_ENABLED": "false"}):
            success, res = sync_detection_record(
                timestamp_iso=datetime.now().isoformat(),
                elephant_count=2,
                confidence=0.92,
                image_filename="test.jpg"
            )
            self.assertTrue(success)
            mock_tg_trigger.assert_not_called()

    @patch('free_alert_service.FreeAlertManager.trigger_elephant_detection_event', side_effect=Exception("Telegram Network Failure"))
    @patch('whatsapp_pywhatkit_service.WhatsAppPyWhatKitService.queue_elephant_alert')
    def test_telegram_failure_does_not_prevent_whatsapp_or_crash_pipeline(self, mock_wa_queue, mock_tg_trigger):
        """10 & 11. Telegram failure does not crash pipeline and allows independent WhatsApp processing."""
        from server import sync_detection_record
        with patch.dict(os.environ, {"TELEGRAM_ALERTS_ENABLED": "true", "WHATSAPP_ALERTS_ENABLED": "true"}):
            mock_wa_queue.return_value = {"queued": True, "status": "QUEUED"}
            success, res = sync_detection_record(
                timestamp_iso=datetime.now().isoformat(),
                elephant_count=1,
                confidence=0.88,
                image_filename="test.jpg"
            )
            # Pipeline completes successfully without crashing
            self.assertTrue(success)
            mock_wa_queue.assert_called_once()

    @patch('free_alert_service.FreeAlertManager.trigger_elephant_detection_event')
    @patch('whatsapp_pywhatkit_service.WhatsAppPyWhatKitService.queue_elephant_alert', side_effect=Exception("WhatsApp Queue Failure"))
    def test_whatsapp_exception_does_not_crash_pipeline(self, mock_wa_queue, mock_tg_trigger):
        """10. WhatsApp exception does not crash detection pipeline."""
        from server import sync_detection_record
        with patch.dict(os.environ, {"TELEGRAM_ALERTS_ENABLED": "true", "WHATSAPP_ALERTS_ENABLED": "true"}):
            success, res = sync_detection_record(
                timestamp_iso=datetime.now().isoformat(),
                elephant_count=3,
                confidence=0.95,
                image_filename="test.jpg"
            )
            self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
