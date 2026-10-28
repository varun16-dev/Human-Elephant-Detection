"""
Automated Integration Tests for VETRAX Spider Robot REST API
Covers Phase 4 & Phase 5 requirements:
- VETRAX status & telemetry retrieval (GET /api/robot/vetrax/status)
- Authentication enforcement via X-Device-Token header (POST /api/robot/vetrax/frame)
- Payload size limiting (>10MB rejected with HTTP 413)
- Empty/corrupt payload rejection (HTTP 400)
- Valid frame ingestion & AI inference pipeline (HTTP 200)
- Latest annotated frame retrieval (GET /api/robot/vetrax/latest-frame)
- Simulation endpoint (POST /api/robot/vetrax/simulate)
"""

import unittest
import cv2
import numpy as np
import json
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server import app, VETRAX_API_KEY


class TestVetraxSpiderRobotAPI(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = False  # Ensure auth checks are fully enforced
        self.client = app.test_client()
        self.valid_token = VETRAX_API_KEY

        # Synthesize a valid 320x240 test JPEG
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(img, "TEST FRAME", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        _, self.test_jpeg_bytes = cv2.imencode('.jpg', img)
        self.test_jpeg_bytes = self.test_jpeg_bytes.tobytes()

    def test_get_vetrax_status(self):
        """GET /api/robot/vetrax/status must return current telemetry and scout state."""
        resp = self.client.get('/api/robot/vetrax/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        self.assertIn("device_id", data)
        self.assertIn("total_frames_received", data)
        self.assertIn("status", data)
        self.assertIn("battery_estimate", data)

    def test_frame_unauthorized_without_token(self):
        """POST /api/robot/vetrax/frame without valid X-Device-Token must return 401 Unauthorized."""
        resp = self.client.post(
            '/api/robot/vetrax/frame',
            data=self.test_jpeg_bytes,
            content_type='image/jpeg'
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Unauthorized", resp.json.get("error", ""))

    def test_frame_unauthorized_with_wrong_token(self):
        """POST /api/robot/vetrax/frame with invalid token must return 401."""
        resp = self.client.post(
            '/api/robot/vetrax/frame',
            data=self.test_jpeg_bytes,
            content_type='image/jpeg',
            headers={'X-Device-Token': 'WRONG_INVALID_TOKEN'}
        )
        self.assertEqual(resp.status_code, 401)

    def test_frame_empty_payload(self):
        """POST /api/robot/vetrax/frame with empty body must return 400 Bad Request."""
        resp = self.client.post(
            '/api/robot/vetrax/frame',
            data=b"",
            content_type='image/jpeg',
            headers={'X-Device-Token': self.valid_token}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No valid image", resp.json.get("error", ""))

    def test_frame_oversized_payload(self):
        """POST /api/robot/vetrax/frame exceeding 10MB limit must return 413 Payload Too Large."""
        large_payload = b"\xff\xd8" + b"A" * (10 * 1024 * 1024 + 100)
        resp = self.client.post(
            '/api/robot/vetrax/frame',
            data=large_payload,
            content_type='image/jpeg',
            headers={'X-Device-Token': self.valid_token}
        )
        self.assertEqual(resp.status_code, 413)
        self.assertIn("Payload too large", resp.json.get("error", ""))

    def test_valid_frame_ingestion_and_ai_inference(self):
        """Valid JPEG frame with authentication must run AI inference and return detection telemetry."""
        resp = self.client.post(
            '/api/robot/vetrax/frame',
            data=self.test_jpeg_bytes,
            content_type='image/jpeg',
            headers={
                'X-Device-Token': self.valid_token,
                'X-Device-ID': 'VETRAX-ALPHA-TEST'
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        self.assertEqual(data.get("status"), "success")
        self.assertIn("elephant_detected", data)
        self.assertIn("inference_time_ms", data)
        self.assertGreaterEqual(data.get("inference_time_ms", 0), 0)

        # Verify status endpoint reflects updated frame telemetry
        status_resp = self.client.get('/api/robot/vetrax/status')
        status_data = status_resp.json
        self.assertGreaterEqual(status_data.get("total_frames_received", 0), 1)

    def test_get_latest_frame_image(self):
        """GET /api/robot/vetrax/latest-frame must return the latest annotated image bytes."""
        # Ensure at least one frame was ingested
        self.client.post(
            '/api/robot/vetrax/frame',
            data=self.test_jpeg_bytes,
            content_type='image/jpeg',
            headers={'X-Device-Token': self.valid_token}
        )

        resp = self.client.get('/api/robot/vetrax/latest-frame')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, 'image/jpeg')
        self.assertGreater(len(resp.data), 100)

    def test_simulation_endpoint(self):
        """POST /api/robot/vetrax/simulate must trigger a simulated elephant sighting frame."""
        resp = self.client.post(
            '/api/robot/vetrax/simulate',
            json={'simulate_elephant': True, 'count': 1}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        self.assertEqual(data.get("intake_status_code"), 200)
        self.assertIn("simulated_source", data)
        intake_res = data.get("intake_result", {})
        self.assertEqual(intake_res.get("status"), "success")
        self.assertIn("elephant_detected", intake_res)


if __name__ == '__main__':
    unittest.main()
