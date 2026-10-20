import json
import os
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch
from src.cloud_sync import start_run, read_run, process_message, RUN_KEY, continuation_delay
from src.database import init_db, set_user_setting


def immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("Test unexpectedly waited for external I/O")


async def inline(function, *args, **kwargs):
    return function(*args, **kwargs)


class TestCloudQueue(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = os.path.join(self.temp.name, "queue_test.db")
        init_db(self.db)
        for name, value in (("asyncio.run", immediate), ("asyncio.to_thread", inline)):
            patcher = patch("src.cloud_sync." + name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.publisher = patch("src.cloud_sync.publish", new_callable=AsyncMock).start()
        self.addCleanup(patch.stopall)
        self.aggregator = Mock()
        self.aggregator.run_sync.return_value = {"status": "ok", "progress": {"has_more": True, "can_continue": True}}

    def begin(self, automatic=False):
        set_user_setting(self.db, "target_stack", "Kotlin, React, Kotlin")
        return start_run(self.db, automatic=automatic)["cloud_run"]["id"]

    def test_start_snapshots_production_matrix_and_multiple_clicks_share_run(self):
        run_id = self.begin()
        self.assertEqual(read_run(self.db)["queries"], ["Kotlin", "React"])
        self.assertNotIn("queries", start_run(self.db)["cloud_run"])
        self.assertEqual(start_run(self.db)["cloud_run"]["id"], run_id)
        self.publisher.assert_awaited_once()

    def test_no_browser_needed_for_successive_deliveries(self):
        run_id = self.begin()
        immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.assertEqual(read_run(self.db)["step"], 1)
        self.publisher.assert_awaited_with(run_id, 1, 1)
        immediate(process_message(self.db, {"run_id": run_id, "step": 1}, self.aggregator))
        self.assertEqual(self.aggregator.run_sync.call_count, 2)
        self.assertEqual(read_run(self.db)["step"], 2)

    def test_duplicate_or_stale_message_cannot_fork_continuation(self):
        run_id = self.begin()
        payload = {"run_id": run_id, "step": 0}
        immediate(process_message(self.db, payload, self.aggregator))
        immediate(process_message(self.db, payload, self.aggregator))
        immediate(process_message(self.db, {"run_id": "old", "step": 0}, self.aggregator))
        self.assertEqual(self.aggregator.run_sync.call_count, 1)

    def test_completed_run_does_not_publish_more_work(self):
        run_id = self.begin()
        self.aggregator.run_sync.return_value = {"status": "ok", "progress": {"has_more": False}}
        immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.assertEqual(read_run(self.db)["status"], "complete")
        self.publisher.assert_awaited_once()

    def test_cooldown_schedules_delayed_delivery_without_sleeping_worker(self):
        run_id = self.begin()
        self.aggregator.run_sync.return_value = {"status": "partial", "progress": {"has_more": True, "can_continue": False, "next_run_at": time.time() + 21600}}
        immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.assertEqual(read_run(self.db)["status"], "waiting")
        self.assertGreaterEqual(self.publisher.await_args.args[2], 21599)

    def test_failed_send_is_not_reported_as_accepted(self):
        self.publisher.side_effect = RuntimeError("queue quota")
        with self.assertRaisesRegex(RuntimeError, "no unattended run was accepted"):
            self.begin()
        self.assertEqual(read_run(self.db)["status"], "error")

    def test_ingestion_failure_redelivers_same_step(self):
        run_id = self.begin()
        self.aggregator.run_sync.return_value = {"status": "error", "error": "database offline"}
        with self.assertRaisesRegex(RuntimeError, "database offline"):
            immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.assertEqual(read_run(self.db)["step"], 0)
        self.publisher.assert_awaited_once()

    def test_failed_continuation_publish_can_retry_without_advancing_step(self):
        run_id = self.begin()
        self.publisher.side_effect = RuntimeError("temporary queue failure")
        with self.assertRaises(RuntimeError):
            immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.assertEqual(read_run(self.db)["step"], 0)
        self.publisher.side_effect = None
        immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.assertEqual(read_run(self.db)["step"], 1)

    def test_paused_auto_run_stops_without_affecting_manual_run(self):
        run_id = self.begin(automatic=True)
        set_user_setting(self.db, "auto_sync_enabled", "0")
        immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.assertEqual(read_run(self.db)["status"], "paused")
        self.aggregator.run_sync.assert_not_called()
        run_id = self.begin()
        immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.aggregator.run_sync.assert_called_once()

    def test_deadline_stops_unbounded_retries(self):
        run_id = self.begin()
        run = read_run(self.db)
        run["expires_at"] = time.time() - 1
        set_user_setting(self.db, RUN_KEY, json.dumps(run))
        immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.assertEqual(read_run(self.db)["status"], "partial")
        self.aggregator.run_sync.assert_not_called()
