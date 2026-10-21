import json
import os
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch
from src.cloud_sync import start_run, read_run, process_message, RUN_KEY, continuation_delay, public_run
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

    def test_expired_run_resumes_original_search_cycle(self):
        original = self.begin()
        run = read_run(self.db)
        run.update(status="partial", expires_at=time.time() - 1)
        set_user_setting(self.db, RUN_KEY, json.dumps(run))
        resumed = self.begin()
        self.assertNotEqual(resumed, original)
        immediate(process_message(self.db, {"run_id": resumed, "step": 0}, self.aggregator))
        self.assertEqual(self.aggregator.run_sync.call_args.kwargs["cycle_id"], original)

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

    def stale_run(self):
        run_id = self.begin()
        run = read_run(self.db)
        run["updated_at"] = time.time() - 700
        set_user_setting(self.db, RUN_KEY, json.dumps(run))
        return run_id

    def test_stale_queue_republishes_without_resetting_queries(self):
        run_id = self.stale_run()
        start_run(self.db, queries=["Different"])
        run = read_run(self.db)
        self.assertEqual(run["id"], run_id)
        self.assertEqual(run["queries"], ["Kotlin", "React"])
        self.assertEqual(run["step"], 1)
        self.publisher.assert_awaited_with(run_id, 1, 1)
        immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.aggregator.run_sync.assert_not_called()
        immediate(process_message(self.db, {"run_id": run_id, "step": 1}, self.aggregator))
        self.aggregator.run_sync.assert_called_once()

    def test_failed_recovery_keeps_original_step(self):
        self.stale_run()
        self.publisher.side_effect = RuntimeError("queue unavailable")
        with self.assertRaisesRegex(RuntimeError, "Could not recover"):
            start_run(self.db)
        self.assertEqual(read_run(self.db)["step"], 0)

    def test_delayed_cooldown_is_not_stalled_or_republished(self):
        self.stale_run()
        run = read_run(self.db)
        run.update(status="waiting", next_at=time.time() + 21600)
        set_user_setting(self.db, RUN_KEY, json.dumps(run))
        self.assertEqual(public_run(run)["status"], "waiting")
        start_run(self.db)
        self.publisher.assert_awaited_once()

    def test_stale_and_expired_runs_are_reported_truthfully(self):
        self.stale_run()
        run = read_run(self.db)
        self.assertEqual(public_run(run)["status"], "stalled")
        run["expires_at"] = time.time() - 1
        self.assertEqual(public_run(run)["status"], "partial")

    def test_recovery_does_not_interrupt_live_worker(self):
        self.stale_run()
        set_user_setting(self.db, "cloud_sync_worker_lease", f"{int(time.time())+360}|busy")
        self.assertEqual(start_run(self.db)["status"], "already_syncing")
        self.publisher.assert_awaited_once()

    def test_simultaneous_worker_retries_instead_of_forking(self):
        run_id = self.begin()
        set_user_setting(self.db, "cloud_sync_worker_lease", f"{int(time.time())+360}|busy")
        with self.assertRaisesRegex(RuntimeError, "Another cloud worker"):
            immediate(process_message(self.db, {"run_id": run_id, "step": 0}, self.aggregator))
        self.aggregator.run_sync.assert_not_called()

    def test_api_callback_registers_vercel_assigned_consumer_group(self):
        import importlib
        callback = importlib.import_module("api.queue_worker")
        with patch.object(callback, "subscribe") as register, patch.object(callback, "accept_and_handle", new_callable=AsyncMock) as accept:
            immediate(callback.handle_delivery(b"{}", {"Ce-VqsConsumerGroup": "test-deployment-consumer"}))
            immediate(callback.handle_delivery(b"{}", {"ce-vqsconsumergroup": "test-deployment-consumer"}))
            register.assert_called_once()
            self.assertEqual(str(register.call_args.kwargs["consumer_group"]), "test-deployment-consumer")
            self.assertEqual(accept.await_count, 2)

    def test_api_callback_rejects_missing_delivery_metadata(self):
        from api.queue_worker import handle_delivery
        with self.assertRaisesRegex(ValueError, "Missing queue consumer"):
            immediate(handle_delivery(b"{}", {}))

    def test_redeploy_requeues_same_cycle_and_preserves_future_cooldown(self):
        with patch.dict(os.environ, {"VERCEL_DEPLOYMENT_ID": "deployment-old"}):
            run_id = self.begin()
        run = read_run(self.db)
        run.update(status="waiting", next_at=time.time() + 3600)
        set_user_setting(self.db, RUN_KEY, json.dumps(run))
        with patch.dict(os.environ, {"VERCEL_DEPLOYMENT_ID": "deployment-new"}):
            self.assertEqual(public_run(run)["status"], "waiting")
            start_run(self.db)
        recovered = read_run(self.db)
        self.assertEqual(recovered["id"], run_id)
        self.assertEqual(recovered["deployment_id"], "deployment-new")
        self.assertEqual(recovered["status"], "waiting")
        self.assertGreaterEqual(self.publisher.await_args.args[2], 3599)
