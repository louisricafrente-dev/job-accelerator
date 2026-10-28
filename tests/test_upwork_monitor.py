import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from src.database import init_db, get_user_setting, set_user_setting
from src.upwork_monitor import claim, poll_cloud, process, start, RUN_KEY


def run(coroutine):
    # All asynchronous I/O in these tests is mocked; no Windows loopback socket is needed.
    with patch("src.upwork_monitor.asyncio.to_thread", new_callable=AsyncMock,
               side_effect=lambda function, *args: function(*args)):
        try:
            coroutine.send(None)
        except StopIteration as done:
            return done.value
        raise AssertionError("Unexpected unmocked asynchronous I/O")


class UpworkMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "upwork_test.db")
        init_db(self.db)

    def test_shared_slot_prevents_local_cloud_overlap(self):
        self.assertTrue(claim(self.db, "local"))
        self.assertFalse(claim(self.db, "cloud"))
        self.assertFalse(claim(self.db, "local"))

    def test_auto_sync_pause_stops_both_workers(self):
        set_user_setting(self.db, "auto_sync_enabled", "0")
        self.assertFalse(claim(self.db, "local"))
        self.assertEqual(poll_cloud(self.db)["status"], "paused")

    def test_paused_monitor_stops_queue_and_resume_starts_new_chain(self):
        saved = {"id": "old", "step": 0, "next_at": time.time(), "deployment": ""}
        set_user_setting(self.db, RUN_KEY, json.dumps(saved))
        set_user_setting(self.db, "auto_sync_enabled", "0")
        with patch("src.upwork_monitor.publish", new_callable=AsyncMock) as publish:
            run(process(self.db, {"run_id": "old", "step": 0}))
            publish.assert_not_awaited()
            self.assertTrue(json.loads(get_user_setting(self.db, RUN_KEY))["paused"])
            set_user_setting(self.db, "auto_sync_enabled", "1")
            self.assertEqual(run(start(self.db))["status"], "queued")
            publish.assert_awaited_once()

    def test_cloud_yields_to_recent_local_poller_then_takes_over(self):
        set_user_setting(self.db, "upwork_local_seen", str(time.time()))
        with patch("src.connectors.upwork_flconsole.fetch_jobs", return_value=[]) as fetch:
            self.assertEqual(poll_cloud(self.db)["status"], "local_online")
            fetch.assert_not_called()
            set_user_setting(self.db, "upwork_local_seen", str(time.time() - 901))
            result = poll_cloud(self.db)
        self.assertEqual(result["source"], "cloud")
        self.assertEqual(result["error"], "")
        self.assertEqual(json.loads(get_user_setting(self.db, "upwork_feed_status"))["source"], "cloud")

    def test_repeated_start_does_not_fork_queue_and_old_delivery_is_ignored(self):
        with patch.dict(os.environ, {"VERCEL_DEPLOYMENT_ID": "test-deploy"}), patch(
                "src.upwork_monitor.publish", new_callable=AsyncMock) as publish:
            self.assertEqual(run(start(self.db))["status"], "queued")
            self.assertEqual(run(start(self.db))["status"], "already_running")
            publish.assert_awaited_once()
            saved_run = json.loads(get_user_setting(self.db, RUN_KEY))
            with patch("src.upwork_monitor.poll_cloud") as poll:
                run(process(self.db, {"run_id": "old", "step": 0}))
                poll.assert_not_called()
                run(process(self.db, {"run_id": saved_run["id"], "step": 0}))
                poll.assert_called_once()
            self.assertEqual(publish.await_args.args, (saved_run["id"], 1, 600))

    def test_failed_publish_retains_step_for_retry(self):
        saved_run = {"id": "test", "step": 0, "next_at": time.time()}
        set_user_setting(self.db, RUN_KEY, json.dumps(saved_run))
        with patch("src.upwork_monitor.poll_cloud"), patch(
                "src.upwork_monitor.publish", new_callable=AsyncMock, side_effect=RuntimeError("queue down")):
            with self.assertRaises(RuntimeError):
                run(process(self.db, {"run_id": "test", "step": 0}))
        self.assertEqual(json.loads(get_user_setting(self.db, RUN_KEY))["step"], 0)
