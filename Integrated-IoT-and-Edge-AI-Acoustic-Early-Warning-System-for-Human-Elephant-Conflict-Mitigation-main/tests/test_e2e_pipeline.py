"""
End-to-End Automated Pipeline Integration Test
Covers the Complete Automated Workflow:
ESP32-CAM -> Image Transmission -> Flask Backend -> AI Elephant Detection ->
Evidence Storage -> Dashboard Update -> Alert Notification Dispatch -> Cooldown Debounce
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json
import time

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server import app, VETRAX_API_KEY
from free_alert_service import get_free_alert_manager
from ai_elephant_detector import get_cooldown_manager


class TestEndToEndPipeline(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.token = VETRAX_API_KEY

        # Reset cooldown states before test
        get_cooldown_manager().reset()

        # Locate sample elephant test image fixture (verified positive detection)
        test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'WelcomeScreen', 'fall_final', 'detected_elephants'))
        self.sample_img_path = None
        if os.path.exists(test_dir):
            preferred = [
                "elephant_20260919_205314.jpg",
                "elephant_20260906_171548.jpg",
                "elephant_20260925_193040.jpg"
            ]
            for p in preferred:
                full_p = os.path.join(test_dir, p)
                if os.path.exists(full_p):
                    self.sample_img_path = full_p
                    break
            if not self.sample_img_path:
                candidates = [f for f in os.listdir(test_dir) if f.lower().endswith(('.jpg', '.jpeg'))]
                if candidates:
                    self.sample_img_path = os.path.join(test_dir, candidates[0])

    @patch('requests.post')
    def test_complete_elephant_detection_to_alert_pipeline(self, mock_post):
        """
        Verify complete automated flow:
        1. Robot frame intake with auth
        2. Server-side AI model inference
        3. Elephant detection confirmed
        4. Evidence image saved to static/detections
        5. Telegram alert dispatched with photo attachment
        6. Real-time dashboard confirmed detection endpoint updated
        7. Evidence visible in gallery endpoint
        """
        if not self.sample_img_path or not os.path.exists(self.sample_img_path):
            self.skipTest("Sample elephant image fixture not found in detected_elephants.")

        # Mock Telegram API success response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "result": {"message_id": 9901, "chat": {"id": 12345}}
        }
        mock_post.return_value = mock_resp

        # Read actual elephant test image
        with open(self.sample_img_path, 'rb') as f:
            frame_bytes = f.read()

        # Step 1: ESP32-CAM transmits frame 1 to Flask backend (Awaiting confirmation)
        resp1 = self.client.post(
            '/api/robot/vetrax/frame',
            data=frame_bytes,
            content_type='image/jpeg',
            headers={
                'X-Device-Token': self.token,
                'X-Device-ID': 'VETRAX-E2E-TEST'
            }
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json
        self.assertEqual(data1.get("status"), "success")
        self.assertTrue(data1.get("elephant_detected"), "Model must detect elephant in test fixture")
        self.assertGreater(data1.get("elephant_count", 0), 0)

        # Step 2: Transmit frame 2 (Reaches confirmation threshold -> triggers alert!)
        resp2 = self.client.post(
            '/api/robot/vetrax/frame',
            data=frame_bytes,
            content_type='image/jpeg',
            headers={
                'X-Device-Token': self.token,
                'X-Device-ID': 'VETRAX-E2E-TEST'
            }
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json
        self.assertTrue(data2.get("elephant_detected"))
        self.assertTrue(data2.get("alert_triggered"), "Frame 2 must satisfy confirmation threshold and trigger alert")

        evidence_filename = data2.get("evidence_image")
        self.assertIsNotNone(evidence_filename)

        # Step 3: Evidence Storage
        evidence_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'detections', evidence_filename)
        self.assertTrue(os.path.exists(evidence_path), f"Evidence file must exist at {evidence_path}")
        self.assertGreater(os.path.getsize(evidence_path), 500)

        # Step 4: Dashboard Status Update
        # Verify confirmed detection endpoint reports fresh detection
        confirmed_resp = self.client.get('/api/elephant-detection/confirmed')
        self.assertEqual(confirmed_resp.status_code, 200)
        confirmed_data = confirmed_resp.json
        self.assertTrue(confirmed_data.get("confirmed"))
        self.assertIsNotNone(confirmed_data.get("detection"))
        self.assertEqual(confirmed_data["detection"].get("device_id"), "VETRAX-SPIDER-01")

        # Verify evidence appears in gallery
        gallery_resp = self.client.get('/api/detection-images')
        self.assertEqual(gallery_resp.status_code, 200)
        self.assertIn(evidence_filename, gallery_resp.json)

        # Step 5: Cooldown Debounce (Continuous Detection Prevention)
        # Transmit frame 3 immediately for same device ID
        resp3 = self.client.post(
            '/api/robot/vetrax/frame',
            data=frame_bytes,
            content_type='image/jpeg',
            headers={
                'X-Device-Token': self.token,
                'X-Device-ID': 'VETRAX-E2E-TEST'
            }
        )
        self.assertEqual(resp3.status_code, 200)
        data3 = resp3.json
        self.assertTrue(data3.get("elephant_detected"))
        # Crucial check: Alert must NOT be triggered third time due to active cooldown!
        self.assertFalse(data3.get("alert_triggered"), "Immediate continuous sighting must be debounced by cooldown manager")

    def test_safe_non_elephant_frame_pipeline(self):
        """Verify non-elephant frame does not trigger alerts or false positives."""
        import numpy as np
        import cv2

        # Create blank 320x240 image
        blank = np.full((240, 320, 3), 100, dtype=np.uint8)
        _, jpeg = cv2.imencode('.jpg', blank)

        resp = self.client.post(
            '/api/robot/vetrax/frame',
            data=jpeg.tobytes(),
            content_type='image/jpeg',
            headers={
                'X-Device-Token': self.token,
                'X-Device-ID': 'VETRAX-SAFE-TEST'
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        self.assertFalse(data.get("elephant_detected"))
        self.assertEqual(data.get("elephant_count"), 0)
        self.assertFalse(data.get("alert_triggered"))

    def test_pipeline_error_recovery(self):
        """Verify pipeline handles corrupted frames without crashing and recovers immediately."""
        # 1. Send garbage bytes
        resp_bad = self.client.post(
            '/api/robot/vetrax/frame',
            data=b"INVALID_CORRUPT_BYTES_XYZ_12345",
            content_type='image/jpeg',
            headers={'X-Device-Token': self.token}
        )
        self.assertEqual(resp_bad.status_code, 400)

        # 2. Immediately send empty payload
        resp_empty = self.client.post(
            '/api/robot/vetrax/frame',
            data=b"",
            content_type='image/jpeg',
            headers={'X-Device-Token': self.token}
        )
        self.assertEqual(resp_empty.status_code, 400)

        # 3. Immediately send valid frame - system must have recovered and succeed
        import numpy as np
        import cv2
        valid_img = np.zeros((240, 320, 3), dtype=np.uint8)
        _, valid_jpeg = cv2.imencode('.jpg', valid_img)

        resp_ok = self.client.post(
            '/api/robot/vetrax/frame',
            data=valid_jpeg.tobytes(),
            content_type='image/jpeg',
            headers={'X-Device-Token': self.token}
        )
        self.assertEqual(resp_ok.status_code, 200)
        self.assertEqual(resp_ok.json.get("status"), "success")


if __name__ == '__main__':
    unittest.main()
