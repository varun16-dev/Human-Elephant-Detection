"""
Unit & Integration Tests for Real Test Message Delivery Verification Engine
Covers:
- Step 1: Messaging method capability checks (Telegram, Carrier SMS, GSM SIM)
- Step 3: Validation of credentials, recipient formatting, and provider handshakes
- Step 4: Explicit authorization enforcement (confirmed=True required)
- Step 5: Accurate 5-tier status reporting:
  * CONFIGURATION_INVALID
  * SEND_FAILED
  * ACCEPTED_BY_PROVIDER
  * AWAITING_RECIPIENT_CONFIRMATION
  * DELIVERY_CONFIRMED
- Security: Token/credential masking, no secret leaks in logs or API responses
- Manual recipient receipt confirmation
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import smtplib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from free_alert_service import FreeAlertManager, get_free_alert_manager
from server import app


class TestRealDeliveryVerification(unittest.TestCase):

    def setUp(self):
        self.mgr = get_free_alert_manager()
        self._orig_config = dict(self.mgr.config)
        self.mgr.config["telegram_bot_token"] = ""
        self.mgr.config["telegram_chat_id"] = ""
        self.mgr.config["smtp_email"] = ""
        self.mgr.config["smtp_password"] = ""
        self.mgr.config["default_phone"] = ""

        self.app_client = app.test_client()
        self.app_client.testing = True

    def tearDown(self):
        self.mgr.config.clear()
        self.mgr.config.update(self._orig_config)
        self.mgr.reload_config()

    def test_missing_credentials_returns_configuration_invalid(self):
        """Step 3: Validation fails if sender credentials or recipient are missing."""
        # Telegram without token
        res_tg = self.mgr.validate_configuration("telegram", recipient="12345678")
        self.assertEqual(res_tg["status"], "CONFIGURATION_INVALID")
        self.assertFalse(res_tg["can_send"])
        self.assertIn("TELEGRAM_BOT_TOKEN", res_tg["details"])

        # SMTP without credentials
        res_smtp = self.mgr.validate_configuration("email_sms", recipient="5551234567", carrier_key="verizon")
        self.assertEqual(res_smtp["status"], "CONFIGURATION_INVALID")
        self.assertFalse(res_smtp["can_send"])
        self.assertIn("credentials", res_smtp["details"])

    def test_gsm_sim_unsupported_returns_configuration_invalid(self):
        """Step 1 & 3: GSM/SIM hardware method returns CONFIGURATION_INVALID with clear hardware notice."""
        res = self.mgr.validate_configuration("gsm_sim", recipient="+919876543210")
        self.assertEqual(res["status"], "CONFIGURATION_INVALID")
        self.assertFalse(res["can_send"])
        self.assertIn("GSM/SIM hardware modem is not detected or supported", res["error"])

    def test_indian_number_on_carrier_sms_returns_configuration_invalid(self):
        """Step 3: Validates that Indian numbers (+91) on Carrier Email-to-SMS are rejected with TRAI explanation."""
        self.mgr.config["smtp_email"] = "alerts@example.com"
        self.mgr.config["smtp_password"] = "16charpassword12"

        res = self.mgr.validate_configuration("email_sms", recipient="+919876543210", carrier_key="verizon")
        self.assertEqual(res["status"], "CONFIGURATION_INVALID")
        self.assertFalse(res["can_send"])
        self.assertIn("Indian mobile numbers", res["error"])

    def test_send_test_without_explicit_confirmation_aborts(self):
        """Step 4: Explicit confirmation is strictly required; confirmed=False rejects dispatch."""
        res = self.mgr.send_real_test_message("telegram", recipient="12345678", confirmed=False)
        self.assertEqual(res["status"], "CONFIGURATION_INVALID")
        self.assertIn("Explicit confirmation required", res["error"])

        # Test through Flask API
        resp = self.app_client.post('/api/alerts/verify/send-test', json={
            "method": "telegram",
            "recipient": "12345678",
            "confirmed": False
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["status"], "CONFIGURATION_INVALID")

    @patch('requests.post')
    def test_telegram_provider_rejection_returns_send_failed(self, mock_post):
        """Step 5: When Telegram API returns ok: false, status is SEND_FAILED."""
        self.mgr.config["telegram_bot_token"] = "123456:FAKE_TOKEN_FOR_TEST"
        self.mgr.config["telegram_chat_id"] = "98765432"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: chat not found"
        }
        mock_post.return_value = mock_resp

        res = self.mgr.send_real_test_message("telegram", recipient="98765432", confirmed=True)
        self.assertEqual(res["status"], "SEND_FAILED")
        self.assertIn("chat not found", res["details"])
        self.assertEqual(res["raw_response"]["error_code"], 400)

    @patch('requests.post')
    def test_telegram_accepted_returns_awaiting_recipient_confirmation(self, mock_post):
        """Step 5: When Telegram API accepts the message, status is AWAITING_RECIPIENT_CONFIRMATION."""
        self.mgr.config["telegram_bot_token"] = "123456:LIVE_TOKEN_MOCK"
        self.mgr.config["telegram_chat_id"] = "123456789"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "result": {
                "message_id": 44321,
                "chat": {"id": 123456789, "type": "private"},
                "date": 1729781000
            }
        }
        mock_post.return_value = mock_resp

        res = self.mgr.send_real_test_message("telegram", recipient="123456789", confirmed=True)
        self.assertEqual(res["status"], "AWAITING_RECIPIENT_CONFIRMATION")
        self.assertIn("Message ID 44321", res["details"])
        self.assertEqual(res["raw_response"]["message_id"], 44321)
        # Message content must match required test alert
        self.assertEqual(res["message"], "TEST ALERT: Human-Elephant Detection System message delivery verification.")
        # Ensure token is never leaked
        self.assertNotIn("LIVE_TOKEN_MOCK", str(res))

    @patch('smtplib.SMTP')
    def test_carrier_sms_smtp_acceptance_returns_accepted_by_provider(self, mock_smtp_cls):
        """Step 5: When SMTP server accepts message, status is ACCEPTED_BY_PROVIDER (cellular delivery unconfirmed)."""
        self.mgr.config["smtp_email"] = "alerts@gmail.com"
        self.mgr.config["smtp_password"] = "abcdefghijklmnop"

        mock_server = MagicMock()
        mock_server.sendmail.return_value = {}  # Empty dict = 0 rejected recipients
        mock_smtp_cls.return_value = mock_server

        res = self.mgr.send_real_test_message(
            "email_sms",
            recipient="5551234567",
            carrier_key="verizon",
            confirmed=True
        )
        self.assertEqual(res["status"], "ACCEPTED_BY_PROVIDER")
        self.assertIn("accepted message for carrier gateway relay", res["details"])
        self.assertEqual(res["raw_response"]["status_code"], 250)
        # Password must never be exposed
        self.assertNotIn("abcdefghijklmnop", str(res))

    @patch('smtplib.SMTP')
    def test_carrier_sms_smtp_auth_failure_returns_send_failed(self, mock_smtp_cls):
        """Step 5: When SMTP auth fails, status is SEND_FAILED."""
        self.mgr.config["smtp_email"] = "alerts@gmail.com"
        self.mgr.config["smtp_password"] = "badpassword"

        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication credentials invalid")
        mock_smtp_cls.return_value = mock_server

        res = self.mgr.send_real_test_message(
            "email_sms",
            recipient="5551234567",
            carrier_key="verizon",
            confirmed=True
        )
        self.assertEqual(res["status"], "SEND_FAILED")
        self.assertIn("SMTP Authentication Rejected", res["details"])

    def test_manual_receipt_confirmation_transitions_to_delivery_confirmed(self):
        """Step 5: Recipient manually confirms receipt -> status transitions to DELIVERY_CONFIRMED."""
        # Create an in-flight test event
        event_id = "test_unit_event_123"
        record = {
            "event_id": event_id,
            "timestamp": "2026-10-24 20:30:00",
            "type": "REAL_DELIVERY_TEST",
            "method": "telegram",
            "masked_sender": "Bot: @TestBot",
            "masked_recipient": "Chat ID: 1234••••",
            "message": "TEST ALERT: Human-Elephant Detection System message delivery verification.",
            "status": "AWAITING_RECIPIENT_CONFIRMATION",
            "details": "Accepted by Telegram API",
            "raw_response": {"ok": True},
            "confirmed_at": None
        }
        self.mgr._record_history(record)

        # Confirm receipt
        ok, updated = self.mgr.confirm_receipt(event_id)
        self.assertTrue(ok)
        self.assertEqual(updated["status"], "DELIVERY_CONFIRMED")
        self.assertIsNotNone(updated["confirmed_at"])
        self.assertIn("Handset receipt confirmed", updated["details"])

        # Also verify via API endpoint
        resp = self.app_client.post('/api/alerts/verify/confirm-receipt', json={"event_id": event_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "success")

    def test_recipient_and_sender_masking(self):
        """Step 4: Recipient identifiers and sender tokens are securely masked."""
        # Telegram Chat ID masking
        masked_chat = FreeAlertManager.mask_recipient("telegram", "123456789")
        self.assertNotIn("123456789", masked_chat)
        self.assertIn("••••", masked_chat)

        # Telegram Channel username masking
        masked_channel = FreeAlertManager.mask_recipient("telegram", "@elephant_warnings")
        self.assertTrue(masked_channel.startswith("@ele"))
        self.assertIn("****", masked_channel)

        # US Phone masking
        masked_phone = FreeAlertManager.mask_recipient("email_sms", "5551234567", "verizon")
        self.assertNotIn("555123", masked_phone)
        self.assertIn("4567", masked_phone)
        self.assertIn("VERIZON", masked_phone)

        # Email sender masking
        masked_email = FreeAlertManager.mask_sender("email_sms", "elephant_command@gmail.com")
        self.assertNotIn("elephant_command@", masked_email)
        self.assertIn("@gmail.com", masked_email)

        # Telegram bot token masking
        masked_token = FreeAlertManager.mask_sender("telegram", "1234567890:AAHq_m7eZ589fakeTokenXYZ")
        self.assertNotIn("fakeTokenXYZ", masked_token)
        self.assertIn("1234567890", masked_token)


if __name__ == '__main__':
    unittest.main()
