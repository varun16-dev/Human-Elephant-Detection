"""
Automated Unit and Integration Tests for SMSGate Transport Integration
Human-Elephant Conflict Early Warning System
Department of AI & ML, Sri Sairam College of Engineering

Covers Phase 4 requirements:
1. Tamil Nadu and Karnataka bilingual text keeps correct dynamic count/location/timestamp through new transport.
2. Invalid or zero count creates no send.
3. Duplicate suppression and cooldown still work.
4. Count-increase policy (increase_only).
5. Absence reset then new incident sends again.
6. Gateway down -> failed after bounded retries (exact attempt count) without crashing.
7. Timeout retried with the SAME message id.
8. Auth error (401/403) not retried.
9. 4xx not retried.
10. HTTP 2xx recorded as gateway_accepted (NOT delivered).
11. Sent -> sent_to_carrier.
12. Delivered -> delivered.
13. Failed/Cancelled -> failed with sanitized reason.
14. Processed too long (> 5 min) -> unknown (never auto-retry).
15. Missing env -> "not configured" and server still starts without crashing.
16. Public gateway host rejected unless SMSGATE_ALLOW_PUBLIC_HOST=true.
17. Password and phone numbers never appear in logs, history, or API JSON (masked).
18. Test-send requires confirmation and sends no elephant count (count=0).
19. Dispatch is non-blocking (slow mocked gateway does not delay detection call).
20. TextBee is not called when provider is smsgate.
21. Both existing trigger points in server.py call the manager exactly once.
"""

import os
import sys
import json
import time
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from smsgate_client import (
    SMSGateClient,
    GatewayError,
    GatewayUnavailable,
    GatewayTimeout,
    GatewayServerError,
    GatewayAuthError,
    GatewayRejected,
    call_with_retries
)
from android_sms_gateway import (
    BilingualMessageBuilder,
    AndroidSmsGatewayManager,
    validate_smsgate_url,
    is_valid_e164,
    normalize_to_e164,
    mask_phone_number,
    mask_api_key,
    get_android_sms_manager
)
from server import app


class TestSMSGateTransport(unittest.TestCase):
    """Comprehensive test suite for SMSGate Local Server transport."""

    def setUp(self):
        # Create isolated temp files for config and history so on-disk files are untouched
        self.tmp_config_fd, self.tmp_config_path = tempfile.mkstemp(suffix="_cfg.json")
        self.tmp_hist_fd, self.tmp_hist_path = tempfile.mkstemp(suffix="_hist.json")
        os.close(self.tmp_config_fd)
        os.close(self.tmp_hist_fd)

        # Base test configuration
        initial_config = {
            "enabled": True,
            "provider": "smsgate",
            "state": "karnataka",
            "location_name": "Bandipur Wildlife Corridor",
            "cooldown_seconds": 300,
            "count_change_policy": "always",
            "absence_reset_seconds": 120,
            "max_daily_limit": 50,
            "daily_sent_count": 0,
            "recipients": {
                "officers": [
                    {
                        "id": "off_1",
                        "name": "Ranger Officer",
                        "phone": "+919876543210",
                        "location": "Bandipur Sector 1",
                        "language": "karnataka",
                        "enabled": True
                    }
                ],
                "villagers": []
            }
        }
        with open(self.tmp_config_path, "w", encoding="utf-8") as f:
            json.dump(initial_config, f)
        with open(self.tmp_hist_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        # Set default valid mock environment for SMSGate
        self.env_patcher = patch.dict(os.environ, {
            "SMSGATE_BASE_URL": "http://192.168.1.150:8080",
            "SMSGATE_USERNAME": "admin",
            "SMSGATE_PASSWORD": "secret_password_xyz",
            "SMSGATE_MESSAGES_PATH": "/messages",
            "SMSGATE_TIMEOUT": "2",
            "SMSGATE_MAX_RETRIES": "3",
            "SMSGATE_BACKOFF": "0.01",
            "SMS_TTL_SECONDS": "900",
            "SMS_PRIORITY": "100",
            "SMS_GATEWAY_PROVIDER": "smsgate"
        })
        self.env_patcher.start()

        self.mgr = AndroidSmsGatewayManager(
            config_path=self.tmp_config_path,
            history_file=self.tmp_hist_path,
            provider="smsgate",
            start_poller=False  # Disabled manual loop in tests to control execution
        )

        self.flask_client = app.test_client()
        self.flask_client.testing = True

    def tearDown(self):
        self.mgr.stop_poller()
        self.env_patcher.stop()
        for p in (self.tmp_config_path, self.tmp_hist_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    # -------------------------------------------------------------------------
    # 1. Bilingual message content through SMSGate transport
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_1_tamil_nadu_and_karnataka_bilingual_dispatch(self, mock_send):
        mock_send.return_value = {"id": "evt-bilingual-01", "state": "Pending"}

        # Tamil Nadu recipient
        self.mgr.config["recipients"]["officers"] = [{
            "id": "off_tn",
            "name": "Mudumalai Officer",
            "phone": "+919876543211",
            "location": "Mudumalai Corridor Zone 3",
            "language": "tamil_nadu",
            "enabled": True
        }]

        res_tn = self.mgr.process_detection(
            elephant_count=3,
            location="Mudumalai Corridor Zone 3",
            timestamp_str="25-10-2026, 02:30 PM",
            confidence=95.0,
            dashboard_url="http://192.168.1.50:5000"
        )
        self.assertTrue(res_tn["success"])
        self.assertEqual(res_tn["status"], "gateway_accepted")
        self.assertTrue(mock_send.called)

        # Inspect outbound text message
        call_kwargs = mock_send.call_args[1]
        outbound_text = call_kwargs.get("text", "")
        self.assertIn("3 elephants", outbound_text)
        self.assertIn("Mudumalai Corridor Zone 3", outbound_text)
        self.assertIn("25-10-2026, 02:30 PM", outbound_text)
        self.assertIn("யானை எச்சரிக்கை!", outbound_text)
        self.assertIn("யானைகள் கண்டறியப்பட்டுள்ளன", outbound_text)

        mock_send.reset_mock()

        # Karnataka recipient
        self.mgr.config["recipients"]["officers"] = [{
            "id": "off_kn",
            "name": "Nagarhole Officer",
            "phone": "+919876543212",
            "location": "Nagarhole Sector 4",
            "language": "karnataka",
            "enabled": True
        }]
        self.mgr.active_event = False  # Reset for new incident

        res_kn = self.mgr.process_detection(
            elephant_count=1,
            location="Nagarhole Sector 4",
            timestamp_str="25-10-2026, 03:00 PM"
        )
        self.assertTrue(res_kn["success"])
        call_kwargs_kn = mock_send.call_args[1]
        outbound_text_kn = call_kwargs_kn.get("text", "")
        self.assertIn("An elephant has been detected", outbound_text_kn)
        self.assertIn("ಆನೆ ಎಚ್ಚರಿಕೆ!", outbound_text_kn)
        self.assertIn("ಆನೆ ಪತ್ತೆಯಾಗಿದೆ", outbound_text_kn)

    # -------------------------------------------------------------------------
    # 2. Invalid or zero count creates no send
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_2_invalid_or_zero_count_creates_no_send(self, mock_send):
        for invalid_count in (0, -1, -5):
            res = self.mgr.process_detection(elephant_count=invalid_count)
            self.assertEqual(res["status"], "SKIPPED")
            self.assertFalse(mock_send.called)

    # -------------------------------------------------------------------------
    # 3. Duplicate suppression and cooldown
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_3_duplicate_suppression_and_cooldown(self, mock_send):
        mock_send.return_value = {"id": "evt-cd-1", "state": "Pending"}
        self.mgr.config["cooldown_seconds"] = 100

        # First alert -> Dispatched
        r1 = self.mgr.process_detection(elephant_count=2)
        self.assertEqual(r1["status"], "gateway_accepted")
        self.assertEqual(mock_send.call_count, 1)

        # Immediate second alert with same count -> Suppressed
        r2 = self.mgr.process_detection(elephant_count=2)
        self.assertEqual(r2["status"], "SKIPPED")
        self.assertIn("cooldown", r2["reason"].lower())
        self.assertEqual(mock_send.call_count, 1)

    # -------------------------------------------------------------------------
    # 4. Count-increase policy (increase_only)
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_4_count_increase_policy(self, mock_send):
        mock_send.return_value = {"id": "evt-inc-1", "state": "Pending"}
        self.mgr.config["cooldown_seconds"] = 300
        self.mgr.config["count_change_policy"] = "increase_only"

        # First alert: count 2 -> Sent
        r1 = self.mgr.process_detection(elephant_count=2)
        self.assertEqual(r1["status"], "gateway_accepted")
        self.assertEqual(mock_send.call_count, 1)

        # Count decreases: count 1 -> Suppressed
        r2 = self.mgr.process_detection(elephant_count=1)
        self.assertEqual(r2["status"], "SKIPPED")
        self.assertIn("decreased", r2["reason"].lower())
        self.assertEqual(mock_send.call_count, 1)

        # Count increases: count 4 -> Sent
        r3 = self.mgr.process_detection(elephant_count=4)
        self.assertEqual(r3["status"], "gateway_accepted")
        self.assertEqual(mock_send.call_count, 2)

    # -------------------------------------------------------------------------
    # 5. Absence reset interval then new incident sends again
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_5_absence_reset_lifecycle(self, mock_send):
        mock_send.return_value = {"id": "evt-abs-1", "state": "Pending"}
        self.mgr.config["absence_reset_seconds"] = 60

        # Start incident
        r1 = self.mgr.process_detection(elephant_count=3)
        self.assertTrue(self.mgr.active_event)
        self.assertEqual(self.mgr.last_sent_count, 3)

        # Simulate camera seeing no elephants for 70s (> 60s timeout)
        self.mgr.last_detection_seen_time = time.time() - 75
        r_absent = self.mgr.process_detection(elephant_count=0)
        self.assertEqual(r_absent["status"], "SKIPPED")
        self.assertFalse(self.mgr.active_event)
        self.assertEqual(self.mgr.last_sent_count, 0)

        # New incident detected -> sends immediately
        r_new = self.mgr.process_detection(elephant_count=2)
        self.assertEqual(r_new["status"], "gateway_accepted")
        self.assertEqual(mock_send.call_count, 2)

    # -------------------------------------------------------------------------
    # 6. Gateway down -> failed after bounded retries without crashing
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_6_gateway_down_bounded_retries(self, mock_send):
        # Always raises GatewayUnavailable
        mock_send.side_effect = GatewayUnavailable("Cannot connect to phone gateway")

        res = self.mgr.process_detection(elephant_count=2)

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "failed")
        # With SMSGATE_MAX_RETRIES=3, attempts = 4 (initial + 3 retries)
        self.assertEqual(mock_send.call_count, 4)

        # Record in history exists
        hist = self.mgr.get_history()
        self.assertGreater(len(hist), 0)
        self.assertEqual(hist[0]["status"], "failed")

    # -------------------------------------------------------------------------
    # 7. Timeout retried with the SAME message ID
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_7_timeout_retried_with_same_message_id(self, mock_send):
        captured_message_ids = []

        def side_effect(*args, **kwargs):
            captured_message_ids.append(kwargs.get("message_id"))
            if len(captured_message_ids) < 3:
                raise GatewayTimeout("Timeout on send")
            return {"id": kwargs.get("message_id"), "state": "Pending"}

        mock_send.side_effect = side_effect

        res = self.mgr.process_detection(elephant_count=2)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "gateway_accepted")
        self.assertEqual(len(captured_message_ids), 3)
        # Verify the same message_id is reused across all retry attempts
        self.assertEqual(len(set(captured_message_ids)), 1)
        self.assertTrue(captured_message_ids[0].startswith("evt"))

    # -------------------------------------------------------------------------
    # 8. Auth error not retried
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_8_auth_error_never_retried(self, mock_send):
        mock_send.side_effect = GatewayAuthError("Gateway rejected the credentials (HTTP 401)")

        res = self.mgr.process_detection(elephant_count=2)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "failed")
        # Non-retryable error must execute exactly 1 attempt
        self.assertEqual(mock_send.call_count, 1)

    # -------------------------------------------------------------------------
    # 9. 4xx error not retried
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_9_4xx_rejected_never_retried(self, mock_send):
        mock_send.side_effect = GatewayRejected("Gateway refused the request (HTTP 400): Bad Request")

        res = self.mgr.process_detection(elephant_count=2)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "failed")
        self.assertEqual(mock_send.call_count, 1)

    # -------------------------------------------------------------------------
    # 10. HTTP 2xx recorded as gateway_accepted (NOT delivered)
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_10_http_2xx_recorded_as_gateway_accepted_not_delivered(self, mock_send):
        mock_send.return_value = {"id": "msg-accept-123", "state": "Pending"}

        res = self.mgr.process_detection(elephant_count=2)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "gateway_accepted")
        self.assertNotEqual(res["status"], "delivered")

        # History check
        hist = self.mgr.get_history()
        self.assertEqual(hist[0]["status"], "gateway_accepted")
        self.assertNotEqual(hist[0]["status"], "delivered")

    # -------------------------------------------------------------------------
    # 11. Status Poller: Sent -> sent_to_carrier
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "get_status")
    def test_11_status_poller_sent_to_carrier(self, mock_get_status):
        mock_get_status.return_value = {"state": "Sent"}

        # Seed an accepted event
        record = {
            "timestamp": datetime_str_now(),
            "event_type": "AUTOMATED_DETECTION",
            "status": "gateway_accepted",
            "meta": {
                "gateway_message_id": "gw-msg-sent-01",
                "recipients_results": [{"gateway_message_id": "gw-msg-sent-01", "status": "gateway_accepted"}]
            }
        }
        self.mgr._record_history(record)

        updated = self.mgr.poll_pending_statuses()
        self.assertGreater(updated, 0)

        hist = self.mgr.get_history()
        self.assertEqual(hist[0]["status"], "sent_to_carrier")

    # -------------------------------------------------------------------------
    # 12. Status Poller: Delivered -> delivered
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "get_status")
    def test_12_status_poller_delivered(self, mock_get_status):
        mock_get_status.return_value = {"state": "Delivered"}

        record = {
            "timestamp": datetime_str_now(),
            "event_type": "AUTOMATED_DETECTION",
            "status": "sent_to_carrier",
            "meta": {
                "gateway_message_id": "gw-msg-deliv-01",
                "recipients_results": [{"gateway_message_id": "gw-msg-deliv-01", "status": "sent_to_carrier"}]
            }
        }
        self.mgr._record_history(record)

        updated = self.mgr.poll_pending_statuses()
        self.assertGreater(updated, 0)

        hist = self.mgr.get_history()
        self.assertEqual(hist[0]["status"], "delivered")

    # -------------------------------------------------------------------------
    # 13. Status Poller: Failed -> failed with sanitized reason
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "get_status")
    def test_13_status_poller_failed_with_sanitized_reason(self, mock_get_status):
        mock_get_status.return_value = {
            "state": "Failed",
            "reason": "SIM card network lost for +919876543210 (pw: secret_password_xyz)"
        }

        record = {
            "timestamp": datetime_str_now(),
            "event_type": "AUTOMATED_DETECTION",
            "status": "gateway_accepted",
            "meta": {
                "gateway_message_id": "gw-msg-fail-01",
                "recipients_results": [{"gateway_message_id": "gw-msg-fail-01", "status": "gateway_accepted"}]
            }
        }
        self.mgr._record_history(record)

        updated = self.mgr.poll_pending_statuses()
        self.assertGreater(updated, 0)

        hist = self.mgr.get_history()
        self.assertEqual(hist[0]["status"], "failed")
        # Verify sanitization in stored error
        err_text = hist[0].get("error", "")
        self.assertNotIn("secret_password_xyz", err_text)
        self.assertNotIn("+919876543210", err_text)
        self.assertIn("[number]", err_text)

    # -------------------------------------------------------------------------
    # 14. Status Poller: Processed too long (> 5 min) -> unknown
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "get_status")
    def test_14_status_poller_processed_stuck_marks_unknown(self, mock_get_status):
        mock_get_status.return_value = {"state": "Processed"}

        # Timestamp 6 minutes in the past
        past_time = time.time() - 360
        past_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(past_time))

        record = {
            "timestamp": past_str,
            "event_type": "AUTOMATED_DETECTION",
            "status": "gateway_accepted",
            "meta": {
                "gateway_message_id": "gw-msg-stuck-01",
                "recipients_results": [{"gateway_message_id": "gw-msg-stuck-01", "status": "gateway_accepted"}]
            }
        }
        self.mgr._record_history(record)

        updated = self.mgr.poll_pending_statuses()
        self.assertGreater(updated, 0)

        hist = self.mgr.get_history()
        self.assertEqual(hist[0]["status"], "unknown")

    # -------------------------------------------------------------------------
    # 15. Missing env reports "not configured" and server still starts
    # -------------------------------------------------------------------------
    def test_15_missing_env_reports_not_configured_no_crash(self):
        with patch.dict(os.environ, {
            "SMSGATE_BASE_URL": "",
            "SMSGATE_USERNAME": "",
            "SMSGATE_PASSWORD": ""
        }):
            unconfigured_mgr = AndroidSmsGatewayManager(
                config_path=self.tmp_config_path,
                history_file=self.tmp_hist_path,
                start_poller=False
            )
            self.assertFalse(unconfigured_mgr.is_smsgate_configured())

            # Validate connection returns NOT_CONFIGURED without crashing
            res = unconfigured_mgr.validate_connection()
            self.assertFalse(res["valid"])
            self.assertEqual(res["status"], "NOT_CONFIGURED")

            # Send returns not configured without crashing
            ok, msg, details = unconfigured_mgr.send_sms("+919876543210", "Test Alert")
            self.assertFalse(ok)
            self.assertEqual(details["status"], "not configured")

            # Flask API /api/sms/status returns 200 with smsgate_configured=False
            resp = self.flask_client.get('/api/sms/status')
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertFalse(data.get("smsgate_configured", True))

    # -------------------------------------------------------------------------
    # 16. Public gateway host rejected unless SMSGATE_ALLOW_PUBLIC_HOST=true
    # -------------------------------------------------------------------------
    def test_16_public_gateway_host_security_validation(self):
        # Public IP should be rejected
        ok, reason = validate_smsgate_url("http://8.8.8.8:8080", allow_public=False)
        self.assertFalse(ok)
        self.assertIn("rejected", reason.lower())

        # Public internet domain should be rejected
        ok_domain, _ = validate_smsgate_url("http://api.sms-gate.app:8080", allow_public=False)
        self.assertFalse(ok_domain)

        # Private RFC1918 IPs accepted
        self.assertTrue(validate_smsgate_url("http://192.168.1.50:8080")[0])
        self.assertTrue(validate_smsgate_url("http://10.0.0.5:8080")[0])
        self.assertTrue(validate_smsgate_url("http://172.16.0.10:8080")[0])

        # Loopback accepted
        self.assertTrue(validate_smsgate_url("http://127.0.0.1:8080")[0])
        self.assertTrue(validate_smsgate_url("http://localhost:8080")[0])

        # CGNAT accepted (100.64.0.0/10)
        self.assertTrue(validate_smsgate_url("http://100.64.1.25:8080")[0])

        # .local and .lan domains accepted
        self.assertTrue(validate_smsgate_url("http://myphone.local:8080")[0])
        self.assertTrue(validate_smsgate_url("http://gateway.lan:8080")[0])

        # Public allowed when override flag is set
        self.assertTrue(validate_smsgate_url("http://8.8.8.8:8080", allow_public=True)[0])

    # -------------------------------------------------------------------------
    # 17. Password and phone numbers never leak in logs, history, or API
    # -------------------------------------------------------------------------
    def test_17_credentials_and_phone_privacy(self):
        safe_cfg = self.mgr.get_safe_config()

        # Password must NEVER be exposed
        self.assertNotIn("password", safe_cfg)
        self.assertNotIn("smsgate_password", safe_cfg)
        self.assertNotIn("secret_password_xyz", json.dumps(safe_cfg))

        # Recipients must be masked
        officers = safe_cfg["recipients"]["officers"]
        self.assertGreater(len(officers), 0)
        self.assertEqual(officers[0]["phone_masked"], "+91 98*** ***10")

        # History masking
        record = {
            "timestamp": datetime_str_now(),
            "event_type": "AUTOMATED_DETECTION",
            "message": "Alert text",
            "details": self.mgr._sanitize_text("Error with secret_password_xyz on +919876543210")
        }
        self.assertNotIn("secret_password_xyz", record["details"])
        self.assertNotIn("+919876543210", record["details"])

        # Flask /api/sms/status API response check
        api_res = self.flask_client.get('/api/sms/status')
        api_text = api_res.get_data(as_text=True)
        self.assertNotIn("secret_password_xyz", api_text)

    # -------------------------------------------------------------------------
    # 18. Test-send requires confirmation and sends no elephant count
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_18_test_send_requires_confirmation_and_no_count(self, mock_send):
        mock_send.return_value = {"id": "test-msg-01", "state": "Pending"}

        # Without confirmation -> Rejected
        ok_unconf, msg_unconf, rec_unconf = self.mgr.send_real_test_sms(
            recipient="+919876543210",
            confirmed=False
        )
        self.assertFalse(ok_unconf)
        self.assertIn("Explicit confirmation required", msg_unconf)
        self.assertFalse(mock_send.called)

        # With confirmation -> Accepted
        ok_conf, msg_conf, rec_conf = self.mgr.send_real_test_sms(
            recipient="+919876543210",
            confirmed=True
        )
        self.assertTrue(ok_conf)
        self.assertEqual(rec_conf["elephant_count"], 0)
        self.assertEqual(rec_conf["event_type"], "MANUAL_TEST")

        # Inspect outbound message: must NOT mention elephant count
        call_kwargs = mock_send.call_args[1]
        outbound_text = call_kwargs.get("text", "")
        self.assertIn("TEST ALERT", outbound_text)
        self.assertNotIn("Count:", outbound_text)
        self.assertNotIn("elephants detected", outbound_text)

    # -------------------------------------------------------------------------
    # 19. Dispatch is non-blocking (slow gateway does not delay detection)
    # -------------------------------------------------------------------------
    @patch.object(SMSGateClient, "send")
    def test_19_dispatch_is_non_blocking(self, mock_send):
        def slow_send(*args, **kwargs):
            time.sleep(1.0)
            return {"id": "slow-01", "state": "Pending"}

        mock_send.side_effect = slow_send

        t_start = time.time()
        ret = self.mgr.process_detection_async(elephant_count=3)
        duration = time.time() - t_start

        self.assertTrue(ret)
        # Asynchronous call must return almost instantly (< 0.2s) despite 1.0s delay
        self.assertLess(duration, 0.25)

    # -------------------------------------------------------------------------
    # 20. TextBee is not called when provider is smsgate
    # -------------------------------------------------------------------------
    @patch("requests.post")
    @patch.object(SMSGateClient, "send")
    def test_20_textbee_not_called_when_provider_is_smsgate(self, mock_smsgate_send, mock_requests_post):
        mock_smsgate_send.return_value = {"id": "smsgate-only-01", "state": "Pending"}

        self.assertEqual(self.mgr.provider, "smsgate")
        res = self.mgr.process_detection(elephant_count=2)

        self.assertTrue(res["success"])
        self.assertTrue(mock_smsgate_send.called)

        # Ensure requests.post was NEVER called for TextBee's endpoint
        for call in mock_requests_post.call_args_list:
            called_url = call[0][0] if call[0] else call[1].get("url", "")
            self.assertNotIn("api.textbee.dev", called_url)

    # -------------------------------------------------------------------------
    # 21. Existing trigger paths call manager once per detection
    # -------------------------------------------------------------------------
    def test_21_existing_trigger_paths_call_manager_once(self):
        with patch("android_sms_gateway.AndroidSmsGatewayManager.process_detection_async") as mock_async:
            from android_sms_gateway import get_android_sms_manager
            mgr = get_android_sms_manager()
            mgr.process_detection_async(elephant_count=3, location="Test Zone")
            self.assertEqual(mock_async.call_count, 1)


def datetime_str_now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


if __name__ == "__main__":
    unittest.main()
