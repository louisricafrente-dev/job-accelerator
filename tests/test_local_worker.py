import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

from src.aggregator import Aggregator
from src.auth import create_session_token
from src.database import init_db, insert_jobs, get_jobs, get_user_setting, set_user_setting, acquire_sync_lease
from src.local_worker import request_local_sync, REQUEST_KEY, WORKER_KEY
from src.models import Job
from src.server import create_app

spec = importlib.util.spec_from_file_location("worker_under_test", Path(__file__).resolve().parents[1] / "scripts/local_worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class TestLocalWorker(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "cloud_test.db")
        self.local = str(Path(self.temp.name) / "local_test.db")
        init_db(self.db)
        init_db(self.local)
        self.env = patch.dict(os.environ, {"LOCAL_WORKER_TOKEN": "test-worker-token"})
        self.env.start()
        self.addCleanup(self.env.stop)
        with patch("src.aggregator.get_default_connectors", return_value=[]):
            self.app = create_app(self.db)
        self.admin = create_session_token("admin", "test-admin")
        self.worker_patch = patch.object(worker, "DB_PATH", self.local)
        self.worker_patch.start()
        self.addCleanup(self.worker_patch.stop)

    def call(self, path, method="GET", data=None, admin=False, extra=None):
        path, _, query = path.partition("?")
        raw = json.dumps(data).encode() if data is not None else b""
        env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
               "CONTENT_LENGTH": str(len(raw)), "CONTENT_TYPE": "application/json",
               "wsgi.input": io.BytesIO(raw), "wsgi.errors": io.StringIO(),
               "SERVER_NAME": "localhost", "SERVER_PORT": "80", "wsgi.url_scheme": "http",
               "wsgi.version": (1, 0), "wsgi.multithread": False, "wsgi.multiprocess": False,
               "wsgi.run_once": False,
               "HTTP_AUTHORIZATION": "Bearer " + (self.admin if admin else "test-worker-token")}
        env.update(extra or {})
        statuses = []
        result = b"".join(self.app(env, lambda status, headers, exc_info=None: statuses.append(status)))
        return int(statuses[0].split()[0]), json.loads(result)

    def heartbeat(self, active=""):
        return self.call("/api/local-worker/heartbeat", "POST", {"worker_id": "test-pc", "active_request_id": active})

    def claim(self):
        self.heartbeat()
        queued = request_local_sync(self.db, ["python developer"])
        status, body = self.call("/api/local-worker/request?worker_id=test-pc")
        self.assertEqual(status, 200)
        self.assertEqual(body["request"]["id"], queued["local_request"]["id"])
        return body["request"]

    def bridge(self, path, method="GET", data=None):
        status, body = self.call(path, method, data)
        if status != 200:
            raise RuntimeError(f"API {status}: {body}")
        return body

    def test_live_api_pipeline_uploads_updates_and_preserves_saved_status(self):
        job = Job("Junior Python Developer", "Example", "Remote", "Source A", 1,
                  "https://example.com/job", date_posted="today", description="Original")
        insert_jobs(self.local, [job])
        insert_jobs(self.db, [job])
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE jobs SET status='saved'")
        conn.commit()
        conn.close()
        req = self.claim()
        with patch.object(worker, "api_call", side_effect=self.bridge):
            worker.run_request(req, Aggregator(self.local, []))
        self.assertEqual(worker.pending_jobs(), [])
        self.assertEqual(json.loads(get_user_setting(self.db, REQUEST_KEY))["status"], "complete")
        self.assertFalse(get_user_setting(self.db, "sync_lease", ""))
        conn = sqlite3.connect(self.local)
        conn.execute("UPDATE jobs SET salary=?, description=?, sources=?", (
            "PHP 40,000", "Updated description with more details", json.dumps([
                {"platform": "Source A", "url": "https://example.com/job"},
                {"platform": "Source B", "url": "https://example.org/job"}])))
        conn.commit()
        conn.close()
        self.assertEqual(len(worker.pending_jobs()), 1)
        req = self.claim()
        with patch.object(worker, "api_call", side_effect=self.bridge):
            worker.run_request(req, Aggregator(self.local, []))
        row = get_jobs(self.db)[0]
        self.assertEqual(row["status"], "saved")
        self.assertEqual(row["salary"], "PHP 40,000")
        self.assertIn("Updated description", row["description"])
        self.assertIn("Source B", {source["platform"] for source in row["sources"]})

    def test_upload_failure_keeps_changes_pending(self):
        insert_jobs(self.local, [Job("Python Developer", "Example", "Remote", "A", 1, "https://example.com/job")])
        with patch.object(worker, "api_call", side_effect=OSError("network lost")):
            with self.assertRaises(OSError):
                worker.upload_pending("request", "test-pc")
        self.assertEqual(len(worker.pending_jobs()), 1)

    def test_retry_upload_uses_persisted_scrape_and_counts(self):
        insert_jobs(self.local, [Job("Python Developer", "Example", "Remote", "A", 1, "https://example.com/job")])
        req = self.claim()
        aggregator = Mock(connectors=[])
        aggregator.run_sync.return_value = {"status": "ok", "added": 1, "total_fetched": 1}
        def lose_completion(path, method="GET", data=None):
            if path.endswith("/complete"):
                raise OSError("connection lost before completion")
            return self.bridge(path, method, data)
        with patch.object(worker, "api_call", side_effect=lose_completion):
            with self.assertRaises(OSError):
                worker.run_request(req, aggregator)
        with patch.object(worker, "api_call", side_effect=self.bridge):
            worker.run_request(req, aggregator)
        aggregator.run_sync.assert_called_once()
        result = json.loads(get_user_setting(self.db, REQUEST_KEY))["result"]
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["uploaded"], 1)

    def test_partial_batch_retains_request_and_checkpoint_cycle(self):
        req = self.claim()
        aggregator = Mock(connectors=[])
        aggregator.run_sync.side_effect = [
            {"status": "ok", "progress": {"has_more": True, "next_run_at": time.time()}},
            {"status": "ok", "progress": {"has_more": False}},
        ]
        with patch.object(worker, "api_call", side_effect=self.bridge):
            self.assertTrue(worker.run_request(req, aggregator)["has_more"])
            self.assertEqual(json.loads(get_user_setting(self.db, REQUEST_KEY))["status"], "running")
            worker.run_request(req, aggregator)
        self.assertEqual(json.loads(get_user_setting(self.db, REQUEST_KEY))["status"], "complete")
        self.assertEqual([call.kwargs["cycle_id"] for call in aggregator.run_sync.call_args_list], [req["id"], req["id"]])

    def test_offline_request_is_interrupted_not_syncing(self):
        set_user_setting(self.db, REQUEST_KEY, json.dumps({"id": "old", "status": "running"}))
        set_user_setting(self.db, WORKER_KEY, json.dumps({"heartbeat_at": time.time() - 3600}))
        status, body = self.call("/api/sync/status", admin=True)
        self.assertEqual(status, 200)
        self.assertFalse(body["is_syncing"])
        self.assertEqual(body["local_request"]["status"], "interrupted")

    def test_idle_worker_does_not_override_newer_cloud_results(self):
        self.heartbeat()
        set_user_setting(self.db, REQUEST_KEY, json.dumps({"status": "complete", "result": {"added": 1}}))
        set_user_setting(self.db, "local_worker_telemetry", json.dumps({"last_result": {"added": 2}}))
        set_user_setting(self.db, "sync_status", json.dumps({"last_result": {"status": "ok", "added": 9}}))
        _, body = self.call("/api/sync/status", admin=True)
        self.assertEqual(body["last_result"]["added"], 9)

    def test_cloud_queue_stays_active_until_complete_or_stalled(self):
        now = time.time()
        run = {"id": "cloud", "status": "queued", "updated_at": now, "expires_at": now + 3600}
        set_user_setting(self.db, "cloud_sync_run", json.dumps(run))
        set_user_setting(self.db, REQUEST_KEY, json.dumps({"status": "running", "id": "offline-local"}))
        _, body = self.call("/api/sync/status", admin=True)
        self.assertTrue(body["is_syncing"])
        run["updated_at"] = now - 1000
        set_user_setting(self.db, "cloud_sync_run", json.dumps(run))
        _, body = self.call("/api/sync/status", admin=True)
        self.assertFalse(body["is_syncing"])
        self.assertEqual(body["cloud_run"]["status"], "stalled")

    def test_shared_lease_blocks_local_claim_and_cloud_execution(self):
        self.heartbeat()
        set_user_setting(self.db, REQUEST_KEY, json.dumps({"id": "queued", "status": "queued"}))
        lease = f"{int(time.time()) + 60}|cloud-worker"
        self.assertTrue(acquire_sync_lease(self.db, lease, int(time.time())))
        _, body = self.call("/api/local-worker/request?worker_id=test-pc")
        self.assertIsNone(body["request"])
        set_user_setting(self.db, "sync_lease", "0|expired")
        _, body = self.call("/api/local-worker/request?worker_id=test-pc")
        request = body["request"]
        self.assertFalse(acquire_sync_lease(self.db, lease, int(time.time())))
        _, beat = self.heartbeat(request["id"])
        self.assertTrue(beat["lease_valid"])
        set_user_setting(self.db, "sync_lease", lease)
        for route, payload in [("jobs", {"jobs": []}), ("complete", {"result": {"status": "ok"}})]:
            status, _ = self.call("/api/local-worker/" + route, "POST", {
                "request_id": request["id"], "worker_id": "test-pc", **payload})
            self.assertEqual(status, 409)
        self.assertEqual(get_user_setting(self.db, "sync_lease"), lease)

    def test_restart_recovers_expired_local_claim(self):
        set_user_setting(self.db, REQUEST_KEY, json.dumps({"id": "old", "status": "running", "worker_id": "dead", "lease_owner": "local:old:dead"}))
        set_user_setting(self.db, "sync_lease", "0|local:old:dead")
        self.heartbeat()
        _, body = self.call("/api/local-worker/request?worker_id=test-pc")
        self.assertEqual(body["request"]["worker_id"], "test-pc")
        self.assertEqual(body["request"]["status"], "running")

    def test_cron_header_alone_is_not_authorization(self):
        status, _ = self.call("/api/cron/sync", extra={"HTTP_AUTHORIZATION": "", "HTTP_X_VERCEL_CRON": "1"})
        self.assertEqual(status, 403)

    def test_second_worker_process_cannot_take_same_lock(self):
        with patch.object(worker, "LOCAL_DATA", Path(self.temp.name)):
            with worker.worker_lock():
                with self.assertRaises(OSError):
                    with worker.worker_lock():
                        self.fail("Duplicate worker acquired process lock")


if __name__ == "__main__":
    unittest.main()
