"""Dashboard API authentication regression tests.

These tests run against Flask's test client with a fake bot. They never call
Discord's API, use real credentials, or mutate live guild configuration.
"""
import unittest

from flask import Flask

import web_dashboard


class FakeBot:
    guilds = []

    def is_ready(self):
        return False

    def get_guild(self, guild_id):
        return None


class DashboardAuthTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test-only-secret"
        web_dashboard.register_dashboard(self.app, FakeBot())
        self.client = self.app.test_client()

    def test_guild_list_requires_login(self):
        response = self.client.get("/api/guilds")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json().get("error"), "login_required")

    def test_overview_requires_login_before_guild_lookup(self):
        response = self.client.get("/api/guild/123456789012345/overview")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json().get("error"), "login_required")

    def test_backup_api_requires_login_for_reads_and_writes(self):
        base = "/api/guild/123456789012345/config/backups"
        read_response = self.client.get(base)
        write_response = self.client.post(base, json={"action": "create"})
        self.assertEqual(read_response.status_code, 401)
        self.assertEqual(write_response.status_code, 401)
        self.assertEqual(read_response.get_json().get("error"), "login_required")
        self.assertEqual(write_response.get_json().get("error"), "login_required")

    def test_command_permissions_api_requires_login_for_reads_and_writes(self):
        base = "/api/guild/123456789012345/config/command-permissions"
        read_response = self.client.get(base)
        write_response = self.client.post(base, json={"command": "help", "enabled": True})
        self.assertEqual(read_response.status_code, 401)
        self.assertEqual(write_response.status_code, 401)
        self.assertEqual(read_response.get_json().get("error"), "login_required")
        self.assertEqual(write_response.get_json().get("error"), "login_required")

    def test_api_responses_include_security_headers(self):
        response = self.client.get("/api/guilds")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")


if __name__ == "__main__":
    unittest.main()
