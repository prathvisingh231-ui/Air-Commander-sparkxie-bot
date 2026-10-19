"""Dashboard API authentication regression tests.

These tests run against Flask's test client with a fake bot. They never call
Discord's API, use real credentials, or mutate live guild configuration.
"""
import unittest
from unittest import mock

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

    def test_authenticated_user_cannot_access_unmanaged_guild(self):
        sid = "test-auth-session"
        web_dashboard._AUTH_SESSIONS[sid] = {
            "access_token": "test-token",
            "user": {"id": "test-user", "username": "Tester"},
            "expires_at": __import__("time").time() + 60,
        }
        try:
            with self.client.session_transaction() as sess:
                sess["air_sid"] = sid
            with mock.patch.object(web_dashboard, "_managed_guilds", return_value=[]):
                response = self.client.get("/api/guild/123456789012345/overview")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.get_json().get("error"), "forbidden")
        finally:
            web_dashboard._AUTH_SESSIONS.pop(sid, None)

    def test_backup_download_requires_login(self):
        response = self.client.get(
            "/api/guild/123456789012345/config/backups/AC-123456789012345-abcdef/download"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json().get("error"), "login_required")

    def test_api_responses_include_security_headers(self):
        response = self.client.get("/api/guilds")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")


    def test_all_config_write_routes_require_csrf(self):
        class Guild:
            id = 123456789012345
            owner_id = 999999999999999

        class ReadyBot(FakeBot):
            guilds = [Guild()]

            def get_guild(self, guild_id):
                return Guild() if int(guild_id) == 123456789012345 else None

        app = Flask(__name__)
        app.secret_key = "test-only-secret"
        web_dashboard.register_dashboard(app, ReadyBot())
        client = app.test_client()
        sid = "test-csrf-session"
        web_dashboard._AUTH_SESSIONS[sid] = {
            "access_token": "test-token",
            "user": {"id": "test-user", "username": "Tester"},
            "expires_at": __import__("time").time() + 60,
        }
        routes = [
            "/api/guild/123456789012345/config/security",
            "/api/guild/123456789012345/config/welcome",
            "/api/guild/123456789012345/config/verification",
            "/api/guild/123456789012345/config/leveling",
            "/api/guild/123456789012345/config/tickets",
            "/api/guild/123456789012345/config/giveaway-templates",
            "/api/guild/123456789012345/config/ai-channel",
            "/api/guild/123456789012345/config/youtube-alerts",
            "/api/guild/123456789012345/config/backups",
            "/api/guild/123456789012345/config/command-permissions",
        ]
        try:
            with client.session_transaction() as sess:
                sess["air_sid"] = sid
            with mock.patch.object(web_dashboard, "_managed_guilds", return_value=[
                {"id": "123456789012345", "permissions": str(web_dashboard.MANAGE_GUILD)}
            ]):
                for route in routes:
                    with self.subTest(route=route):
                        response = client.post(route, json={})
                        self.assertEqual(response.status_code, 400)
                        self.assertEqual(response.get_json().get("error"), "csrf_failed")
        finally:
            web_dashboard._AUTH_SESSIONS.pop(sid, None)

if __name__ == "__main__":
    unittest.main()



class DashboardPanelWiringTests(unittest.TestCase):
    """Regression coverage for the missing-config-panels dashboard failure."""

    def test_authenticated_dashboard_renders_all_config_panels_and_api_routes(self):
        app = Flask(__name__, template_folder="../templates")
        app.secret_key = "test-only-secret"
        web_dashboard.register_dashboard(app, FakeBot())
        client = app.test_client()
        sid = "test-dashboard-panels"
        web_dashboard._AUTH_SESSIONS[sid] = {
            "access_token": "test-token",
            "user": {"id": "test-user", "username": "Tester"},
            "expires_at": __import__("time").time() + 60,
        }
        panel_ids = (
            "securityPanel", "welcomePanel", "verificationPanel", "ticketsPanel",
            "giveawayTemplatesPanel", "backupsPanel", "youtubeAlertsPanel",
            "aiChannelPanel", "levelingPanel", "commandPermissionsPanel",
        )
        api_paths = (
            "/api/guild/<guild_id>/config/security",
            "/api/guild/<guild_id>/config/welcome",
            "/api/guild/<guild_id>/config/verification",
            "/api/guild/<guild_id>/config/leveling",
            "/api/guild/<guild_id>/config/tickets",
            "/api/guild/<guild_id>/config/giveaway-templates",
            "/api/guild/<guild_id>/config/ai-channel",
            "/api/guild/<guild_id>/config/youtube-alerts",
            "/api/guild/<guild_id>/config/backups",
            "/api/guild/<guild_id>/config/command-permissions",
        )
        try:
            with client.session_transaction() as sess:
                sess["air_sid"] = sid
            response = client.get("/dashboard")
            self.assertEqual(response.status_code, 200)
            rendered = response.get_data(as_text=True)
            self.assertIn("async function chooseServer(server)", rendered)
            self.assertNotIn("function chooseServer(server)", rendered)
            for panel_id in panel_ids:
                with self.subTest(panel=panel_id):
                    self.assertIn(panel_id, rendered)
            for loader in (
                "loadSecurity(server)", "loadWelcome(server)", "loadVerification(server)",
                "loadLeveling(server)", "loadTickets(server)", "loadGiveawayTemplates(server)",
                "loadYouTubeAlerts(server)", "loadAIChannel(server)", "loadBackups(server)",
                "loadCommandPermissions(server)",
            ):
                with self.subTest(loader=loader):
                    self.assertIn(loader, rendered)
            registered_paths = {rule.rule for rule in app.url_map.iter_rules()}
            for api_path in api_paths:
                with self.subTest(api_path=api_path):
                    self.assertIn(api_path, registered_paths)
        finally:
            web_dashboard._AUTH_SESSIONS.pop(sid, None)
