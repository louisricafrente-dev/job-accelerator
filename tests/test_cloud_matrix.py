import os
import tempfile
import unittest
from unittest.mock import patch

from src.aggregator import Aggregator
from src.auth import create_session_token
from src.connectors.base import BaseConnector
from src.database import init_db, set_user_setting
from src.server import create_app
from tests.test_server_auth import wsgi_request


class RecordingConnector(BaseConnector):
    platform = "Matrix test"
    tier = 1

    def __init__(self):
        self.calls = []

    def fetch(self, query="", location=""):
        self.calls.append(query)
        return []


class TestCloudMatrix(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = os.path.join(self.temp.name, "matrix_test.db")
        init_db(self.db)
        self.connector = RecordingConnector()

    def test_automatic_sync_uses_all_saved_keywords_and_refreshes_after_edit(self):
        aggregator = Aggregator(self.db, [self.connector])
        set_user_setting(self.db, "target_stack", "React, Kotlin, QA Automation, React", revision=100)
        with patch("src.aggregator.time.sleep"):
            aggregator.run_sync(force=True)
            self.assertEqual(self.connector.calls, ["React", "Kotlin", "QA Automation"])
            set_user_setting(self.db, "daily_scrape_day", "")
            self.connector.calls.clear()
            set_user_setting(self.db, "target_stack", "Next.js, Java", revision=200)
            aggregator.run_sync(force=True)
            self.assertEqual(self.connector.calls, ["Next.js", "Java"])

    def test_manual_queries_override_saved_matrix(self):
        set_user_setting(self.db, "target_stack", "Kotlin")
        with patch("src.aggregator.time.sleep"):
            Aggregator(self.db, [self.connector]).run_sync(["React"], force=True)
        self.assertEqual(self.connector.calls, ["React"])

    def test_defaults_only_used_without_nonempty_saved_matrix(self):
        for saved in (None, "", " , , "):
            set_user_setting(self.db, "daily_scrape_day", "")
            self.connector.calls.clear()
            if saved is not None:
                set_user_setting(self.db, "target_stack", saved)
            with patch("src.aggregator.time.sleep"):
                Aggregator(self.db, [self.connector]).run_sync(force=True)
            self.assertIn("junior developer", self.connector.calls)

    def test_both_cloud_cron_aliases_use_persisted_matrix(self):
        set_user_setting(self.db, "target_stack", "Kotlin, React, TypeScript", revision=100)
        with patch("src.aggregator.get_default_connectors", return_value=[self.connector]):
            app = create_app(self.db)
        cookie = "job_accel_session=" + create_session_token("admin", "matrix-admin")
        for route in ("/api/cron/sync", "/api/sync/cron"):
            set_user_setting(self.db, "sync_batch_progress", "")
            set_user_setting(self.db, "daily_scrape_day", "")
            self.connector.calls.clear()
            with patch("src.sync_batches.QUERY_DELAY_SECONDS", 0):
                result = wsgi_request(app, "GET", route, cookie=cookie)
            self.assertEqual(result["status"], 200)
            self.assertEqual(self.connector.calls, ["Kotlin", "React", "TypeScript"])
