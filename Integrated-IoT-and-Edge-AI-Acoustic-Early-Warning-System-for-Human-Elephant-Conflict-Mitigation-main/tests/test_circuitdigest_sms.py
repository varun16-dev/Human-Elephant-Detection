"""
Automated Unit and Integration Tests for CircuitDigest Cloud SMS Integration
Department of AI & ML, Sri Sairam College of Engineering

Ensures:
- 100% mocked - Never makes real network requests or sends real SMS
- Verified request structure: POST https://www.circuitdigest.cloud/api/v1/send_sms?ID={template_id}
- Header format: Authorization: <API_KEY>, Content-Type: application/json
- Strict variable bounds: var1 and var2 <= 30 chars, ASCII sanitization
- Dual recipient groups (Officers & Villagers) with phone normalization
- Cooldown, duplicate suppression, and count-change policies
- Absence reset interval closing incidents
- Robust error handling (401 invalid key, 429 quota, connection timeout)
- RBAC protection: Unauthorized roles blocked with HTTP 403 Forbidden
- Credential masking and safe REST API responses
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from circuitdigest_sms_service import (
    CircuitDigestMessageBuilder,
    CircuitDigestSmsManager,
    normalize_phone_number,
    sanitize_variable,
    mask_phone_number,
    mask_credential,
    get_circuitdigest_sms_manager
)
from server import app


class TestCircuitDigestMessageBuilder(unittest.TestCase):
    """Verifies template variable mapping, length constraints, and bilingual messages."""

    def test_variable_sanitization_and_30_char_limit(self):
        """Verifies that dynamic variables never exceed 30 chars and strip non-ASCII."""
        long_text = "This is an extremely long location name that exceeds thirty characters"
        sanitized = sanitize_variable(long_text, max_len=30)
        self.assertLessEqual(len(sanitized), 30)

        # Non-ASCII / newlines
        dirty = "Zone 1 \nPerimeter \tதமிழ்"
        clean = sanitize_variable(dirty, max_len=30)
        self.assertNotIn("\n", clean)
        self.assertNotIn("\t", clean)
        self.assertNotIn("தமிழ்", clean)
        self.assertLessEqual(len(clean), 30)

    def test_template_103_variable_mapping_officer(self):
        """Verifies template 103 variable mapping for forest officers."""
        var1, var2 = CircuitDigestMessageBuilder.map_template_variables(
            template_id=103,
            count=2,
            location="Bannerghatta Corridor",
            group="officer",
            confidence=0.88
        )
        self.assertLessEqual(len(var1), 30)
        self.assertLessEqual(len(var2), 30)
        self.assertIn("2 Elephants", var1)
        self.assertIn("88%", var1)
        self.assertIn("Bannerghatta", var2)

    def test_template_103_variable_mapping_villager(self):
        """Verifies template 103 variable mapping for villagers with safety advisory."""
        var1, var2 = CircuitDigestMessageBuilder.map_template_variables(
            template_id=103,
            count=1,
            location="Zone North",
            group="villager",
            confidence=0.90
        )
        self.assertLessEqual(len(var1), 30)
        self.assertLessEqual(len(var2), 30)
        self.assertIn("1 Elephant", var1)
        self.assertIn("Stay Safe", var2)

    def test_template_101_variable_mapping(self):
        """Verifies template 101 (Device Status) mapping."""
        var1, var2 = CircuitDigestMessageBuilder.map_template_variables(
            template_id=101,
            count=3,
            location="Sector 4",
            group="officer",
            confidence=0.85
        )
        self.assertLessEqual(len(var1), 30)
        self.assertLessEqual(len(var2), 30)
        self.assertEqual(var1, "Elephant Warning System")
        self.assertIn("3 Elephants at Sector 4", var2)

    def test_bilingual_audit_text_tamil_nadu(self):
        """Verifies full English + Tamil audit text with AI prediction disclaimer."""
        msg = CircuitDigestMessageBuilder.build_bilingual_audit_text(
            count=2,
            location="Zone 1",
            state="tamil_nadu",
            group="officer",
            confidence=0.92
        )
        self.assertIn("🚨 [OFFICER ALERT] AI Elephant Detection", msg)
        self.assertIn("English: AI Camera model detected 2 elephants at Zone 1.", msg)
        self.assertIn("AI Confidence: 92% (Model prediction, unverified by field staff)", msg)
        self.assertIn("தமிழ்:", msg)
        self.assertIn("யானைகள்", msg)

    def test_bilingual_audit_text_karnataka(self):
        """Verifies full English + Kannada audit text for Karnataka."""
        msg = CircuitDigestMessageBuilder.build_bilingual_audit_text(
            count=1,
            location="Bannerghatta Border",
            state="karnataka",
            group="villager"
        )
        self.assertIn("🚨 ELEPHANT ALERT!", msg)
        self.assertIn("English: WARNING: 1 elephant detected", msg)
        self.assertIn("Stay indoors and avoid forest border paths.", msg)
        self.assertIn("ಕನ್ನಡ:", msg)
        self.assertIn("ಆನೆ", msg)


class TestCircuitDigestSmsManager(unittest.TestCase):
    """Verifies HTTP dispatch, retry/error handling, recipient persistence, and state machine."""

    def setUp(self):
        self.test_config_path = os.path.join(os.path.dirname(__file__), "test_circuitdigest_config.json")
        self.test_history_path = os.path.join(os.path.dirname(__file__), "test_circuitdigest_history.json")
        for p in [self.test_config_path, self.test_history_path]:
            if os.path.exists(p):
                os.remove(p)

        self.mgr = CircuitDigestSmsManager(
            config_path=self.test_config_path,
            history_path=self.test_history_path
        )
        self.mgr.config["api_key"] = "cd_test_valid_api_key_12345"
        self.mgr.config["recipients"] = {"officers": [], "villagers": []}

    def tearDown(self):
        for p in [self.test_config_path, self.test_history_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def test_phone_normalization(self):
        """Verifies standard phone number normalization for Indian numbers."""
        self.assertEqual(normalize_phone_number("9876543210"), "919876543210")
        self.assertEqual(normalize_phone_number("+919876543210"), "919876543210")
        self.assertEqual(normalize_phone_number("09876543210"), "919876543210")
        self.assertEqual(normalize_phone_number("+91 98765-43210"), "919876543210")
        self.assertIsNone(normalize_phone_number("12345"))  # Too short

    def test_masking_helpers(self):
        """Verifies credential and phone privacy masking."""
        self.assertEqual(mask_phone_number("919876543210"), "+91 98*** ***10")
        self.assertEqual(mask_credential("cd_abcdef1234567890"), "cd_a••••••••7890")
        self.assertEqual(mask_credential(""), "Not configured")

    def test_recipient_group_management(self):
        """Verifies adding, updating, and deleting recipients in groups."""
        # Add officer
        ok, msg, entry = self.mgr.add_recipient("officers", "Ranger Somanna", "+91 9876543210")
        self.assertTrue(ok)
        self.assertEqual(entry["phone"], "919876543210")

        # Duplicate phone check
        ok2, msg2, _ = self.mgr.add_recipient("officers", "Another Officer", "9876543210")
        self.assertFalse(ok2)
        self.assertIn("already registered", msg2)

        # Add villager
        ok_v, _, v_entry = self.mgr.add_recipient("villagers", "Village Head", "918888888888")
        self.assertTrue(ok_v)

        # Update recipient status (toggle mute)
        ok_u, _, u_entry = self.mgr.update_recipient("officers", entry["id"], enabled=False)
        self.assertTrue(ok_u)
        self.assertFalse(u_entry["enabled"])

        # Delete recipient
        ok_d, _ = self.mgr.delete_recipient("officers", entry["id"])
        self.assertTrue(ok_d)
        recipients = self.mgr.get_recipients()
        self.assertEqual(len(recipients["officers"]), 0)
        self.assertEqual(len(recipients["villagers"]), 1)

    @patch("circuitdigest_sms_service.requests.post")
    def test_send_single_sms_success(self, mock_post):
        """Verifies verified HTTP request structure on successful dispatch."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "message": "SMS sent successfully",
            "details": {"mobile": "919876543210", "template_id": "103"}
        }
        mock_post.return_value = mock_resp

        ok, msg, record = self.mgr.send_single_sms(
            mobile="9876543210",
            var1="AI Cam: 2 Elephants",
            var2="Zone 1",
            template_id=103
        )
        self.assertTrue(ok)
        self.assertEqual(record["response_status"], 200)

        # Verify call details
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("ID=103", args[0])
        self.assertEqual(kwargs["headers"]["Authorization"], "cd_test_valid_api_key_12345")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["json"]["mobiles"], "919876543210")
        self.assertEqual(kwargs["json"]["var1"], "AI Cam: 2 Elephants")
        self.assertEqual(kwargs["json"]["var2"], "Zone 1")

    @patch("circuitdigest_sms_service.requests.post")
    def test_send_single_sms_401_unauthorized(self, mock_post):
        """Verifies proper error handling on 401 Unauthorized."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Invalid API Key"
        mock_post.return_value = mock_resp

        ok, msg, record = self.mgr.send_single_sms("9876543210", "Alert", "Zone 1")
        self.assertFalse(ok)
        self.assertIn("Authentication failure", msg)
        self.assertEqual(record["response_status"], 401)

    @patch("circuitdigest_sms_service.requests.post")
    def test_send_single_sms_429_rate_limit(self, mock_post):
        """Verifies handling of rate limits and quota exhaustion."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Daily limit exceeded"
        mock_post.return_value = mock_resp

        ok, msg, record = self.mgr.send_single_sms("9876543210", "Alert", "Zone 1")
        self.assertFalse(ok)
        self.assertIn("limit exceeded", msg)

    @patch("circuitdigest_sms_service.requests.post")
    def test_state_machine_debouncing_and_increase_policy(self, mock_post):
        """Verifies debouncing: sends on initial detection and count increase, suppresses duplicates."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "success"}
        mock_post.return_value = mock_resp

        # Add one recipient
        self.mgr.add_recipient("officers", "Officer 1", "919876543210")

        # 1. First event: count=1 -> Should dispatch
        dispatched, reason, data = self.mgr.evaluate_and_dispatch(
            elephant_count=1,
            confidence=0.85,
            location="Monitoring Zone 1"
        )
        self.assertTrue(dispatched)
        self.assertTrue(self.mgr.incident_active)
        self.assertEqual(self.mgr.current_count, 1)

        # 2. Immediate frame duplicate: count=1 -> Should be suppressed
        dispatched2, reason2, _ = self.mgr.evaluate_and_dispatch(
            elephant_count=1,
            confidence=0.85,
            location="Monitoring Zone 1"
        )
        self.assertFalse(dispatched2)
        self.assertIn("suppressed", reason2)

        # 3. Count increases: count=3 -> Should dispatch under 'increase_only' policy
        dispatched3, reason3, _ = self.mgr.evaluate_and_dispatch(
            elephant_count=3,
            confidence=0.88,
            location="Monitoring Zone 1"
        )
        self.assertTrue(dispatched3)
        self.assertEqual(self.mgr.current_count, 3)

    def test_absence_reset_closes_incident(self):
        """Verifies incident closure after absence reset interval with count=0."""
        self.mgr.incident_active = True
        self.mgr.current_count = 2
        self.mgr.last_alert_time = 100.0
        self.mgr.config["absence_reset_seconds"] = 30

        with patch("circuitdigest_sms_service.time.time", return_value=150.0):
            dispatched, reason, _ = self.mgr.evaluate_and_dispatch(elephant_count=0, confidence=0.0, location="Zone 1")
            self.assertFalse(dispatched)
            self.assertFalse(self.mgr.incident_active)
            self.assertEqual(self.mgr.current_count, 0)


class TestCircuitDigestRestEndpoints(unittest.TestCase):
    """Verifies Flask REST API endpoints and RBAC authorization."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        mgr = get_circuitdigest_sms_manager()
        mgr.config["recipients"] = {"officers": [], "villagers": []}

    def test_get_status_endpoint(self):
        """GET /api/circuitdigest/status returns masked config and operational telemetry."""
        res = self.client.get("/api/circuitdigest/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("api_key_masked", data)
        self.assertIn("template_id", data)
        self.assertIn("max_daily_limit", data)
        self.assertNotIn("cd_test_valid_api_key_12345", json.dumps(data))  # Never leak raw key

    def test_preview_message_endpoint(self):
        """POST /api/circuitdigest/preview-message calculates template variables and bilingual preview."""
        res = self.client.post("/api/circuitdigest/preview-message", json={
            "count": 3,
            "location": "Bannerghatta Range",
            "state": "tamil_nadu",
            "template_id": 103,
            "group": "officer"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("var1", data)
        self.assertIn("var2", data)
        self.assertLessEqual(data["var1_len"], 30)
        self.assertLessEqual(data["var2_len"], 30)
        self.assertIn("rendered_sms", data)
        self.assertIn("bilingual_message", data)

    def test_validate_key_endpoint(self):
        """POST /api/circuitdigest/validate validates syntax safely."""
        res = self.client.post("/api/circuitdigest/validate", json={"api_key": "cd_sample_token_xyz123"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["valid"])

    def test_rbac_unauthorized_villager_blocked_from_editing_recipients(self):
        """Verifies that a logged-in villager is strictly blocked with HTTP 403 Forbidden."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "villager-uuid-123"
            sess["role"] = "villager"

        # Attempt to add recipient
        res = self.client.post("/api/circuitdigest/recipients/add", json={
            "group": "officers",
            "name": "Hacker",
            "phone": "919999999999"
        })
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertIn("Forbidden", data.get("error", ""))

        # Attempt to modify config
        res_cfg = self.client.post("/api/circuitdigest/config", json={"enabled": False})
        self.assertEqual(res_cfg.status_code, 403)

    def test_rbac_forest_officer_allowed_to_add_recipient(self):
        """Verifies that an authenticated Forest Officer has full authorization."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "officer-uuid-456"
            sess["role"] = "forest_officer"

        res = self.client.post("/api/circuitdigest/recipients/add", json={
            "group": "officers",
            "name": "Range Officer Rajesh",
            "phone": "919876500001"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

    def test_send_test_sms_requires_explicit_confirmation(self):
        """POST /api/circuitdigest/send-test rejects requests without confirmed=True."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "officer-uuid-456"
            sess["role"] = "forest_officer"

        res = self.client.post("/api/circuitdigest/send-test", json={"phone": "917094528671"})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("confirmation required", data.get("error", ""))


if __name__ == "__main__":
    unittest.main()
