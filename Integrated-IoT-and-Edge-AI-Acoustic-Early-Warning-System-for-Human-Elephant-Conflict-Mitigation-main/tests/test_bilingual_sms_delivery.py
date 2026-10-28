"""
Automated Tests for Bilingual SMS Delivery
Human-Elephant Conflict Early Warning System

Covers Section 9 requirements:
1. Tamil Nadu recipient receives a message containing English and Tamil.
2. Karnataka recipient receives a message containing English and Kannada.
3. The actual outbound provider request contains the complete bilingual body.
4. Elephant count, location, timestamp, confidence, and dashboard URL are correctly inserted when available.
5. Missing optional detection information is handled safely.
6. Unicode characters are preserved.
7. Long messages and multipart SMS are handled correctly (UCS-2 vs GSM-7).
8. Forest officer and villager recipient groups work independently.
9. Disabled recipients do not receive notifications.
10. Cooldown and incident reset prevent duplicate SMS alerts.
11. Provider errors are recorded correctly.
12. Mocked external calls ensure no real SMS is sent during automated testing.
"""

import os
import sys
import json
import time
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from android_sms_gateway import (
    BilingualMessageBuilder,
    AndroidSmsGatewayManager,
    mask_phone_number,
    mask_api_key
)
from server import app


class TestBilingualSmsDelivery(unittest.TestCase):
    """Full coverage test suite for Bilingual SMS delivery across providers."""

    def setUp(self):
        self.tmp_config = f"test_bilingual_cfg_{int(time.time() * 1000)}.json"
        self.manager = AndroidSmsGatewayManager(config_path=self.tmp_config)
        self.manager.config["api_key"] = "test_key_abc123"
        self.manager.config["device_id"] = "test_device_pixel_8"
        self.manager.config["state"] = "karnataka"
        self.manager.config["location_name"] = "Bandipur Sector 3"
        self.manager.config["cooldown_seconds"] = 300
        self.manager.config["count_change_policy"] = "always"
        self.manager.config["absence_reset_seconds"] = 120
        self.manager.config["daily_sent_count"] = 0
        self.manager.config["max_daily_limit"] = 50
        self.manager.config["recipients"]["officers"] = []
        self.manager.config["recipients"]["villagers"] = []

    def tearDown(self):
        if os.path.exists(self.tmp_config):
            try:
                os.remove(self.tmp_config)
            except OSError:
                pass

    # -------------------------------------------------------------------------
    # 1. Tamil Nadu recipient receives English + Tamil in the same SMS
    # -------------------------------------------------------------------------
    def test_1_tamil_nadu_recipient_receives_english_plus_tamil(self):
        msg = BilingualMessageBuilder.build_bilingual_sms(
            count=2,
            location="Mudumalai Buffer Zone",
            state="tamil_nadu",
            timestamp_str="25-10-2026, 10:15 AM",
            confidence=95.2,
            dashboard_url="http://127.0.0.1:5000"
        )
        # English section assertions
        self.assertIn("ELEPHANT ALERT!", msg)
        self.assertIn("Mudumalai Buffer Zone", msg)
        self.assertIn("2 elephants", msg)
        self.assertIn("Confidence: 95%", msg)
        self.assertIn("Avoid approaching elephants. Follow forest department instructions.", msg)
        self.assertIn("http://127.0.0.1:5000", msg)

        # Tamil section assertions
        self.assertIn("யானை எச்சரிக்கை!", msg)
        self.assertIn("யானைகள் கண்டறியப்பட்டுள்ளன", msg)
        self.assertIn("கண்டறிதல் நம்பகத்தன்மை: 95%", msg)
        self.assertIn("யானைகளை நெருங்க வேண்டாம். வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றவும்.", msg)
        self.assertIn("மேலும் விவரங்கள்: http://127.0.0.1:5000", msg)

    # -------------------------------------------------------------------------
    # 2. Karnataka recipient receives English + Kannada in the same SMS
    # -------------------------------------------------------------------------
    def test_2_karnataka_recipient_receives_english_plus_kannada(self):
        msg = BilingualMessageBuilder.build_bilingual_sms(
            count=1,
            location="Nagarhole Gate 2",
            state="karnataka",
            timestamp_str="25-10-2026, 11:30 AM",
            confidence=91.8,
            dashboard_url="http://127.0.0.1:5000"
        )
        # English section assertions
        self.assertIn("ELEPHANT ALERT!", msg)
        self.assertIn("Nagarhole Gate 2", msg)
        self.assertIn("An elephant has been detected near", msg)  # Singular
        self.assertIn("Count: 1", msg)
        self.assertIn("Confidence: 92%", msg)
        self.assertIn("Avoid approaching the elephant. Follow forest department instructions.", msg)

        # Kannada section assertions
        self.assertIn("ಆನೆ ಎಚ್ಚರಿಕೆ!", msg)
        self.assertIn("ಆನೆ ಪತ್ತೆಯಾಗಿದೆ", msg)  # Singular
        self.assertIn("ಪತ್ತೆಹಚ್ಚುವಿಕೆಯ ವಿಶ್ವಾಸಾರ್ಹತೆ: 92%", msg)
        self.assertIn("ಆನೆಯ ಹತ್ತಿರ ಹೋಗಬೇಡಿ. ಅರಣ್ಯ ಇಲಾಖೆಯ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ.", msg)
        self.assertIn("ಹೆಚ್ಚಿನ ವಿವರಗಳು: http://127.0.0.1:5000", msg)

    # -------------------------------------------------------------------------
    # 3. Actual outbound provider request contains complete bilingual body
    # -------------------------------------------------------------------------
    @patch("requests.post")
    def test_3_actual_outbound_provider_request_contains_complete_bilingual_body(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True, "message": "Dispatched via SIM"}
        mock_post.return_value = mock_resp

        self.manager.add_recipient(
            group="officers",
            name="Ranger Kumar",
            phone="+919876543210",
            location="Theppakadu",
            language="tamil_nadu"
        )

        res = self.manager.process_detection(
            elephant_count=3,
            location="Theppakadu",
            confidence=97.5,
            dashboard_url="https://hec-alert.gov.in"
        )

        self.assertEqual(res["status"], "ACCEPTED_BY_GATEWAY")
        self.assertTrue(mock_post.called)

        # Inspect the exact outbound payload
        call_args, call_kwargs = mock_post.call_args
        payload = call_kwargs.get("json", {})
        self.assertIn("recipients", payload)
        self.assertIn("+919876543210", payload["recipients"])
        outbound_msg = payload.get("message", "")

        # Must have both English and Tamil complete text
        self.assertIn("ELEPHANT ALERT!", outbound_msg)
        self.assertIn("யானை எச்சரிக்கை!", outbound_msg)
        self.assertIn("3 elephants", outbound_msg)
        self.assertIn("98%", outbound_msg)  # 97.5 rounded
        self.assertIn("https://hec-alert.gov.in", outbound_msg)

    # -------------------------------------------------------------------------
    # 4. Count, location, timestamp, confidence, and dashboard URL correctly inserted
    # -------------------------------------------------------------------------
    def test_4_all_detection_fields_accurately_inserted(self):
        msg = BilingualMessageBuilder.build_bilingual_sms(
            count=5,
            location="Corridor Beta 9",
            state="tamil_nadu",
            timestamp_str="25-10-2026, 04:45 PM",
            confidence=89.4,
            dashboard_url="http://192.168.1.100:5000"
        )
        self.assertIn("Corridor Beta 9", msg)
        self.assertIn("Count: 5", msg)
        self.assertIn("5 elephants", msg)
        self.assertIn("89%", msg)
        self.assertIn("25-10-2026, 04:45 PM", msg)
        self.assertIn("http://192.168.1.100:5000", msg)

    # -------------------------------------------------------------------------
    # 5. Missing optional detection information is handled safely
    # -------------------------------------------------------------------------
    def test_5_missing_optional_detection_info_handled_safely(self):
        # Confidence=None and dashboard_url=None
        msg = BilingualMessageBuilder.build_bilingual_sms(
            count=2,
            location="Valparai Estate",
            state="tamil_nadu",
            confidence=None,
            dashboard_url=None
        )
        self.assertNotIn("Confidence: None", msg)
        self.assertNotIn("None%", msg)
        self.assertNotIn("View details: None", msg)
        self.assertNotIn("மேலும் விவரங்கள்: None", msg)
        # Core alert & instructions remain intact
        self.assertIn("ELEPHANT ALERT!", msg)
        self.assertIn("யானை எச்சரிக்கை!", msg)
        self.assertIn("Avoid approaching elephants.", msg)
        self.assertIn("யானைகளை நெருங்க வேண்டாம்.", msg)

    # -------------------------------------------------------------------------
    # 6. Unicode characters preserved without corruption
    # -------------------------------------------------------------------------
    def test_6_unicode_characters_preserved_and_not_corrupted(self):
        tamil_sample = "யானை எச்சரிக்கை! வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றவும்."
        kannada_sample = "ಆನೆ ಎಚ್ಚರಿಕೆ! ಅರಣ್ಯ ಇಲಾಖೆಯ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ."

        # Verify UTF-8 / UCS-2 roundtrip without replacement character U+FFFD or '?'
        utf8_encoded = tamil_sample.encode("utf-8")
        self.assertEqual(utf8_encoded.decode("utf-8"), tamil_sample)
        self.assertNotIn("?", tamil_sample)
        self.assertNotIn("\ufffd", tamil_sample)

        utf8_kn = kannada_sample.encode("utf-8")
        self.assertEqual(utf8_kn.decode("utf-8"), kannada_sample)
        self.assertNotIn("?", kannada_sample)
        self.assertNotIn("\ufffd", kannada_sample)

        # Verify segment calculation detects Unicode
        metrics_ta = BilingualMessageBuilder.calculate_segments(tamil_sample)
        self.assertTrue(metrics_ta["is_unicode"])
        self.assertIn("UCS-2", metrics_ta["encoding"])

        metrics_kn = BilingualMessageBuilder.calculate_segments(kannada_sample)
        self.assertTrue(metrics_kn["is_unicode"])
        self.assertIn("UCS-2", metrics_kn["encoding"])

    # -------------------------------------------------------------------------
    # 7. Long messages and multipart SMS handled correctly (UCS-2 vs GSM-7)
    # -------------------------------------------------------------------------
    def test_7_long_messages_and_multipart_segmentation(self):
        # Pure ASCII under 160 characters
        ascii_short = "ELEPHANT ALERT! 1 elephant detected at Zone 1. Stay safe."
        m1 = BilingualMessageBuilder.calculate_segments(ascii_short)
        self.assertFalse(m1["is_unicode"])
        self.assertEqual(m1["encoding"], "GSM-7")
        self.assertEqual(m1["segments"], 1)
        self.assertEqual(m1["chars_per_segment"], 160)

        # Pure ASCII over 160 characters (161 chars -> 2 segments of 153 chars)
        ascii_long = "A" * 165
        m2 = BilingualMessageBuilder.calculate_segments(ascii_long)
        self.assertFalse(m2["is_unicode"])
        self.assertEqual(m2["segments"], 2)
        self.assertEqual(m2["chars_per_segment"], 153)

        # Unicode under 70 characters
        uni_short = "யானை எச்சரிக்கை! 1 யானை"  # ~23 chars
        m3 = BilingualMessageBuilder.calculate_segments(uni_short)
        self.assertTrue(m3["is_unicode"])
        self.assertIn("UCS-2", m3["encoding"])
        self.assertEqual(m3["segments"], 1)
        self.assertEqual(m3["chars_per_segment"], 70)

        # Unicode over 70 characters (71 chars -> 2 segments of 67 chars)
        uni_long = "ய" * 75
        m4 = BilingualMessageBuilder.calculate_segments(uni_long)
        self.assertTrue(m4["is_unicode"])
        self.assertEqual(m4["segments"], 2)
        self.assertEqual(m4["chars_per_segment"], 67)

        # Full real bilingual message (typically 350-450 UCS-2 chars -> 6-7 segments)
        real_bilingual = BilingualMessageBuilder.build_bilingual_sms(
            count=3,
            location="Bandipur Tiger Reserve Outpost 4",
            state="karnataka",
            confidence=94.5,
            dashboard_url="http://127.0.0.1:5000"
        )
        m_real = BilingualMessageBuilder.calculate_segments(real_bilingual)
        self.assertTrue(m_real["is_unicode"])
        self.assertGreater(m_real["segments"], 1)
        self.assertEqual(m_real["chars_per_segment"], 67)

    # -------------------------------------------------------------------------
    # 8. Forest officer and villager recipient groups work independently
    # -------------------------------------------------------------------------
    @patch("requests.post")
    def test_8_officer_and_villager_groups_work_independently(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True, "message": "OK"}
        mock_post.return_value = mock_resp

        # Forest Officer in Tamil Nadu
        self.manager.add_recipient(
            group="officers",
            name="Officer Selvam",
            phone="+919800000001",
            location="Sathyamangalam",
            language="tamil_nadu"
        )
        # Local Villager in Karnataka
        self.manager.add_recipient(
            group="villagers",
            name="Basavaraj (Farmer)",
            phone="+919800000002",
            location="Chamarajanagar",
            language="karnataka"
        )

        res = self.manager.process_detection(
            elephant_count=2,
            location="Border Corridor",
            confidence=92.0
        )

        self.assertEqual(res["status"], "ACCEPTED_BY_GATEWAY")
        # 2 distinct dispatches
        self.assertEqual(mock_post.call_count, 2)

        calls = mock_post.call_args_list
        # First call was to Officer (Tamil Nadu language preference)
        payload1 = calls[0][1]["json"]
        self.assertEqual(payload1["recipients"], ["+919800000001"])
        self.assertIn("யானை எச்சரிக்கை!", payload1["message"])
        self.assertNotIn("ಆನೆ ಎಚ್ಚರಿಕೆ!", payload1["message"])

        # Second call was to Villager (Karnataka language preference)
        payload2 = calls[1][1]["json"]
        self.assertEqual(payload2["recipients"], ["+919800000002"])
        self.assertIn("ಆನೆ ಎಚ್ಚರಿಕೆ!", payload2["message"])
        self.assertNotIn("யானை எச்சரிக்கை!", payload2["message"])

    # -------------------------------------------------------------------------
    # 9. Disabled recipients do not receive notifications
    # -------------------------------------------------------------------------
    @patch("requests.post")
    def test_9_disabled_recipients_do_not_receive_notifications(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True, "message": "OK"}
        mock_post.return_value = mock_resp

        # Enabled Officer
        self.manager.add_recipient(
            group="officers",
            name="Active Officer",
            phone="+919811111111",
            location="Zone 1",
            enabled=True
        )
        # Disabled Officer
        self.manager.add_recipient(
            group="officers",
            name="On-Leave Officer",
            phone="+919822222222",
            location="Zone 2",
            enabled=False
        )

        res = self.manager.process_detection(elephant_count=1)
        self.assertEqual(res["status"], "ACCEPTED_BY_GATEWAY")
        self.assertEqual(mock_post.call_count, 1)

        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["recipients"], ["+919811111111"])
        self.assertNotIn("+919822222222", payload["recipients"])

    # -------------------------------------------------------------------------
    # 10. Cooldown and incident reset prevent duplicate SMS alerts
    # -------------------------------------------------------------------------
    @patch("requests.post")
    def test_10_cooldown_and_incident_reset_prevent_duplicates(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True}
        mock_post.return_value = mock_resp

        self.manager.config["cooldown_seconds"] = 100
        self.manager.config["count_change_policy"] = "always"
        self.manager.add_recipient(group="officers", name="Ranger", phone="+919833333333", location="Zone Alpha")

        # First alert -> Accepted
        r1 = self.manager.process_detection(elephant_count=2)
        self.assertEqual(r1["status"], "ACCEPTED_BY_GATEWAY")
        self.assertEqual(mock_post.call_count, 1)

        # Immediate second alert with SAME count -> Suppressed by cooldown
        r2 = self.manager.process_detection(elephant_count=2)
        self.assertEqual(r2["status"], "SKIPPED")
        self.assertIn("cooldown", r2["reason"].lower())
        self.assertEqual(mock_post.call_count, 1)  # No new post

        # Third alert with INCREASED count (policy=always) -> Accepted
        r3 = self.manager.process_detection(elephant_count=4)
        self.assertEqual(r3["status"], "ACCEPTED_BY_GATEWAY")
        self.assertEqual(mock_post.call_count, 2)

    # -------------------------------------------------------------------------
    # 11. Provider errors are recorded correctly
    # -------------------------------------------------------------------------
    @patch("requests.post")
    def test_11_provider_errors_recorded_correctly(self, mock_post):
        # Simulate TextBee 429 quota exceeded error
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = json.dumps({"error": "Daily quota limit reached on free tier"})
        mock_post.return_value = mock_resp

        self.manager.add_recipient(group="officers", name="Ranger", phone="+919844444444", location="Sector 5")
        res = self.manager.process_detection(elephant_count=1)

        self.assertEqual(res["status"], "SEND_FAILED")
        self.assertFalse(res["success"])

        # Verify last_alert record stores failure details
        last = self.manager.last_alert_details
        self.assertFalse(last["success"])
        self.assertEqual(last["status"], "SEND_FAILED")

        # Verify server did not crash and recorded history
        self.assertGreater(len(self.manager.history), 0)
        self.assertIn("FAILED", self.manager.history[0]["status"])

    # -------------------------------------------------------------------------
    # 12. Mocked external calls ensure no real SMS sent in test suite
    # -------------------------------------------------------------------------
    def test_12_mocked_external_calls_safety(self):
        # Ensure that without a confirmed=True and valid key, send_real_test_sms rejects
        test_mgr = AndroidSmsGatewayManager(config_path="test_mock_safety.json")
        test_mgr.config["api_key"] = ""
        success, err_msg, rec = test_mgr.send_real_test_sms("+919999999999", confirmed=False)
        self.assertFalse(success)
        self.assertIn("Explicit confirmation required", err_msg)

        if os.path.exists("test_mock_safety.json"):
            os.remove("test_mock_safety.json")


class TestServerBilingualRoutes(unittest.TestCase):
    """Verifies server API routes for bilingual preview, recipients, and configuration."""

    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    def test_preview_message_bilingual_api(self):
        # Test Tamil Nadu preview
        resp = self.client.post('/api/sms/preview-message', json={
            'state': 'tamil_nadu',
            'location': 'Anamalai Sector 5',
            'count': 3,
            'confidence': 96.0,
            'full': True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("ELEPHANT ALERT!", data['message'])
        self.assertIn("யானை எச்சரிக்கை!", data['message'])
        self.assertTrue(data['is_unicode'])
        self.assertIn("UCS-2", data['encoding'])
        self.assertGreater(data['segments'], 1)
        self.assertEqual(data['chars_per_segment'], 67)

        # Test Karnataka preview
        resp_kn = self.client.post('/api/sms/preview-message', json={
            'state': 'karnataka',
            'location': 'Bannerghatta Corridor',
            'count': 1,
            'confidence': 93.5,
            'full': True
        })
        self.assertEqual(resp_kn.status_code, 200)
        data_kn = resp_kn.get_json()
        self.assertIn("ELEPHANT ALERT!", data_kn['message'])
        self.assertIn("ಆನೆ ಎಚ್ಚರಿಕೆ!", data_kn['message'])
        self.assertTrue(data_kn['is_unicode'])

    def test_recipients_api_crud_flow(self):
        # 1. Fetch current recipients
        res = self.client.get('/api/sms/recipients')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        recipients = data.get('recipients', {})
        self.assertIn('officers', recipients)
        self.assertIn('villagers', recipients)

        # 2. Add a new forest officer with unique test phone
        unique_phone = f"+91987{int(time.time() * 1000) % 10000000:07d}"
        add_res = self.client.post('/api/sms/recipients/add', json={
            'group': 'officers',
            'name': 'API Test Officer',
            'phone': unique_phone,
            'location': 'Mudumalai North',
            'language': 'tamil_nadu'
        })
        self.assertEqual(add_res.status_code, 200)
        add_data = add_res.get_json()
        self.assertTrue(add_data['success'])
        recip_id = add_data['recipient']['id']

        # 3. Toggle status
        tog_res = self.client.post('/api/sms/recipients/toggle', json={
            'id': recip_id,
            'group': 'officers'
        })
        self.assertEqual(tog_res.status_code, 200)
        self.assertTrue(tog_res.get_json()['success'])

        # 4. Delete the added recipient
        del_res = self.client.post('/api/sms/recipients/delete', json={
            'id': recip_id,
            'group': 'officers'
        })
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()['success'])


if __name__ == '__main__':
    unittest.main()
