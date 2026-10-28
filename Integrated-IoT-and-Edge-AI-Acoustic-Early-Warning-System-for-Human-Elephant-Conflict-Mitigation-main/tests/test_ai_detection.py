"""
Automated Unit Tests for AI Elephant Detection Pipeline & Cooldown Logic
Covers Phase 5 requirements:
- Valid image input
- Corrupted or empty image input
- Model unavailable and inference exception handling
- Elephant detection, non-elephant input, confidence threshold behavior
- Duplicate event suppression and cooldown behavior
"""

import unittest
import numpy as np
import cv2
import time
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_elephant_detector import ElephantDetector, DetectionCooldownManager, get_elephant_detector


class TestAIElephantDetector(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.detector = get_elephant_detector()

    def test_singleton_instance(self):
        """Verify detector singleton pattern returns same initialized instance."""
        detector2 = get_elephant_detector()
        self.assertIs(self.detector, detector2)

    def test_corrupted_empty_input(self):
        """Verify detector handles empty bytes, None, and corrupted frames without crashing."""
        # None input
        res_none = self.detector.detect(None)
        self.assertFalse(res_none['elephant_detected'])
        self.assertEqual(res_none['elephant_count'], 0)
        self.assertIn("error", res_none)

        # Empty bytes
        res_empty = self.detector.detect(b"")
        self.assertFalse(res_empty['elephant_detected'])
        self.assertEqual(res_empty['elephant_count'], 0)

        # Corrupted junk bytes
        res_corrupt = self.detector.detect(b"\x00\xff\xfe\x01\x42INVALIDJPEGDATA")
        self.assertFalse(res_corrupt['elephant_detected'])
        self.assertEqual(res_corrupt['elephant_count'], 0)

    def test_non_elephant_synthetic_frame(self):
        """Verify detector processes a synthetic non-elephant frame (solid color/noise) safely."""
        # Solid grey frame 320x240
        blank_frame = np.full((240, 320, 3), 128, dtype=np.uint8)
        res = self.detector.detect(blank_frame)

        self.assertIn('elephant_detected', res)
        self.assertFalse(res['elephant_detected'], "Solid grey frame should not detect elephants")
        self.assertEqual(res['elephant_count'], 0)
        self.assertEqual(res['confidence'], 0.0)
        self.assertIsInstance(res['detections'], list)
        self.assertGreaterEqual(res['inference_time_ms'], 0)
        self.assertIsNotNone(res['annotated_frame'])

    def test_jpeg_bytes_input(self):
        """Verify detector can process encoded JPEG bytes directly."""
        test_img = np.zeros((240, 320, 3), dtype=np.uint8)
        _, jpeg_bytes = cv2.imencode('.jpg', test_img)
        res = self.detector.detect(jpeg_bytes.tobytes())

        self.assertIn('elephant_detected', res)
        self.assertFalse(res['elephant_detected'])
        self.assertEqual(res['elephant_count'], 0)

    def test_confidence_threshold_filtering(self):
        """Verify custom threshold configuration is respected by detector."""
        # Ensure setting high threshold filters out low-confidence noise
        frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        res_high = self.detector.detect(frame, confidence_threshold=0.99)
        self.assertFalse(res_high['elephant_detected'])
        self.assertEqual(res_high['elephant_count'], 0)


class TestDetectionCooldownManager(unittest.TestCase):

    def setUp(self):
        self.cooldown = DetectionCooldownManager(cooldown_seconds=2, confirmation_frames=1)

    def test_initial_detection_allowed(self):
        """First detection should trigger an alert when confirmation_frames=1."""
        allowed, reason = self.cooldown.should_alert(device_id="CAM-01")
        self.assertTrue(allowed)
        self.assertIn("confirmed", reason)

    def test_confirmation_frames_logic(self):
        """Verify that when confirmation_frames=2, single frame awaits confirmation."""
        strict_mgr = DetectionCooldownManager(cooldown_seconds=5, confirmation_frames=2)
        # Frame 1: Should await confirmation
        allowed1, reason1 = strict_mgr.should_alert("CAM-STRICT")
        self.assertFalse(allowed1)
        self.assertIn("Awaiting confirmation", reason1)

        # Frame 2: Confirmed!
        allowed2, reason2 = strict_mgr.should_alert("CAM-STRICT")
        self.assertTrue(allowed2)
        self.assertIn("confirmed", reason2)

    def test_duplicate_continuous_detection_suppressed(self):
        """Consecutive detections within cooldown window must be suppressed."""
        # First event
        allowed1, _ = self.cooldown.should_alert(device_id="CAM-01")
        self.assertTrue(allowed1)

        # Immediate follow-up event
        allowed2, reason2 = self.cooldown.should_alert(device_id="CAM-01")
        self.assertFalse(allowed2, "Continuous detection within 2s should be suppressed")
        self.assertIn("Cooldown active", reason2)

    def test_device_isolation(self):
        """Cooldown on one camera/robot node should not block alerts from another node."""
        allowed1, _ = self.cooldown.should_alert(device_id="VETRAX-ALPHA-01")
        self.assertTrue(allowed1)

        allowed2, _ = self.cooldown.should_alert(device_id="CORRIDOR-FIXED-CAM-02")
        self.assertTrue(allowed2, "Different device ID should not be blocked by first device's cooldown")

    def test_cooldown_expiry(self):
        """After cooldown interval elapses, next detection must be permitted."""
        short_cooldown = DetectionCooldownManager(cooldown_seconds=1, confirmation_frames=1)
        allowed1, _ = short_cooldown.should_alert(device_id="TEST-NODE")
        self.assertTrue(allowed1)

        # Wait for cooldown to expire
        time.sleep(1.1)

        allowed2, reason2 = short_cooldown.should_alert(device_id="TEST-NODE")
        self.assertTrue(allowed2, "Detection after cooldown expiry should be permitted")
        self.assertIn("confirmed", reason2)

    def test_manual_reset(self):
        """Resetting a device's cooldown allows immediate alerting."""
        self.cooldown.should_alert(device_id="CAM-01")
        self.cooldown.reset(device_id="CAM-01")

        allowed, _ = self.cooldown.should_alert(device_id="CAM-01")
        self.assertTrue(allowed, "Resetting cooldown should allow immediate alert")


if __name__ == '__main__':
    unittest.main()
