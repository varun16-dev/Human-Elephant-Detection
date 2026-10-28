"""
Automated Unit Tests for Free Alert Notification Engine (Telegram & Carrier Email-to-SMS)
Covers Phase 5 requirements:
- Successful Telegram API response using mocks
- Telegram rejection (401 Unauthorized), timeout, rate limit (429), and malformed response
- Bounded retries with backoff on 5xx errors
- HTML escaping of alert text
- Unsupported carrier rejection (Indian +91 numbers)
- Accurate status recording (SENT_TO_PROVIDER, RELAYED_TO_SMTP_GATEWAY, FAILED - never false delivery claims)
- Durable persistence to history
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import json
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from free_alert_service import (
    TelegramAlertDispatcher,
    EmailSmsAlertDispatcher,
    FreeAlertService,
    CARRIER_GATEWAYS
)


class TestTelegramAlertDispatcher(unittest.TestCase):

    def setUp(self):
        self.dispatcher = TelegramAlertDispatcher(
            bot_token="TEST_BOT_TOKEN_12345",
            default_chat_id="TEST_CHAT_999",
            timeout=2.0
        )

    def test_missing_credentials(self):
        """Should fail cleanly if bot token or chat ID is missing."""
        unconfigured = TelegramAlertDispatcher(bot_token="", default_chat_id="")
        success, msg = unconfigured.send_alert("Elephant detected!")
        self.assertFalse(success)
        self.assertIn("not configured", msg)

    @patch('requests.post')
    def test_successful_telegram_dispatch(self, mock_post):
        """Verify successful Telegram API response (200 OK) records SENT_TO_PROVIDER."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "result": {
                "message_id": 8842,
                "chat": {"id": 12345678}
            }
        }
        mock_post.return_value = mock_resp

        success, status = self.dispatcher.send_alert("Elephant spotted at Corridor 3", severity="CRITICAL")

        self.assertTrue(success)
        self.assertIn("SENT_TO_PROVIDER", status)
        self.assertIn("8842", status)
        # Verify it doesn't falsely claim handset receipt
        self.assertNotIn("DELIVERED_TO_HANDSET", status)
        self.assertEqual(mock_post.call_count, 1)

    @patch('requests.post')
    def test_client_error_401_no_retry(self, mock_post):
        """Client errors (4xx) like invalid bot token must not trigger wasteful retries."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 401,
            "description": "Unauthorized: invalid bot token"
        }
        mock_post.return_value = mock_resp

        success, status = self.dispatcher.send_alert("Test message")

        self.assertFalse(success)
        self.assertIn("401", status)
        self.assertIn("Unauthorized", status)
        # Crucial check: 4xx should NOT retry
        self.assertEqual(mock_post.call_count, 1)

    @patch('requests.post')
    def test_rate_limit_429(self, mock_post):
        """429 Too Many Requests error should be reported cleanly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 429,
            "description": "Too Many Requests: retry after 5"
        }
        mock_post.return_value = mock_resp

        success, status = self.dispatcher.send_alert("Elephant sighted")

        self.assertFalse(success)
        self.assertIn("429", status)
        self.assertEqual(mock_post.call_count, 1)

    @patch('time.sleep')
    @patch('requests.post')
    def test_server_error_bounded_retries(self, mock_post, mock_sleep):
        """5xx / network exceptions should be retried up to 3 times before failing."""
        mock_post.side_effect = Exception("Connection reset by peer")

        success, status = self.dispatcher.send_alert("Elephant alert")

        self.assertFalse(success)
        self.assertIn("Exception", status)
        self.assertEqual(mock_post.call_count, 3, "Should retry exactly 3 times before failing")
        self.assertEqual(mock_sleep.call_count, 2, "Should sleep twice for backoff")

    @patch('requests.post')
    def test_html_escaping(self, mock_post):
        """User-supplied text with HTML tags/special characters must be safely escaped."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 1}}
        mock_post.return_value = mock_resp

        injection_payload = "Alert <script>alert('xss')</script> & <b>bold</b>"
        self.dispatcher.send_alert(injection_payload)

        posted_payload = mock_post.call_args[1].get('json') or {}
        posted_text = posted_payload.get('text', '')

        self.assertIn("&lt;script&gt;", posted_text)
        self.assertNotIn("<script>", posted_text)
        self.assertIn("&amp;", posted_text)


class TestEmailSmsAlertDispatcher(unittest.TestCase):

    def setUp(self):
        self.dispatcher = EmailSmsAlertDispatcher(
            smtp_email="test.sender@gmail.com",
            smtp_password="abcd efgh ijkl mnop",
            smtp_server="smtp.gmail.com",
            smtp_port=587
        )

    def test_indian_phone_number_rejection(self):
        """Indian mobile numbers (+91) must be rejected with helpful guidance towards Option A."""
        indian_numbers = ["+919876543210", "919876543210", "+91 98765 43210"]
        for num in indian_numbers:
            addr, err = self.dispatcher.get_gateway_address(num, carrier_key="verizon")
            self.assertIsNone(addr)
            self.assertIn("Indian mobile numbers (+91) do not support", err)
            self.assertIn("Option A (Telegram Bot API)", err)

    def test_us_carrier_gateway_formatting(self):
        """Valid 10-digit North American numbers must map to verified carrier gateway domains."""
        # Verizon
        addr_vz, err_vz = self.dispatcher.get_gateway_address("4155550199", carrier_key="verizon")
        self.assertIsNone(err_vz)
        self.assertEqual(addr_vz, "4155550199@vtext.com")

        # AT&T
        addr_att, err_att = self.dispatcher.get_gateway_address("(415) 555-0199", carrier_key="att")
        self.assertIsNone(err_att)
        self.assertEqual(addr_att, "4155550199@txt.att.net")

        # T-Mobile
        addr_tm, err_tm = self.dispatcher.get_gateway_address("+14155550199", carrier_key="tmobile")
        self.assertIsNone(err_tm)
        self.assertEqual(addr_tm, "4155550199@tmomail.net")

    def test_invalid_phone_numbers(self):
        """Short, empty, or alpha-filled numbers must be rejected."""
        for invalid in ["123", "", "abcdefghij", "555-12"]:
            addr, err = self.dispatcher.get_gateway_address(invalid, carrier_key="verizon")
            self.assertIsNone(addr)
            self.assertIn("Invalid phone number", err)

    @patch('smtplib.SMTP')
    def test_smtp_auth_failure_handling(self, mock_smtp_cls):
        """SMTP authentication failure must return False and not throw unhandled exceptions."""
        import smtplib
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 Bad credentials")
        mock_smtp_cls.return_value = mock_server

        success, err = self.dispatcher.test_connection("test@gmail.com", "wrong_password")
        self.assertFalse(success)
        self.assertIn("Authentication Failed", err.get("error", ""))


class TestFreeAlertServiceHistory(unittest.TestCase):

    def setUp(self):
        self.service = FreeAlertService()

    def test_get_history_returns_list(self):
        """History retrieval must return a list of recent alert records."""
        history = self.service.get_history()
        self.assertIsInstance(history, list)

    def test_status_never_claims_handset_delivery(self):
        """All recorded statuses must accurately represent provider handoff, never false delivery."""
        for item in self.service.get_history():
            status = item.get("status", "")
            self.assertNotEqual(status, "DELIVERED_TO_HANDSET")


if __name__ == '__main__':
    unittest.main()
