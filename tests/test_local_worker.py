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
    def test_upwork_feed_requires_worker_auth_and_validates_source(self):
        payload = {"jobs": [{"platform": "Upwork", "title": "PHP Web Developer",
                              "description": "Build PHP and MySQL web apps",
                              "job_url": "https://www.upwork.com/jobs/~022114011265936675730"}]}
        code, _ = self.call("/api/local-worker/upwork", "POST", payload,
                            extra={"HTTP_AUTHORIZATION": "Bearer wrong"})
        self.assertEqual(code, 401)
        code, result = self.call("/api/local-worker/upwork", "POST", payload)
        self.assertEqual(code, 200)
        self.assertEqual(result["added"], 1)
        set_user_setting(self.db, "sync_status", json.dumps({"progress": {"boards": {
            "Upwork": {"last_error": "Configuration required: retired RSS"}}}}))
        code, status = self.call("/api/sync/status", admin=True)
        self.assertEqual(status["telemetry"]["Upwork"]["route"], "FLCONSOLE")
        self.assertEqual(status["progress"]["boards"]["Upwork"]["last_error"], "")
        code, result = self.call("/api/local-worker/upwork", "POST", payload)
        self.assertEqual(result["added"], 0)
        payload["jobs"][0]["job_url"] = "https://evil.example/jobs/~123"
        code, _ = self.call("/api/local-worker/upwork", "POST", payload)
        self.assertEqual(code, 400)

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

    def test_cooldown_finishes_partial_and_next_click_creates_a_fresh_request(self):
        req = self.claim()
        aggregator = Mock(connectors=[])
        aggregator.run_sync.return_value = {"status": "partial", "progress": {"has_more": False, "unfinished": True,
            "deferred_boards": [{"platform": "Blocked", "retry_at": time.time() + 21600}]}}
        with patch.object(worker, "api_call", side_effect=self.bridge):
            self.assertIsNone(worker.run_request(req, aggregator))
        completed = json.loads(get_user_setting(self.db, REQUEST_KEY))
        self.assertEqual(completed["status"], "partial")
        self.assertFalse(get_user_setting(self.db, "sync_lease", ""))
        queued = request_local_sync(self.db, ["python developer"])["local_request"]
        self.assertNotEqual(queued["id"], req["id"])
        repeated = request_local_sync(self.db, ["python developer"])["local_request"]
        self.assertEqual(repeated["id"], queued["id"])

    def test_resume_partial_run_keeps_cycle_and_completed_searches(self):
        req = self.claim()
        req.update(status="complete", completed_at=time.time(), requested_at=time.time() - 90000,
                   result={"status": "partial", "progress": {"has_more": True}})
        set_user_setting(self.db, REQUEST_KEY, json.dumps(req))
        resumed = request_local_sync(self.db, ["python developer"], resume=True)["local_request"]
        self.assertEqual(resumed["id"], req["id"])
        self.assertEqual(resumed["status"], "queued")
        self.assertGreater(resumed["requested_at"], req["requested_at"])
        self.assertNotIn("completed_at", resumed)
        _, claimed = self.call("/api/local-worker/request?worker_id=test-pc")
        self.assertEqual(claimed["request"]["id"], req["id"])

    def test_cumulative_counts_survive_empty_batch_and_reach_dashboard(self):
        req = self.claim()
        set_user_setting(self.local, "sync_batch_progress", json.dumps({"cycle_id": req["id"]}))
        set_user_setting(self.local, "local_worker_scrape_totals", json.dumps({
            "request_id": req["id"], "total_fetched": 42, "platforms": {"Source A": 42}}))
        set_user_setting(self.local, "local_worker_upload_totals", json.dumps({
            "request_id": req["id"], "sent": 20, "added": 5, "skipped": 15}))
        self.call("/api/local-worker/heartbeat", "POST", {
            "worker_id": "test-pc", "active_request_id": req["id"], "telemetry": worker.local_telemetry()})
        _, body = self.call("/api/sync/status", admin=True)
        self.assertEqual(body["run_totals"]["total_fetched"], 42)
        self.assertEqual(body["run_totals"]["added"], 5)
        set_user_setting(self.local, "sync_batch_progress", json.dumps({"cycle_id": "different-run"}))
        self.assertNotIn("run_totals", worker.local_telemetry())

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

    def test_midnight_cron_queues_cloud_even_when_local_worker_is_online(self):
        self.heartbeat()
        with patch("src.cloud_sync.start_run", return_value={"status": "queued", "cloud_run": {"id": "midnight"}}) as queue, patch(
            "src.local_worker.request_local_sync") as local:
            status, result = self.call("/api/cron/cloud-sync", admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(result["cloud_run"]["id"], "midnight")
        queue.assert_called_once_with(self.db, automatic=True)
        local.assert_not_called()

    def test_paired_worker_receives_saved_proxy_settings_without_public_exposure(self):
        self.heartbeat()
        set_user_setting(self.db, "proxy_mode", "hybrid")
        set_user_setting(self.db, "proxy_list", "http://example-user:example-password@proxy.example:80")
        status, body = self.call("/api/local-worker/request?worker_id=test-pc")
        self.assertEqual(status, 200)
        self.assertEqual(body["proxy_settings"]["proxy_mode"], "hybrid")
        self.assertIn("proxy.example", body["proxy_settings"]["proxy_list"])
        _, public = self.call("/api/sync/status", admin=True)
        self.assertNotIn("example-password", json.dumps(public))

    def test_midnight_cron_requires_secret_and_honors_pause(self):
        status, _ = self.call("/api/cron/cloud-sync")
        self.assertEqual(status, 403)
        with patch.dict(os.environ, {"CRON_SECRET": "test-cron"}), patch("src.cloud_sync.start_run", return_value={"status": "queued"}) as queue:
            status, _ = self.call("/api/cron/cloud-sync", extra={"HTTP_AUTHORIZATION": "Bearer test-cron"})
            self.assertEqual(status, 200)
            queue.assert_called_once()
            set_user_setting(self.db, "auto_sync_enabled", "0")
            _, result = self.call("/api/cron/cloud-sync", extra={"HTTP_AUTHORIZATION": "Bearer test-cron"})
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(queue.call_count, 1)

    def test_midnight_schedule_uses_manila_time_and_preserves_existing_schedule(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        config = json.loads((Path(__file__).resolve().parents[1] / "vercel.json").read_text())
        schedules = {job["path"]: job["schedule"] for job in config["crons"]}
        self.assertEqual(schedules["/api/cron/sync"], "0 1 * * *")
        self.assertEqual(schedules["/api/cron/cloud-sync"], "0 16 * * *")
        midnight = datetime(2026, 10, 21, 16, tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Manila"))
        self.assertEqual((midnight.hour, midnight.minute), (0, 0))

    def test_second_worker_process_cannot_take_same_lock(self):
        with patch.object(worker, "LOCAL_DATA", Path(self.temp.name)):
            with worker.worker_lock():
                with self.assertRaises(OSError):
                    with worker.worker_lock():
                        self.fail("Duplicate worker acquired process lock")


if __name__ == "__main__":
    unittest.main()
