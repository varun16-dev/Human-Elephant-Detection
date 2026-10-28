"""
Automated Tests for Frontend Assets, JavaScript Syntax, and HTML Template Integrity
Covers Phase 5 requirements:
- JavaScript syntax validation (via Node.js)
- HTML template DOM element existence and integrity
- Verification of Free Alert Hub & VETRAX Spider Robot UI elements
"""

import unittest
import subprocess
import os
import re
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class TestFrontendAssets(unittest.TestCase):

    def test_javascript_syntax_via_node(self):
        """Verify JavaScript files have valid syntax and pass Node.js check without errors."""
        js_files = [
            os.path.join(BASE_DIR, 'static', 'js', 'free_alerts.js'),
            os.path.join(BASE_DIR, 'static', 'js', 'android_sms.js'),
            os.path.join(BASE_DIR, 'static', 'js', 'vetrax_robot.js'),
            os.path.join(BASE_DIR, 'static', 'js', 'camera_detection.js')
        ]
        for fpath in js_files:
            self.assertTrue(os.path.exists(fpath), f"JS file missing: {fpath}")
            proc = subprocess.run(
                ['node', '--check', fpath],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.assertEqual(
                proc.returncode, 0,
                f"Syntax error in {os.path.basename(fpath)}:\n{proc.stderr}"
            )

    def test_index_html_free_alert_dom_elements(self):
        """Verify templates/index.html includes all required DOM IDs for Free Alert Hub."""
        html_path = os.path.join(BASE_DIR, 'templates', 'index.html')
        self.assertTrue(os.path.exists(html_path))

        with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        required_ids = [
            "free-alert-form",
            "free-telegram-chat",
            "free-telegram-token",
            "free-target-phone",
            "free-carrier-select",
            "free-smtp-email",
            "free-smtp-password",
            "free-alert-severity",
            "free-alert-message",
            "btn-free-send",
            "btn-test-telegram",
            "btn-test-carrier-sms",
            "btn-save-free-config",
            "free-alert-history-body"
        ]

        for elem_id in required_ids:
            self.assertIn(
                f'id="{elem_id}"',
                content,
                f"Required DOM element id='{elem_id}' missing in templates/index.html"
            )

    def test_index_html_vetrax_dom_elements_removed(self):
        """Verify templates/index.html cleanly omits VETRAX Spider Robot card."""
        html_path = os.path.join(BASE_DIR, 'templates', 'index.html')
        with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        self.assertNotIn('id="vetrax-card"', content)
        self.assertNotIn('VETRAX Spider Robot', content)

    def test_index_html_android_sms_dom_elements(self):
        """Verify templates/index.html includes required DOM IDs for Android SIM SMS Gateway."""
        html_path = os.path.join(BASE_DIR, 'templates', 'index.html')
        with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        required_sms_ids = [
            "sms-gateway-status-badge",
            "sms-daily-quota-display",
            "btn-validate-sms-gateway",
            "sms-validate-result",
            "sms-state-select",
            "sms-location-input",
            "sms-recipient-input",
            "sms-recipient-masked-display",
            "sms-api-key-input",
            "sms-cooldown-input",
            "sms-policy-select",
            "sms-absence-input",
            "sms-preview-message-box",
            "btn-save-sms-config",
            "btn-send-real-test-sms",
            "sms-history-table-body",
            "sms-test-confirm-modal"
        ]

        for elem_id in required_sms_ids:
            self.assertIn(
                f'id="{elem_id}"',
                content,
                f"Required Android SMS DOM element id='{elem_id}' missing in templates/index.html"
            )

    def test_index_html_twilio_removed(self):
        """Verify templates/index.html cleanly omits Twilio SMS components."""
        html_path = os.path.join(BASE_DIR, 'templates', 'index.html')
        with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        self.assertNotIn('twilio', content.lower())


if __name__ == '__main__':
    unittest.main()
