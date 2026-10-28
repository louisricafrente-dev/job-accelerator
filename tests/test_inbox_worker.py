import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from src import execution_inbox as inbox
from src.aggregator import Aggregator
from src.connectors.base import BaseConnector
from src.database import init_db, insert_jobs, get_jobs, get_user_setting, set_user_setting, set_sync_checkpoint, update_job_status
from src.inbox_worker import run_claimed, run_cloud, run_local
from src.models import Job


def listing(platform="Source A", url="https://example.com/job/a"):
    return Job("Junior Python Developer", "Example Company", "Remote", platform, 1, url,
               description="Python developer, fresh graduates welcome", date_posted=date.today().isoformat())


class Feed(BaseConnector):
    platform = "Source A"
    tier = 1
    is_feed = True

    def fetch(self, query="developer", location="remote"):
        return [listing()]


class InboxWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "execution_test.db")
        init_db(self.db)

    def test_local_execution_preserves_application(self):
        insert_jobs(self.db, [listing()])
        job = get_jobs(self.db)[0]
        update_job_status(self.db, job["id"], "applied", notes="Keep notes", pipeline_stage="interview")
        inbox.enqueue(self.db, ["developer"])
        command = inbox.claim(self.db, "local", "pc")
        result = run_claimed(self.db, command, Aggregator(self.db, [Feed()]))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(inbox.read(self.db)["status"], "complete")
        kept = get_jobs(self.db, status="applied")[0]
        self.assertEqual(kept["notes"], "Keep notes")
        self.assertEqual(kept["pipeline_stage"], "interview")

    def test_cancel_during_fetch_discards_results(self):
        class CancelledFeed(Feed):
            def fetch(inner, *args, **kwargs):
                inbox.cancel(self.db)
                return [listing()]
        inbox.enqueue(self.db, ["developer"])
        command = inbox.claim(self.db, "local", "pc")
        self.assertIsNone(run_claimed(self.db, command, Aggregator(self.db, [CancelledFeed()])))
        self.assertEqual(get_jobs(self.db), [])
        self.assertEqual(inbox.read(self.db)["status"], "cancelled")

    def test_database_fence_prevents_stale_writes(self):
        inbox.enqueue(self.db)
        guard = {**inbox.claim(self.db, "local", "pc"), "key": inbox.KEY}
        insert_jobs(self.db, [listing()], execution_guard=guard)
        self.assertEqual(len(get_jobs(self.db)), 1)
        set_sync_checkpoint(self.db, "old-checkpoint", "old-status", execution_guard=guard)
        inbox.cancel(self.db)
        insert_jobs(self.db, [listing("Source B", "https://example.com/job/b")], execution_guard=guard)
        set_sync_checkpoint(self.db, "stale-checkpoint", "stale-status", execution_guard=guard)
        self.assertEqual(get_user_setting(self.db, "sync_status"), "old-status")
        self.assertNotIn("Source B", get_jobs(self.db)[0]["sources"])
        extra = listing(url="https://example.com/job/other")
        extra.title = "Junior Kotlin Developer"
        insert_jobs(self.db, [extra], execution_guard=guard)
        self.assertEqual(len(get_jobs(self.db)), 1)

    def test_cloud_takes_offline_command(self):
        command = inbox.enqueue(self.db, ["developer"], now=time.time() - 91)
        result = run_cloud(self.db, command["id"], Aggregator(self.db, [Feed()]))
        self.assertEqual(result["added"], 1)
        self.assertEqual(inbox.read(self.db)["executor"], "cloud")

    def test_idle_worker_only_reads_small_inbox(self):
        stop = Mock()
        stop.is_set.side_effect = [False, True]
        with patch("src.inbox_worker.inbox.read", wraps=inbox.read) as read, patch("urllib.request.urlopen") as http:
            run_local(self.db, Aggregator(self.db, []), stop=stop)
        self.assertEqual(read.call_count, 1)
        stop.wait.assert_called_once_with(60)
        http.assert_not_called()

    def test_source_wait_loop_does_not_poll_database_every_quarter_second(self):
        import threading
        from src import sync_batches
        ready = threading.Event()
        self.addCleanup(ready.set)

        class SlowFeed(Feed):
            def fetch(inner, *args, **kwargs):
                if not ready.wait(5):
                    raise RuntimeError("Test did not release source")
                return [listing()]

        inbox.enqueue(self.db, ["developer"])
        aggregator = Aggregator(self.db, [SlowFeed()])
        aggregator.execution_guard = {**inbox.claim(self.db, "local", "pc"), "key": inbox.KEY}
        elapsed = [0]
        cycles = [0]
        actual_wait = sync_batches.wait

        def simulated_wait(futures, **kwargs):
            cycles[0] += 1
            elapsed[0] += 0.25
            if cycles[0] >= 100:
                ready.set()
            return actual_wait(futures, timeout=0.001, return_when=kwargs["return_when"])

        with patch("src.sync_batches.time.monotonic", side_effect=lambda: elapsed[0]), patch(
                "src.sync_batches.wait", side_effect=simulated_wait), patch(
                "src.execution_inbox.owned", wraps=inbox.owned) as reads:
            result = aggregator.run_sync(queries=["developer"], budget_seconds=30)
        self.assertEqual(result["added"], 1)
        self.assertGreaterEqual(cycles[0], 100)
        self.assertLessEqual(reads.call_count, 3)

    def test_automatic_pause_does_not_fetch(self):
        set_user_setting(self.db, "auto_sync_enabled", "0")
        inbox.enqueue(self.db, automatic=True)
        command = inbox.claim(self.db, "local", "pc")
        aggregator = Aggregator(self.db, [Feed()])
        with patch.object(aggregator, "run_sync") as fetch:
            run_claimed(self.db, command, aggregator)
        fetch.assert_not_called()
        self.assertEqual(inbox.read(self.db)["status"], "paused")

    def test_automatic_digest_is_not_resent_by_duplicate_cloud_supervisor(self):
        command = inbox.enqueue(self.db, ["developer"], automatic=True, now=time.time() - 91)
        aggregator = Aggregator(self.db, [Feed()])
        with patch("scripts.daily_notifier.send_daily_email", return_value={"success": True}) as send:
            run_cloud(self.db, command["id"], aggregator)
            run_cloud(self.db, command["id"], aggregator)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["new_jobs_count"], 1)

    def test_dispatch_is_idempotent(self):
        from src.execution_dispatch import start
        with patch.dict(os.environ, {"GITHUB_ACTIONS_TOKEN": "test-only"}), patch("src.execution_dispatch.dispatch") as send:
            first = start(self.db)
            second = start(self.db)
        self.assertEqual(first["execution"]["id"], second["execution"]["id"])
        send.assert_called_once()

    def test_failed_dispatch_retains_command(self):
        from src.execution_dispatch import start
        with patch.dict(os.environ, {"GITHUB_ACTIONS_TOKEN": "test-only"}), patch("src.execution_dispatch.dispatch", side_effect=RuntimeError("Unavailable")):
            with self.assertRaises(RuntimeError):
                start(self.db)
        self.assertEqual(inbox.read(self.db)["status"], "queued")
        self.assertNotIn("dispatched_at", inbox.read(self.db))


class DatabaseApiTests(unittest.TestCase):
    from tests.test_local_worker import TestLocalWorker as _Fixture
    setUp = _Fixture.setUp
    call = _Fixture.call

    def test_sync_only_dispatches_and_status_does_not_consult_heartbeat(self):
        with patch.dict(os.environ, {"JOB_EXECUTOR": "database", "GITHUB_ACTIONS_TOKEN": "test-only"}), patch("src.execution_dispatch.dispatch") as send:
            code, result = self.call("/api/sync", "POST", {"keywords": ["developer"]}, admin=True)
            self.assertEqual(code, 200)
            send.assert_called_once()
            with patch("src.local_worker.worker_status", side_effect=AssertionError("Old heartbeat path used")):
                code, status = self.call("/api/sync/status", admin=True)
            self.assertEqual(code, 200)
            self.assertTrue(status["is_syncing"])
            self.assertEqual(status["execution"]["id"], result["execution"]["id"])
            code, stopped = self.call("/api/sync", "POST", {"action": "stop"}, admin=True)
            self.assertEqual(code, 200)
            self.assertEqual(inbox.read(self.db)["status"], "stopped")

    def test_dispatch_configuration_error_is_recoverable_503(self):
        with patch.dict(os.environ, {"JOB_EXECUTOR": "database"}), patch("src.execution_dispatch.start", side_effect=RuntimeError("No token")):
            code, result = self.call("/api/sync", "POST", {}, admin=True)
        self.assertEqual(code, 503)
        self.assertEqual(result["status"], "error")

    def test_gmail_summary_does_not_include_message_bodies(self):
        code, result = self.call("/api/gmail/messages?summary=1", admin=True)
        self.assertEqual(code, 200)
        self.assertIn("total", result["stats"])
        self.assertNotIn("messages", result)
