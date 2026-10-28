"""
Automated Security, RBAC, and Backend API Integration Tests
Covers Phase 3 & Phase 5 requirements:
- Route availability & unsupported HTTP methods (405)
- Sensitive endpoint authorization & RBAC (POST /api/alerts/free/config requires forest_officer role)
- Secret masking in public configuration endpoints (no exposed passwords/tokens)
- Path traversal prevention on evidence endpoint (/api/detection-images/<filename>)
- Request validation and malformed JSON handling
- Alert history and telemetry retrieval
"""

import unittest
import json
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server import app


class TestSecurityAndBackendAPI(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_core_routes_availability(self):
        """Verify core dashboard routes and API endpoints return valid HTTP status codes."""
        # Landing / Dashboard route
        resp = self.client.get('/')
        self.assertIn(resp.status_code, [200, 302])

        # Free alerts history endpoint
        resp_hist = self.client.get('/api/alerts/free/history')
        self.assertEqual(resp_hist.status_code, 200)
        self.assertIsInstance(resp_hist.json, list)

        # Free alerts config endpoint
        resp_cfg = self.client.get('/api/alerts/free/config')
        self.assertEqual(resp_cfg.status_code, 200)
        self.assertIsInstance(resp_cfg.json, dict)

    def test_unsupported_http_method_rejected(self):
        """GET request on POST-only endpoints must return 405 Method Not Allowed."""
        resp = self.client.get('/api/alerts/free/send')
        self.assertEqual(resp.status_code, 405)

        resp_vetrax = self.client.put('/api/robot/vetrax/frame')
        self.assertEqual(resp_vetrax.status_code, 405)

    def test_path_traversal_prevention(self):
        """Path traversal attempts (../, ..\\) on evidence images must be blocked."""
        traversal_attempts = [
            "../../etc/passwd",
            "..\\..\\windows\\win.ini",
            "....//....//server.py",
            "server.py",  # Should not serve non-image server source files
            "%2e%2e%2fserver.py"
        ]
        for payload in traversal_attempts:
            resp = self.client.get(f'/api/detection-images/{payload}')
            # Must return 400 Bad Request or 404 Not Found, NEVER 200
            self.assertIn(resp.status_code, [400, 404], f"Path traversal not blocked for payload: {payload}")

    def test_sensitive_config_rbac_unauthenticated(self):
        """Unauthenticated requests to save alert config must return 403 Forbidden."""
        resp = self.client.post('/api/alerts/free/config', json={
            "telegram_bot_token": "HACKED_TOKEN"
        })
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Unauthorized", resp.json.get("error", ""))

    def test_sensitive_config_rbac_unauthorized_role(self):
        """Users with villager role must be denied access to save alert config."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'villager_test_123'
            sess['role'] = 'villager'
            sess['user_name'] = 'Villager Test'

        resp = self.client.post('/api/alerts/free/config', json={
            "telegram_bot_token": "HACKED_TOKEN"
        })
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Forest Officer", resp.json.get("error", ""))

    def test_sensitive_config_rbac_authorized_officer(self):
        """Forest officer sessions must be authorized to save alert config."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'officer_test_123'
            sess['role'] = 'forest_officer'
            sess['user_name'] = 'Officer Test'

        resp = self.client.post('/api/alerts/free/config', json={
            "telegram_enabled": True,
            "broadcast_channel": "both"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json.get("success"))

    def test_secrets_masked_in_public_config_response(self):
        """Passwords and tokens returned by config API must be masked (••••) to prevent leaks."""
        resp = self.client.get('/api/alerts/free/config')
        self.assertEqual(resp.status_code, 200)
        data = resp.json

        # Verify password is not returned in plaintext
        smtp_pass = data.get("smtp_password", "")
        if smtp_pass:
            self.assertTrue(smtp_pass.startswith("••••"), "SMTP password must be masked with bullet characters")

        token = data.get("telegram_bot_token", "")
        if token and len(token) > 8:
            self.assertIn("••••", token, "Telegram bot token must contain bullet masking characters")

    def test_malformed_json_handling(self):
        """Malformed or invalid JSON sent to API endpoints must not cause server 500 crashes."""
        resp = self.client.post(
            '/api/alerts/free/send',
            data="NOT_JSON_DATA{{{",
            content_type='application/json'
        )
        # Should return 400 Bad Request or handled error, never uncaught 500
        self.assertIn(resp.status_code, [400, 422])


if __name__ == '__main__':
    unittest.main()
