import base64
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
import re
from unittest.mock import patch

from src.auth import resolve_guest_db_path, save_guest_changes, create_session_token, verify_session_token, _guest_sync_cache
from src.database import init_db, insert_jobs, get_jobs, get_stats, get_user_setting, set_user_setting, acquire_sync_lease, release_sync_lease, TursoConnection
from src.models import Job
from src.aggregator import Aggregator
from src.connectors.base import BaseConnector
from src.server import create_app
from tests.test_server_auth import wsgi_request


class QueryConnector(BaseConnector):
    platform = "Test Board"
    tier = 1

    def __init__(self):
        self.calls = []

    def fetch(self, query="", location=""):
        self.calls.append(query)
        return []


class TestRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.temp.name, "regression_test.db")
        init_db(self.db)
        self.app = create_app(self.db)
        self.cookie = "job_accel_session=" + create_session_token("admin", "review")

    def tearDown(self):
        _guest_sync_cache.clear()
        self.temp.cleanup()

    def job(self, url="https://example.com/1", location="Manila", **kwargs):
        return Job("Android Developer", "Example", location, "LinkedIn", 1, url, **kwargs)

    def test_known_fallback_signature_is_rejected(self):
        raw = json.dumps({"role": "admin", "id": "review", "exp": int(time.time()) + 1000}).encode()
        payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        signature = hmac.new(b"job-accel-auth-secret-key-2026-secure-session", payload.encode(), hashlib.sha256).hexdigest()
        self.assertIsNone(verify_session_token(payload + "." + signature))

    def test_forged_cron_header_rejected(self):
        env = {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/notify/daily", "QUERY_STRING": "", "wsgi.input": None, "HTTP_X_VERCEL_CRON": "1"}
        result = self.app._handle(env)
        self.assertIn("Forbidden", "".join(result))

    def test_real_cron_secret_accepted_without_dispatch(self):
        import sys
        import types
        sender = types.ModuleType("scripts.daily_notifier")
        sender.send_daily_email = lambda path: {"success": True, "mocked": True}
        with patch.dict(os.environ, {"CRON_SECRET": "review-cron"}), patch.dict(sys.modules, {"scripts.daily_notifier": sender}):
            result = self.app._handle({"REQUEST_METHOD": "GET", "PATH_INFO": "/api/notify/daily", "QUERY_STRING": "", "wsgi.input": None, "HTTP_AUTHORIZATION": "Bearer review-cron"})
            self.assertTrue(json.loads("".join(result))["mocked"])

    def test_distinct_same_board_requisitions_survive(self):
        insert_jobs(self.db, [self.job(date_posted="2026-10-10"), self.job("https://example.com/2", date_posted="2026-10-16"), self.job("https://example.com/3", "Cebu", date_posted="2026-10-10")])
        self.assertEqual(get_stats(self.db)["total"], 3)

    def test_pagination_reaches_every_job(self):
        insert_jobs(self.db, [Job(f"Developer {i}", "Example", "Manila", "LinkedIn", 1, f"https://example.com/{i}") for i in range(205)])
        first = wsgi_request(self.app, "GET", "/api/jobs?limit=200", cookie=self.cookie)["json"]
        second = wsgi_request(self.app, "GET", "/api/jobs?limit=200&offset=200", cookie=self.cookie)["json"]
        self.assertEqual(first["total"], 205)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertEqual(len({j["id"] for j in first["jobs"] + second["jobs"]}), 205)

    def test_wal_jobs_and_stable_ids_reach_guest(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("PRAGMA wal_autocheckpoint=0")
            insert_jobs(self.db, [self.job(date_posted="2026-10-10")])
            conn.execute("UPDATE jobs SET id=42")
            conn.commit()
            guest = resolve_guest_db_path("guest_wal", self.db)
            self.assertEqual(get_jobs(guest)[0]["id"], 42)
            insert_jobs(self.db, [self.job("https://example.com/2", date_posted="2026-10-16")])
            _guest_sync_cache.clear()
            resolve_guest_db_path("guest_wal", self.db)
            self.assertEqual(get_stats(guest)["total"], 2)
        finally:
            conn.close()

    def test_guest_state_survives_instance_recreation_without_master_edits(self):
        insert_jobs(self.db, [self.job()])
        guest = resolve_guest_db_path("guest_cold", self.db)
        save_guest_changes("guest_cold", self.db, 1, {"status": "applied", "notes": "private guest note"})
        set_user_setting(self.db, "guest:guest_cold:setting:target_stack", "Kotlin")
        os.remove(guest)
        _guest_sync_cache.clear()
        recreated = resolve_guest_db_path("guest_cold", self.db)
        self.assertEqual(get_jobs(recreated)[0]["notes"], "private guest note")
        self.assertEqual(get_jobs(recreated)[0]["status"], "applied")
        self.assertEqual(get_user_setting(recreated, "target_stack"), "Kotlin")
        self.assertEqual(get_jobs(self.db)[0]["status"], "new")
        self.assertIsNone(get_jobs(self.db)[0]["notes"])

    def test_invalid_status_stage_and_date_rejected(self):
        insert_jobs(self.db, [self.job()])
        for body in ({"status": "bad"}, {"stage": "bad"}, {"follow_up_date": "2026-99-99"}, {"status": []}):
            result = wsgi_request(self.app, "POST", "/api/jobs/1/status", body, cookie=self.cookie)
            self.assertEqual(result["status"], 400)
        self.assertEqual(get_jobs(self.db)[0]["status"], "new")

    def test_secrets_not_returned_or_overwritten_by_settings(self):
        set_user_setting(self.db, "smtp_password", "private-test-value")
        response = wsgi_request(self.app, "GET", "/api/settings", cookie=self.cookie)
        self.assertNotIn("smtp_password", response["json"])
        response = wsgi_request(self.app, "POST", "/api/settings", {"smtp_password": "changed"}, cookie=self.cookie)
        self.assertEqual(get_user_setting(self.db, "smtp_password"), "private-test-value")

    def test_new_keywords_invalidate_cache(self):
        connector = QueryConnector()
        aggregator = Aggregator(self.db, [connector])
        aggregator.run_sync(["react developer"])
        calls = len(connector.calls)
        aggregator.run_sync(["python developer"])
        self.assertGreater(len(connector.calls), calls)
        self.assertIn("python developer", connector.calls)

    def test_cloud_batches_preserve_merging_and_workflow(self):
        from types import SimpleNamespace
        sql = sqlite3.connect(self.db)

        class Client:
            def execute(self, query, params=None):
                cursor = sql.execute(query, params or [])
                rows = cursor.fetchall() if cursor.description else []
                result = SimpleNamespace(columns=[c[0] for c in cursor.description] if cursor.description else [], rows=rows, rows_affected=max(0, cursor.rowcount), last_insert_rowid=cursor.lastrowid)
                sql.commit()
                return result

            def batch(self, statements):
                return [self.execute(query, params) for query, params in statements]

            def close(self):
                pass

        client = Client()
        first = self.job()
        second = Job(first.title, first.company, first.location, "Indeed", 1, "https://indeed.example/1")
        try:
            with patch("src.database.get_db_connection", side_effect=lambda *args, **kwargs: TursoConnection(client)):
                added, skipped = insert_jobs(self.db, [first, second, self.job("https://example.com/2", "Cebu")])
            self.assertEqual((added, skipped), (2, 1))
            rows = get_jobs(self.db)
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(next(row for row in rows if row["location"] == "Manila")["sources"]), 2)
        finally:
            sql.close()

    def test_ingestion_failure_visible_to_another_instance(self):
        aggregator = Aggregator(self.db, [])
        with patch("src.aggregator.insert_jobs", side_effect=RuntimeError("database unavailable")):
            self.assertEqual(aggregator.run_sync()["status"], "error")
        other = Aggregator(self.db, [])
        self.assertEqual(other.get_telemetry()["last_result"]["status"], "error")
        self.assertEqual(aggregator.last_sync_time, 0)

    def test_sync_lease_is_exclusive_and_owner_checked(self):
        now = int(time.time())
        self.assertTrue(acquire_sync_lease(self.db, f"{now+600}|first", now))
        self.assertFalse(acquire_sync_lease(self.db, f"{now+600}|second", now))
        release_sync_lease(self.db, f"{now+600}|second")
        self.assertFalse(acquire_sync_lease(self.db, f"{now+600}|second", now))
        release_sync_lease(self.db, f"{now+600}|first")
        self.assertTrue(acquire_sync_lease(self.db, f"{now+600}|second", now))

    def test_serverless_sync_waits_for_result(self):
        with patch.dict(os.environ, {"VERCEL": "1", "TURSO_AUTH_TOKEN": "test", "TURSO_DATABASE_URL": "https://unused.example"}), patch("src.server.Aggregator.run_sync", return_value={"status": "ok", "added": 0}) as run:
            result = wsgi_request(self.app, "POST", "/api/sync", {"background": True}, cookie=self.cookie)
            self.assertEqual(result["json"]["status"], "ok")
            run.assert_called_once()

    def test_sync_accepts_every_frontend_preset(self):
        source = (Path(__file__).parents[1] / "src/static/app.js").read_text(encoding="utf-8")
        catalog = source.split("const PRESET_CATEGORIES =", 1)[1].split("const PRESET_SKILLS =", 1)[0]
        keywords = [skill for group in re.findall(r"skills:\s*\[(.*?)\]", catalog, re.S) for skill in re.findall(r'"([^"\n]+)"', group)]
        self.assertGreater(len(keywords), 100)
        with patch("src.server.Aggregator.run_sync", return_value={"status": "ok", "added": 0}) as run:
            result = wsgi_request(self.app, "POST", "/api/sync", {"keywords": keywords}, cookie=self.cookie)
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["json"]["status"], "ok")
        self.assertEqual(run.call_args.kwargs["queries"], list(dict.fromkeys(keywords)))

    def test_invalid_sync_payloads_return_json_errors(self):
        for keywords in (["skill"] * 1001, [None], [""], "x" * 201, ["x" * 200] * 60, 42):
            with self.subTest(keywords_type=type(keywords).__name__):
                result = wsgi_request(self.app, "POST", "/api/sync", {"keywords": keywords}, cookie=self.cookie)
                self.assertEqual(result["status"], 400)
                self.assertEqual(result["json"]["status"], "error")
                self.assertTrue(result["json"]["error"])
        result = wsgi_request(self.app, "POST", "/api/sync", "[]", cookie=self.cookie)
        self.assertEqual(result["status"], 400)
        self.assertEqual(result["json"]["error"], "JSON body must be an object")


if __name__ == "__main__":
    unittest.main()
