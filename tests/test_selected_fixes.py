import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from src.auth import create_session_token
from src.database import init_db, set_user_setting
from src.server import create_app
from tests.test_server_auth import wsgi_request


class TestSelectedFixes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = os.path.join(self.temp.name, "selected_test.db")
        init_db(self.db)
        self.app = create_app(self.db)
        self.admin = "job_accel_session=" + create_session_token("admin", "review")

    def test_guest_login_and_existing_sessions_are_disabled(self):
        self.assertEqual(wsgi_request(self.app, "POST", "/api/auth/login-guest", {})["status"], 403)
        cookie = "job_accel_session=" + create_session_token("guest", "existing")
        with patch("src.server.resolve_guest_db_path") as resolve:
            for path in ("/api/jobs", "/api/stats", "/api/settings", "/api/jobs/export/csv"):
                self.assertEqual(wsgi_request(self.app, "GET", path, cookie=cookie)["status"], 401)
            self.assertFalse(wsgi_request(self.app, "GET", "/api/auth/status", cookie=cookie)["json"]["authenticated"])
            resolve.assert_not_called()
        self.assertEqual(wsgi_request(self.app, "GET", "/api/stats", cookie=self.admin)["status"], 200)

    def test_cloud_pause_skips_scrape_but_manual_sync_still_works(self):
        set_user_setting(self.db, "auto_sync_enabled", "0")
        with patch("src.server.Aggregator.run_sync", return_value={"status": "ok", "added": 0}) as run:
            for path in ("/api/cron/sync", "/api/sync/cron"):
                response = wsgi_request(self.app, "GET", path, cookie=self.admin)
                self.assertEqual(response["json"]["status"], "skipped")
            run.assert_not_called()
            self.assertEqual(wsgi_request(self.app, "POST", "/api/sync", {}, cookie=self.admin)["json"]["status"], "ok")
            run.assert_called_once()

    def test_cron_outcomes_match_sync_result(self):
        for status, expected, http in (("ok", "success", 200), ("partial", "partial", 200),
                                       ("error", "error", 500), ("already_syncing", "already_syncing", 200)):
            with self.subTest(status=status), patch("src.server.Aggregator.run_sync", return_value={"status": status, "added": 0}):
                response = wsgi_request(self.app, "GET", "/api/cron/sync", cookie=self.admin)
                self.assertEqual(response["json"]["status"], expected)
                self.assertEqual(response["status"], http)

    def test_health_is_public_and_identifies_service(self):
        response = wsgi_request(self.app, "GET", "/api/health")
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["json"], {"service": "job-accelerator", "status": "ok"})

    def test_settings_api_rejects_late_revision_and_hides_internal_metadata(self):
        for value, revision in (("newest", 200), ("stale", 100)):
            response = wsgi_request(self.app, "POST", "/api/settings", {"view_filters": value, "__revisions": {"view_filters": revision}}, cookie=self.admin)
            self.assertEqual(response["status"], 200)
        settings = wsgi_request(self.app, "GET", "/api/settings", cookie=self.admin)["json"]
        self.assertEqual(settings["view_filters"], "newest")
        self.assertNotIn("__revisions", settings)
        for revisions in ([], {"view_filters": True}, {"view_filters": -1}, {"view_filters": "200"}):
            self.assertEqual(wsgi_request(self.app, "POST", "/api/settings", {"view_filters": "invalid", "__revisions": revisions}, cookie=self.admin)["status"], 400)

    def test_email_failure_makes_successful_sync_partial(self):
        import sys
        from types import ModuleType
        notifier = ModuleType("scripts.daily_notifier")
        notifier.send_daily_email = lambda **kwargs: {"success": False, "error": "mock email failure"}
        with patch.dict(sys.modules, {"scripts.daily_notifier": notifier}), patch("src.server.Aggregator.run_sync", return_value={"status": "ok", "added": 1}):
            response = wsgi_request(self.app, "GET", "/api/cron/sync", cookie=self.admin)
            self.assertEqual(response["json"]["status"], "partial")
            self.assertEqual(response["json"]["sync_stats"]["status"], "ok")


class TestLauncher(unittest.TestCase):
    def test_running_app_is_opened_without_restart(self):
        import run
        health = io.BytesIO(json.dumps({"service": "job-accelerator", "status": "ok"}).encode())
        with patch.object(run, "init_db"), patch.object(run, "get_stats", return_value={"total": 1, "new": 1, "applied": 0}), patch("urllib.request.urlopen", return_value=health), patch.object(run, "open_browser") as browser, patch.object(run, "create_app") as create, patch("time.sleep"), patch("subprocess.call") as terminate:
            run.main()
            browser.assert_called_once()
            create.assert_not_called()
            terminate.assert_not_called()

    def test_unknown_listener_is_left_running(self):
        import run
        with patch.object(run, "init_db"), patch.object(run, "get_stats", return_value={"total": 1, "new": 1, "applied": 0}), patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("local", 401, "Unauthorized", {}, None)), patch("socket.create_connection"), patch.object(run, "create_app") as create, patch("subprocess.call") as terminate:
            run.main()
            create.assert_not_called()
            terminate.assert_not_called()
