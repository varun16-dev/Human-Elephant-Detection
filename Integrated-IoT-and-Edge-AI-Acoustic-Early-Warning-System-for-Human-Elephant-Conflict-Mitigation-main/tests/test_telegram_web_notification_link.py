"""
Unit Tests for Web Notification Activation & Linked Telegram Alerts
Validates Phase requirements:
1. Every time the app is opened, it should not send notifications (startup grace period + cache preloading).
2. If web notification is activated, then Telegram notifications are sent.
3. If web notification is NOT activated, Telegram notifications are suppressed.
4. /api/notifications/web-status accurately reports and toggles activation state.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import time
from datetime import datetime

# Ensure project root in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import server
from server import app, is_web_notification_active, set_web_notification_active, sync_detection_record


class TestTelegramWebNotificationLink(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def tearDown(self):
        set_web_notification_active(True)

    @patch('server.is_web_notification_active', return_value=False)
    @patch('free_alert_service.FreeAlertManager.trigger_elephant_detection_event')
    def test_telegram_suppressed_when_web_notification_inactive(self, mock_tg_trigger, mock_web_active):
        """Telegram alert must be suppressed when web notification is not activated."""
        with patch.dict(os.environ, {"TELEGRAM_ALERTS_ENABLED": "true"}):
            success, res = sync_detection_record(
                timestamp_iso=datetime.now().isoformat(),
                elephant_count=2,
                confidence=0.92,
                image_filename="test_elephant.jpg",
                send_alert=True
            )
            self.assertTrue(success)
            # Telegram trigger MUST NOT be called because web notification is inactive
            mock_tg_trigger.assert_not_called()

    @patch('server.is_web_notification_active', return_value=True)
    @patch('free_alert_service.FreeAlertManager.trigger_elephant_detection_event')
    def test_telegram_sent_when_web_notification_active(self, mock_tg_trigger, mock_web_active):
        """Telegram alert must be dispatched when web notification is activated."""
        with patch.dict(os.environ, {"TELEGRAM_ALERTS_ENABLED": "true"}):
            success, res = sync_detection_record(
                timestamp_iso=datetime.now().isoformat(),
                elephant_count=3,
                confidence=0.95,
                image_filename="test_elephant_active.jpg",
                send_alert=True
            )
            self.assertTrue(success)
            # Telegram trigger MUST be called because web notification is active
            mock_tg_trigger.assert_called_once()

    def test_startup_grace_period_suppresses_notifications_on_open(self):
        """On app start (within first 10s of launch), notifications are strictly suppressed."""
        with patch('server.SERVER_START_TIME', time.time()):
            with patch('server.IS_TEST_ENV', False):
                with patch('free_alert_service.FreeAlertManager.trigger_elephant_detection_event') as mock_tg:
                    success, res = sync_detection_record(
                        timestamp_iso=datetime.now().isoformat(),
                        elephant_count=1,
                        confidence=0.88,
                        image_filename="launch_test.jpg",
                        send_alert=True
                    )
                    self.assertTrue(success)
                    mock_tg.assert_not_called()

    def test_web_status_endpoint_get_and_post(self):
        """Verify /api/notifications/web-status GET and POST functionality."""
        # Test GET
        get_res = self.client.get('/api/notifications/web-status')
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.get_json()
        self.assertIn("active", get_data)
        self.assertIn("telegram_linked", get_data)
        self.assertTrue(get_data["telegram_linked"])

        # Test POST activation
        post_res = self.client.post('/api/notifications/web-status', json={"active": True})
        self.assertEqual(post_res.status_code, 200)
        self.assertTrue(is_web_notification_active())

        # Test POST deactivation
        post_deact = self.client.post('/api/notifications/web-status', json={"active": False})
        self.assertEqual(post_deact.status_code, 200)

    def test_subscribe_and_unsubscribe_toggles_activation(self):
        """Verify subscribe endpoint activates web notification and unsubscribe deactivates it."""
        sub_payload = {
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test-token-unit-test",
                "keys": {
                    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9t0A3q8-fP",
                    "auth": "tBHItJI5svbpez7KI4CCXg"
                }
            }
        }
        
        # Subscribe
        sub_resp = self.client.post('/api/push/subscribe', json=sub_payload)
        self.assertEqual(sub_resp.status_code, 200)
        sub_data = sub_resp.get_json()
        self.assertTrue(sub_data.get("success"))
        self.assertTrue(sub_data.get("web_notifications_active"))
        self.assertTrue(is_web_notification_active())

        # Unsubscribe
        unsub_resp = self.client.post('/api/push/unsubscribe', json=sub_payload)
        self.assertEqual(unsub_resp.status_code, 200)
        unsub_data = unsub_resp.get_json()
        self.assertTrue(unsub_data.get("success"))
        self.assertFalse(unsub_data.get("web_notifications_active"))


if __name__ == '__main__':
    unittest.main()
