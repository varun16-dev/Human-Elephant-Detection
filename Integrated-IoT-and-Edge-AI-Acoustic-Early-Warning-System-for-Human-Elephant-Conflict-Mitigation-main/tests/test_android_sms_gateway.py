"""
Tests for Android SIM SMS Gateway Integration (TextBee)
Department of AI & ML, Sri Sairam College of Engineering
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from android_sms_gateway import (
    BilingualMessageBuilder,
    AndroidSmsGatewayManager,
    mask_phone_number,
    mask_api_key,
    get_android_sms_manager
)
from server import app


class TestBilingualMessageBuilder(unittest.TestCase):
    """Verifies bilingual message construction for Tamil Nadu and Karnataka."""

    def test_tamil_nadu_bilingual_message(self):
        """Verifies English + Tamil in the same SMS with dynamic count & location."""
        msg = BilingualMessageBuilder.build_alert_message(
            count=3,
            location="Monitoring Zone 1",
            state="tamil_nadu",
            timestamp_str="24-10-2026, 11:00 PM"
        )
        self.assertIn("🚨 ELEPHANT ALERT!", msg)
        self.assertIn("English: 3 elephants detected at Monitoring Zone 1.", msg)
        self.assertIn("Time: 24-10-2026, 11:00 PM", msg)
        self.assertIn("Please stay safe and inform the forest department.", msg)
        # Tamil content
        self.assertIn("தமிழ்: Monitoring Zone 1-ல் 3 யானைகள் கண்டறியப்பட்டுள்ளன.", msg)
        self.assertIn("பாதுகாப்பாக இருங்கள் மற்றும் வனத்துறைக்குத் தகவல் தெரிவிக்கவும்.", msg)

    def test_karnataka_bilingual_message(self):
        """Verifies English + Kannada in the same SMS with dynamic count & location."""
        msg = BilingualMessageBuilder.build_alert_message(
            count=2,
            location="Monitoring Zone 2",
            state="karnataka",
            timestamp_str="24-10-2026, 11:00 PM"
        )
        self.assertIn("🚨 ELEPHANT ALERT!", msg)
        self.assertIn("English: 2 elephants detected at Monitoring Zone 2.", msg)
        self.assertIn("Time: 24-10-2026, 11:00 PM", msg)
        self.assertIn("Please stay safe and inform the forest department.", msg)
        # Kannada content
        self.assertIn("ಕನ್ನಡ: Monitoring Zone 2ದಲ್ಲಿ 2 ಆನೆಗಳು ಪತ್ತೆಯಾಗಿವೆ.", msg)
        self.assertIn("ಸುರಕ್ಷಿತವಾಗಿರಿ ಮತ್ತು ಅರಣ್ಯ ಇಲಾಖೆಗೆ ಮಾಹಿತಿ ನೀಡಿ.", msg)

    def test_singular_plural_handling(self):
        """Verifies correct noun forms for 1 elephant vs multiple elephants."""
        msg_singular = BilingualMessageBuilder.build_alert_message(1, "Corridor Alpha", "tamil_nadu")
        self.assertIn("1 elephant detected", msg_singular)
        self.assertIn("1 யானை கண்டறியப்பட்டுள்ளன", msg_singular)

        msg_plural = BilingualMessageBuilder.build_alert_message(5, "Corridor Alpha", "karnataka")
        self.assertIn("5 elephants detected", msg_plural)
        self.assertIn("5 ಆನೆಗಳು ಪತ್ತೆಯಾಗಿವೆ", msg_plural)

    def test_invalid_or_zero_count_raises_value_error(self):
        """Verifies rejection of invalid, 0, or negative counts."""
        with self.assertRaises(ValueError):
            BilingualMessageBuilder.build_alert_message(0, "Zone 1", "tamil_nadu")

        with self.assertRaises(ValueError):
            BilingualMessageBuilder.build_alert_message(-2, "Zone 1", "karnataka")

        with self.assertRaises(ValueError):
            BilingualMessageBuilder.build_alert_message("three", "Zone 1", "karnataka")  # type: ignore

    def test_build_test_message(self):
        """Verifies explicit test message generation."""
        tn_test = BilingualMessageBuilder.build_test_message("tamil_nadu", "Hosur Outpost")
        self.assertIn("TEST ALERT", tn_test)
        self.assertIn("Android phone SIM card", tn_test)
        self.assertIn("தமிழ்:", tn_test)

        ka_test = BilingualMessageBuilder.build_test_message("karnataka", "Bannerghatta North")
        self.assertIn("TEST ALERT", ka_test)
        self.assertIn("Android phone SIM card", ka_test)
        self.assertIn("ಕನ್ನಡ:", ka_test)


class TestDeduplicationAndCooldown(unittest.TestCase):
    """Verifies frame deduplication, cooldown policies, and absence lifecycle."""

    def setUp(self):
        self.mgr = AndroidSmsGatewayManager()
        self.mgr.config["cooldown_seconds"] = 10
        self.mgr.config["count_change_policy"] = "always"
        self.mgr.config["absence_reset_seconds"] = 5
        self.mgr.active_event = False
        self.mgr.last_sent_count = 0
        self.mgr.last_sent_time = 0.0

    def test_first_detection_triggers_alert(self):
        """First detection frame initiates active event and permits send."""
        should_send, reason = self.mgr.should_send_alert(3)
        self.assertTrue(should_send)
        self.assertIn("New detection incident", reason)

    def test_duplicate_frame_suppression(self):
        """Consecutive frames with same count within cooldown must be suppressed."""
        # Frame 1: Alert sent
        self.mgr.process_detection = MagicMock(return_value={"status": "ACCEPTED_BY_GATEWAY"})
        self.mgr.active_event = True
        self.mgr.last_sent_count = 3
        import time
        self.mgr.last_sent_time = time.time()

        # Frame 2 (0.1s later, same count): Should be suppressed
        should_send, reason = self.mgr.should_send_alert(3)
        self.assertFalse(should_send)
        self.assertIn("Suppressed duplicate alert", reason)

    def test_count_change_policy_always(self):
        """With policy='always', herd count changing from 3 to 5 triggers alert immediately."""
        self.mgr.config["count_change_policy"] = "always"
        self.mgr.active_event = True
        self.mgr.last_sent_count = 3
        import time
        self.mgr.last_sent_time = time.time()

        should_send, reason = self.mgr.should_send_alert(5)
        self.assertTrue(should_send)
        self.assertIn("Herd count changed from 3 to 5", reason)

    def test_count_change_policy_increase_only(self):
        """With policy='increase_only', decrease (5 -> 3) is suppressed, increase (3 -> 5) is sent."""
        self.mgr.config["count_change_policy"] = "increase_only"
        self.mgr.active_event = True
        self.mgr.last_sent_count = 5
        import time
        self.mgr.last_sent_time = time.time()

        # Decrease to 3 -> suppressed
        should_send, reason = self.mgr.should_send_alert(3)
        self.assertFalse(should_send)
        self.assertIn("Count decreased", reason)

        # Increase to 7 -> permitted
        self.mgr.last_sent_count = 3
        should_send, reason = self.mgr.should_send_alert(7)
        self.assertTrue(should_send)
        self.assertIn("Herd count increased", reason)

    def test_absence_interval_resets_lifecycle(self):
        """Zero counts past absence interval reset the active incident."""
        self.mgr.active_event = True
        self.mgr.last_sent_count = 4
        import time
        self.mgr.last_detection_seen_time = time.time() - 10  # 10s ago (> 5s threshold)

        should_send, reason = self.mgr.should_send_alert(0)
        self.assertFalse(should_send)
        self.assertFalse(self.mgr.active_event)
        self.assertEqual(self.mgr.last_sent_count, 0)


class TestSecurityAndMasking(unittest.TestCase):
    """Verifies privacy masking for phone numbers and API keys."""

    def test_phone_masking(self):
        self.assertEqual(mask_phone_number("+919876543210"), "+91 98*** ***10")
        self.assertEqual(mask_phone_number("9876543210"), "98*** ***10")
        self.assertEqual(mask_phone_number(""), "Not configured")

    def test_api_key_masking(self):
        self.assertEqual(mask_api_key("tb_live_secret123456789"), "tb_l••••••••6789")
        self.assertEqual(mask_api_key(""), "")

    def test_get_safe_config_never_exposes_raw_key(self):
        mgr = AndroidSmsGatewayManager()
        mgr.config["api_key"] = "tb_secret_key_123456789"
        safe = mgr.get_safe_config()
        self.assertNotIn("api_key", safe)
        self.assertTrue(safe["has_api_key"])
        self.assertTrue(safe["api_key_masked"].startswith("tb_s••••"))


class TestServerSmsEndpoints(unittest.TestCase):
    """Verifies Flask REST API endpoints for Android SMS Gateway."""

    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    def test_api_sms_status(self):
        """GET /api/sms/status returns 200 with sanitized config."""
        res = self.client.get('/api/sms/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("state", data)
        self.assertIn("recipient_masked", data)
        self.assertIn("free_tier_limits", data)

    def test_api_sms_config_update(self):
        """POST /api/sms/config updates monitoring state and location."""
        res = self.client.post('/api/sms/config', json={
            "state": "tamil_nadu",
            "location_name": "Mudumalai Corridor Zone 4",
            "cooldown_seconds": 180,
            "count_change_policy": "increase_only"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["config"]["state"], "tamil_nadu")
        self.assertEqual(data["config"]["location_name"], "Mudumalai Corridor Zone 4")
        self.assertEqual(data["config"]["cooldown_seconds"], 180)

    def test_api_sms_preview_message(self):
        """POST /api/sms/preview-message generates dynamic bilingual preview."""
        res = self.client.post('/api/sms/preview-message', json={
            "elephant_count": 4,
            "location": "Valparai Sector B",
            "state": "tamil_nadu"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("English: 4 elephants detected at Valparai Sector B", data["message"])
        self.assertIn("தமிழ்: Valparai Sector B-ல் 4 யானைகள்", data["message"])

    def test_api_sms_preview_rejects_zero_or_negative(self):
        """Rejects count <= 0 with 400 Bad Request."""
        res = self.client.post('/api/sms/preview-message', json={
            "elephant_count": 0,
            "location": "Zone 1"
        })
        self.assertEqual(res.status_code, 400)

    @patch('requests.get')
    def test_api_sms_validate_connection(self, mock_get):
        """POST /api/sms/validate contacts TextBee gateway."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{"id": "device_123", "model": "Pixel 7 Pro", "battery": 92}]
        }
        mock_get.return_value = mock_resp

        mgr = get_android_sms_manager()
        mgr.config["api_key"] = "test_key_123"

        res = self.client.post('/api/sms/validate')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["status"], "CONNECTED")
        self.assertEqual(data["device_count"], 1)

    def test_api_sms_send_test_requires_explicit_confirmation(self):
        """POST /api/sms/send-test requires confirmed=True."""
        res = self.client.post('/api/sms/send-test', json={
            "recipient": "+919876543210",
            "confirmed": False
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])

    @patch('requests.post')
    def test_api_sms_send_test_confirmed_success(self, mock_post):
        """When confirmed=True and provider accepts, returns 200 with record."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "data": {"id": "msg_tb_999", "status": "QUEUED"}
        }
        mock_post.return_value = mock_resp

        mgr = get_android_sms_manager()
        mgr.config["api_key"] = "tb_valid_key"
        mgr.config["daily_sent_count"] = 0

        res = self.client.post('/api/sms/send-test', json={
            "recipient": "+919876543210",
            "confirmed": True
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["record"]["status"], "ACCEPTED_BY_GATEWAY")

    def test_api_sms_webhook_delivery_report(self):
        """POST /api/sms/webhook receives delivery callback and updates status."""
        mgr = get_android_sms_manager()
        mgr.history.append({
            "timestamp": "2026-10-24 11:00:00",
            "meta": {"gateway_message_id": "msg_webhook_test"}
        })

        res = self.client.post('/api/sms/webhook', json={
            "messageId": "msg_webhook_test",
            "status": "MESSAGE_DELIVERED"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["event"], "MESSAGE_DELIVERED")

        # Check record updated
        matching_rec = next((r for r in mgr.history if (r.get("meta") or {}).get("gateway_message_id") == "msg_webhook_test"), None)
        self.assertIsNotNone(matching_rec)
        self.assertEqual(matching_rec.get("delivery_status"), "MESSAGE_DELIVERED")


if __name__ == '__main__':
    unittest.main()
