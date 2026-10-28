"""
Automated Unit and Integration Tests for Twilio Programmable Messaging
Department of AI & ML, Sri Sairam College of Engineering

Ensures:
- 100% mocked - Never makes real network requests or sends real SMS
- Bilingual message formatting for Tamil Nadu and Karnataka
- Dynamic elephant count, singular/plural, location, and timestamps
- Cooldown, duplicate suppression, and count-change policies
- Absence reset interval closing incidents
- Twilio error handling (authentication, rate limits, transient network retries)
- StatusCallback delivery report webhook handling
- Credential masking and dashboard REST API endpoints
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from twilio_sms_service import (
    BilingualTwilioMessageBuilder,
    TwilioSmsManager,
    mask_phone_number,
    mask_credential,
    get_twilio_sms_manager
)
from server import app


class TestBilingualTwilioMessageBuilder(unittest.TestCase):
    """Verifies bilingual message construction and SMS segmentation metrics."""

    def test_tamil_nadu_bilingual_message_plural(self):
        """Verifies Tamil Nadu formatting with English + Tamil for multiple elephants."""
        msg = BilingualTwilioMessageBuilder.build_alert_message(
            count=3,
            location="Monitoring Zone 1",
            state="tamil_nadu",
            timestamp_str="25/10/2026, 12:30:00"
        )
        self.assertIn("🚨 ELEPHANT ALERT!", msg)
        self.assertIn("English: 3 elephants detected at Monitoring Zone 1.", msg)
        self.assertIn("Time: 25/10/2026, 12:30:00", msg)
        self.assertIn("Please stay safe and inform the forest department.", msg)
        # Tamil translation check
        self.assertIn("தமிழ்: Monitoring Zone 1-ல் 3 யானைகள் கண்டறியப்பட்டுள்ளன.", msg)
        self.assertIn("பாதுகாப்பாக இருங்கள் மற்றும் வனத்துறைக்குத் தகவல் தெரிவிக்கவும்.", msg)

    def test_tamil_nadu_bilingual_message_singular(self):
        """Verifies singular noun agreement for 1 elephant in English and Tamil."""
        msg = BilingualTwilioMessageBuilder.build_alert_message(
            count=1,
            location="Zone North",
            state="tamil_nadu",
            timestamp_str="25/10/2026, 12:30:00"
        )
        self.assertIn("English: 1 elephant detected at Zone North.", msg)
        self.assertIn("தமிழ்: Zone North-ல் 1 யானை கண்டறியப்பட்டுள்ளன.", msg)

    def test_concise_bilingual_message_prompt_format(self):
        """Verifies concise English + Tamil advisory matching the exact prompt template."""
        msg = BilingualTwilioMessageBuilder.build_alert_message(
            count=1,
            location=None,
            state="tamil_nadu",
            timestamp_str=None,
            format_type="concise"
        )
        self.assertIn("ALERT: Elephant detected near the monitored area.", msg)
        self.assertIn("Please maintain a safe distance and follow local forest department instructions.", msg)
        self.assertIn("எச்சரிக்கை: கண்காணிக்கப்படும் பகுதியில் யானை கண்டறியப்பட்டுள்ளது.", msg)
        self.assertIn("பாதுகாப்பான தூரத்தில் இருங்கள் மற்றும் வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றுங்கள்.", msg)

    def test_concise_bilingual_message_with_location_and_timestamp(self):
        """Verifies concise formatting with dynamic herd count, location, and timestamp."""
        msg = BilingualTwilioMessageBuilder.build_alert_message(
            count=3,
            location="Sector 4 Corridor",
            state="tamil_nadu",
            timestamp_str="26/10/2026, 08:30:00",
            format_type="concise"
        )
        self.assertIn("ALERT: 3 elephants detected near Sector 4 Corridor. Time: 26/10/2026, 08:30:00.", msg)
        self.assertIn("எச்சரிக்கை: Sector 4 Corridor பகுதியில் 3 யானைகள் கண்டறியப்பட்டுள்ளது. நேரம்: 26/10/2026, 08:30:00.", msg)

    def test_karnataka_bilingual_message_plural(self):
        """Verifies Karnataka formatting with English + Kannada for multiple elephants."""
        msg = BilingualTwilioMessageBuilder.build_alert_message(
            count=2,
            location="Monitoring Zone 2",
            state="karnataka",
            timestamp_str="25/10/2026, 12:30:00"
        )
        self.assertIn("🚨 ELEPHANT ALERT!", msg)
        self.assertIn("English: 2 elephants detected at Monitoring Zone 2.", msg)
        self.assertIn("Time: 25/10/2026, 12:30:00", msg)
        self.assertIn("Please stay safe and inform the forest department.", msg)
        # Kannada translation check
        self.assertIn("ಕನ್ನಡ: Monitoring Zone 2ನಲ್ಲಿ 2 ಆನೆಗಳು ಪತ್ತೆಯಾಗಿವೆ.", msg)
        self.assertIn("ಸುರಕ್ಷಿತವಾಗಿರಿ ಮತ್ತು ಅರಣ್ಯ ಇಲಾಖೆಗೆ ಮಾಹಿತಿ ನೀಡಿ.", msg)

    def test_karnataka_bilingual_message_singular(self):
        """Verifies singular noun agreement for 1 elephant in English and Kannada."""
        msg = BilingualTwilioMessageBuilder.build_alert_message(
            count=1,
            location="Buffer Sector 3",
            state="karnataka",
            timestamp_str="25/10/2026, 12:30:00"
        )
        self.assertIn("English: 1 elephant detected at Buffer Sector 3.", msg)
        self.assertIn("ಕನ್ನಡ: Buffer Sector 3ನಲ್ಲಿ 1 ಆನೆ ಪತ್ತೆಯಾಗಿವೆ.", msg)

    def test_segment_calculation_unicode(self):
        """Verifies UCS-2 segmentation calculation for regional Unicode characters."""
        sample_unicode = "🚨 ELEPHANT ALERT! தமிழ்: பாதுகாப்பு எச்சரிக்கை"
        metrics = BilingualTwilioMessageBuilder.calculate_segments(sample_unicode)
        self.assertTrue(metrics["is_unicode"])
        self.assertEqual(metrics["encoding"], "UCS-2 (Unicode)")
        self.assertGreater(metrics["segment_count"], 0)

    def test_segment_calculation_gsm7(self):
        """Verifies GSM-7 calculation for pure ASCII text."""
        sample_ascii = "ELEPHANT ALERT: 1 elephant detected at Sector 4."
        metrics = BilingualTwilioMessageBuilder.calculate_segments(sample_ascii)
        self.assertFalse(metrics["is_unicode"])
        self.assertEqual(metrics["encoding"], "GSM-7")
        self.assertEqual(metrics["segment_count"], 1)


class TestTwilioMaskingAndConfig(unittest.TestCase):
    """Verifies credential and phone number privacy masking."""

    def test_mask_phone_number(self):
        self.assertEqual(mask_phone_number("+917094528671"), "+9170*** ***71")
        self.assertEqual(mask_phone_number("+15551234567"), "+1555*** ***67")
        self.assertEqual(mask_phone_number(""), "Not configured")
        self.assertEqual(mask_phone_number(None), "Not configured")

    def test_mask_credential(self):
        sid = "AC_test_account_sid_for_mock_1234"
        masked = mask_credential(sid, 4, 4)
        self.assertEqual(masked, "AC_t...1234")
        self.assertNotIn("account_sid_for", masked)


class TestTwilioSmsManager(unittest.TestCase):
    """Verifies core Twilio SMS dispatch, state machine, and error handling."""

    def setUp(self):
        self.test_config_path = os.path.join(os.path.dirname(__file__), "temp_twilio_config.json")
        self.test_history_path = os.path.join(os.path.dirname(__file__), "temp_twilio_history.json")
        self.mgr = TwilioSmsManager(config_path=self.test_config_path, history_path=self.test_history_path)
        self.mgr.config.update({
            "enabled": True,
            "account_sid": "AC_mock_test_account_sid_for_tests",
            "auth_token": "test_auth_token_secret_12345678",
            "from_number": "+15551234567",
            "to_number": "+917094528671",
            "cooldown_seconds": 60,
            "count_change_policy": "increase_only",
            "absence_reset_seconds": 30
        })

    def tearDown(self):
        if os.path.exists(self.test_config_path):
            try: os.remove(self.test_config_path)
            except: pass
        if os.path.exists(self.test_history_path):
            try: os.remove(self.test_history_path)
            except: pass

    @patch.object(TwilioSmsManager, "_get_twilio_client")
    def test_validate_credentials_success(self, mock_client_factory):
        """Verifies account fetch verification when credentials are valid."""
        mock_client = MagicMock()
        mock_account = MagicMock()
        mock_account.friendly_name = "HEWS Wildlife Demo"
        mock_account.status = "active"
        mock_account.type = "Full"
        mock_client.api.accounts.return_value.fetch.return_value = mock_account
        mock_client_factory.return_value = mock_client

        valid, msg, details = self.mgr.validate_credentials()
        self.assertTrue(valid)
        self.assertIn("Connected to Twilio Account", msg)
        self.assertEqual(details["friendly_name"], "HEWS Wildlife Demo")

    @patch.object(TwilioSmsManager, "_get_twilio_client")
    def test_validate_credentials_auth_failure(self, mock_client_factory):
        """Verifies clear error reporting on invalid credentials (Twilio 20003)."""
        mock_client = MagicMock()
        mock_client.api.accounts.return_value.fetch.side_effect = Exception("HTTP 401: 20003 Authentication Error")
        mock_client_factory.return_value = mock_client

        valid, msg, _ = self.mgr.validate_credentials()
        self.assertFalse(valid)
        self.assertIn("Authentication Failed", msg)

    @patch.object(TwilioSmsManager, "_get_twilio_client")
    def test_send_sms_success(self, mock_client_factory):
        """Verifies successful SMS submission and record logging."""
        mock_client = MagicMock()
        mock_msg_resource = MagicMock()
        mock_msg_resource.sid = "SM999888777666555"
        mock_msg_resource.status = "queued"
        mock_client.messages.create.return_value = mock_msg_resource
        mock_client_factory.return_value = mock_client

        success, msg, record = self.mgr.send_sms(
            to_number="+917094528671",
            body="🚨 ELEPHANT ALERT! 2 elephants detected.",
            status_callback="https://example.com/api/twilio/webhook"
        )
        self.assertTrue(success)
        self.assertIn("SM999888777666555", msg)
        self.assertEqual(record["status"], "QUEUED")
        self.assertEqual(record["message_sid"], "SM999888777666555")
        mock_client.messages.create.assert_called_once_with(
            body="🚨 ELEPHANT ALERT! 2 elephants detected.",
            from_="+15551234567",
            to="+917094528671",
            status_callback="https://example.com/api/twilio/webhook"
        )

    @patch.object(TwilioSmsManager, "_get_twilio_client")
    def test_send_sms_trial_unverified_error(self, mock_client_factory):
        """Verifies friendly error message for Twilio Trial Error 21608 (unverified recipient)."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("21608: The number +917094528671 is unverified.")
        mock_client_factory.return_value = mock_client

        success, msg, record = self.mgr.send_sms("+917094528671", "Test")
        self.assertFalse(success)
        self.assertIn("Twilio Trial Restriction", msg)
        self.assertEqual(record["status"], "FAILED")

    @patch.object(TwilioSmsManager, "_get_twilio_client")
    def test_send_sms_transient_retry(self, mock_client_factory):
        """Verifies bounded retry on transient network connection errors."""
        mock_client = MagicMock()
        # Fail first, succeed second
        mock_msg_resource = MagicMock()
        mock_msg_resource.sid = "SM_RETRY_OK"
        mock_msg_resource.status = "queued"
        mock_client.messages.create.side_effect = [
            ConnectionResetError("Transient connection reset"),
            mock_msg_resource
        ]
        mock_client_factory.return_value = mock_client

        success, msg, record = self.mgr.send_sms("+917094528671", "Retry test", max_retries=1)
        self.assertTrue(success)
        self.assertEqual(record["message_sid"], "SM_RETRY_OK")
        self.assertEqual(mock_client.messages.create.call_count, 2)

    @patch.object(TwilioSmsManager, "_get_twilio_client")
    def test_send_sms_with_messaging_service_sid(self, mock_client_factory):
        """Verifies sending via Messaging Service SID instead of from_number."""
        self.mgr.config["from_number"] = ""
        self.mgr.config["messaging_service_sid"] = "MGf72320860ba724d666d95eea08c1405d"

        mock_client = MagicMock()
        mock_msg_resource = MagicMock()
        mock_msg_resource.sid = "SM_MSG_SRV_OK"
        mock_msg_resource.status = "queued"
        mock_client.messages.create.return_value = mock_msg_resource
        mock_client_factory.return_value = mock_client

        success, msg, record = self.mgr.send_sms(
            to_number="+917094528671",
            body="ALERT: Elephant detected."
        )
        self.assertTrue(success)
        self.assertEqual(record["message_sid"], "SM_MSG_SRV_OK")
        self.assertEqual(record["sender_type"], "messaging_service")
        mock_client.messages.create.assert_called_once_with(
            body="ALERT: Elephant detected.",
            messaging_service_sid="MGf72320860ba724d666d95eea08c1405d",
            to="+917094528671"
        )

    def test_send_sms_missing_all_senders(self):
        """Verifies rejection when neither from_number nor messaging_service_sid is configured."""
        self.mgr.config["from_number"] = ""
        self.mgr.config["messaging_service_sid"] = ""
        success, msg, _ = self.mgr.send_sms("+917094528671", "Test")
        self.assertFalse(success)
        self.assertIn("Neither From Phone Number nor Messaging Service SID is configured", msg)

    def test_send_sms_missing_credentials(self):
        """Verifies rejection when Twilio Account SID or Auth Token is missing."""
        self.mgr.config["account_sid"] = ""
        success, msg, _ = self.mgr.send_sms("+917094528671", "Test")
        self.assertFalse(success)
        self.assertIn("SID or Token missing", msg)

    def test_send_sms_missing_recipient(self):
        """Verifies rejection when recipient number is empty or whitespace."""
        success, msg, _ = self.mgr.send_sms("", "Test")
        self.assertFalse(success)
        self.assertIn("Recipient phone number is missing", msg)

    @patch.object(TwilioSmsManager, "_get_twilio_client")
    def test_send_sms_invalid_number_error(self, mock_client_factory):
        """Verifies error handling for invalid destination number (Twilio 21211)."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("21211: Invalid To phone number.")
        mock_client_factory.return_value = mock_client

        success, msg, _ = self.mgr.send_sms("+9199", "Test")
        self.assertFalse(success)
        self.assertIn("Invalid 'To' phone number format", msg)

    @patch.object(TwilioSmsManager, "_get_twilio_client")
    def test_send_sms_messaging_service_not_found(self, mock_client_factory):
        """Verifies error handling for missing Messaging Service SID (Twilio 21703)."""
        self.mgr.config["from_number"] = ""
        self.mgr.config["messaging_service_sid"] = "MG12345678901234567890123456789012"
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("21703: Messaging Service SID not found.")
        mock_client_factory.return_value = mock_client

        success, msg, _ = self.mgr.send_sms("+917094528671", "Test")
        self.assertFalse(success)
        self.assertIn("Messaging Service SID", msg)
        self.assertIn("not found or invalid", msg)

    @patch.object(TwilioSmsManager, "_get_twilio_client")
    def test_send_sms_rate_limit_error(self, mock_client_factory):
        """Verifies error handling for Twilio API rate limiting (Twilio 20429)."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("20429: Too Many Requests")
        mock_client_factory.return_value = mock_client

        success, msg, _ = self.mgr.send_sms("+917094528671", "Test")
        self.assertFalse(success)
        self.assertIn("Rate Limit Exceeded", msg)

    @patch.object(TwilioSmsManager, "send_sms")
    def test_detection_sync_with_float_count(self, mock_send_sms):
        """Verifies robust parsing when elephant count is passed as float or float-string."""
        mock_send_sms.return_value = (True, "Sent", {"status": "QUEUED"})
        ok, msg = self.mgr.process_detection_sync(elephant_count=2.0, confidence=0.92)
        self.assertTrue(ok)
        self.assertEqual(mock_send_sms.call_count, 1)

    @patch.object(TwilioSmsManager, "send_sms")
    def test_duplicate_suppression_and_cooldown(self, mock_send_sms):
        """Verifies that duplicate frames during cooldown are suppressed."""
        mock_send_sms.return_value = (True, "Sent", {"status": "QUEUED"})

        # Frame 1: Detection of 2 elephants -> Sent
        ok1, _ = self.mgr.process_detection_sync(elephant_count=2, confidence=0.85)
        self.assertTrue(ok1)
        self.assertEqual(mock_send_sms.call_count, 1)

        # Frame 2: Same count (2 elephants) 2 seconds later -> Suppressed
        ok2, msg2 = self.mgr.process_detection_sync(elephant_count=2, confidence=0.86)
        self.assertFalse(ok2)
        self.assertIn("Duplicate suppressed", msg2)
        self.assertEqual(mock_send_sms.call_count, 1)

    @patch.object(TwilioSmsManager, "send_sms")
    def test_count_increase_triggers_alert_during_cooldown(self, mock_send_sms):
        """Verifies policy 'increase_only' dispatches update when herd count increases."""
        mock_send_sms.return_value = (True, "Sent", {"status": "QUEUED"})

        # Initial detection of 1 elephant
        self.mgr.process_detection_sync(elephant_count=1, confidence=0.8)
        self.assertEqual(mock_send_sms.call_count, 1)

        # Count increases to 3 -> Dispatches update alert immediately
        ok, msg = self.mgr.process_detection_sync(elephant_count=3, confidence=0.9)
        self.assertTrue(ok)
        self.assertEqual(mock_send_sms.call_count, 2)

    @patch.object(TwilioSmsManager, "send_sms")
    def test_absence_reset_closes_incident(self, mock_send_sms):
        """Verifies that zero detections for >absence_reset_seconds closes active incident."""
        mock_send_sms.return_value = (True, "Sent", {"status": "QUEUED"})

        # Start incident
        self.mgr.process_detection_sync(elephant_count=2, confidence=0.85)
        self.assertTrue(self.mgr.incident_active)

        # Set last detection time back 40 seconds (> 30s reset)
        self.mgr.last_detection_time = 0.0

        # Zero detection evaluation
        self.mgr.process_detection_sync(elephant_count=0, confidence=0.0)
        self.assertFalse(self.mgr.incident_active)
        self.assertEqual(self.mgr.current_count, 0)

    def test_handle_status_callback_updates_history(self):
        """Verifies StatusCallback updates record status in history."""
        self.mgr.history = [{
            "message_sid": "SM_TEST_CALLBACK",
            "status": "QUEUED",
            "to": "+91 70*** ***71"
        }]
        self.mgr.last_message_sid = "SM_TEST_CALLBACK"

        handled = self.mgr.handle_status_callback({
            "MessageSid": "SM_TEST_CALLBACK",
            "MessageStatus": "delivered"
        })
        self.assertTrue(handled)
        self.assertEqual(self.mgr.history[0]["status"], "DELIVERED")
        self.assertEqual(self.mgr.last_message_status, "DELIVERED")


class TestTwilioRestEndpoints(unittest.TestCase):
    """Verifies Flask REST API endpoints for Twilio integration."""

    def setUp(self):
        self.client = app.test_client()

    def test_get_twilio_status(self):
        res = self.client.get('/api/twilio/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("is_configured", data)
        self.assertIn("account_sid_masked", data)
        self.assertIn("to_number_masked", data)
        # Secrets must never be exposed
        self.assertNotIn("test_auth_token_secret", str(data))

    def test_preview_message_endpoint(self):
        res = self.client.post('/api/twilio/preview-message', json={
            "count": 4,
            "state": "tamil_nadu",
            "location": "Sector 4 Corridor"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("4 elephants", data["message"])
        self.assertIn("4 யானைகள்", data["message"])
        self.assertTrue(data["is_unicode"])
        self.assertGreater(data["segment_count"], 0)

    def test_send_test_requires_confirmation(self):
        """Ensures test message cannot be triggered without explicit authorization flag."""
        res = self.client.post('/api/twilio/send-test', json={
            "confirmed": False
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("Explicit user authorization confirmation required", data["error"])

    @patch("twilio_sms_service.TwilioSmsManager.send_sms")
    def test_send_test_with_confirmation(self, mock_send_sms):
        """Verifies authorized test dispatch when confirmed is True."""
        mock_send_sms.return_value = (True, "Test SMS sent", {
            "message_sid": "SM_TEST_CONFIRMED",
            "status": "QUEUED"
        })

        res = self.client.post('/api/twilio/send-test', json={
            "confirmed": True,
            "to_number": "+917094528671",
            "count": 2,
            "state": "karnataka",
            "location": "Bannerghatta North"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["record"]["message_sid"], "SM_TEST_CONFIRMED")


class TestDetectionWorkflowTwilioIntegration(unittest.TestCase):
    """Verifies that elephant detection events in server.py trigger Twilio async SMS dispatch."""

    def setUp(self):
        self.client = app.test_client()

    @patch("server.get_push_service")
    @patch("notification_service.NotificationService.update_delivery_status")
    @patch("notification_service.NotificationService.process_detection")
    @patch("twilio_sms_service.TwilioSmsManager.process_detection_async")
    def test_process_detection_alert_triggers_twilio_async(
        self, mock_twilio_async, mock_notif_process, mock_update_status, mock_get_push
    ):
        """Verifies /api/alerts/process triggers Twilio process_detection_async without failure."""
        mock_notif_process.return_value = {
            "alert_id": "test_alert_123",
            "timestamp": "26/10/2026, 08:30:00",
            "elephant_count": 2,
            "confidence": 0.91
        }
        mock_push = MagicMock()
        mock_push.is_configured.return_value = False
        mock_get_push.return_value = mock_push

        res = self.client.post('/api/alerts/process', json={
            "elephant_count": 2,
            "confidence": 0.91,
            "image_filename": "elephant_test.jpg"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        mock_twilio_async.assert_called()
        self.assertTrue(any(call.kwargs.get("elephant_count") == 2 for call in mock_twilio_async.call_args_list))

    @patch("server.get_push_service")
    @patch("twilio_sms_service.TwilioSmsManager.process_detection_async")
    def test_sync_detection_record_triggers_twilio_async(self, mock_twilio_async, mock_get_push):
        """Verifies sync_detection_record triggers Twilio process_detection_async."""
        mock_push = MagicMock()
        mock_push.is_configured.return_value = False
        mock_get_push.return_value = mock_push

        from server import sync_detection_record
        with patch("server._save_local_detection_record"):
            success, result = sync_detection_record(
                timestamp_iso="2026-10-26T08:30:00",
                elephant_count=1,
                confidence=0.88,
                image_filename="camera_test.jpg"
            )
            self.assertTrue(success)
            self.assertGreaterEqual(mock_twilio_async.call_count, 1)
            self.assertTrue(any(call.kwargs.get("elephant_count") == 1 for call in mock_twilio_async.call_args_list))


if __name__ == '__main__':
    unittest.main()
