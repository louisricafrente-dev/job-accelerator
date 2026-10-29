import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from src.database import init_db, get_user_setting, set_user_setting
from src import execution_inbox as inbox
from src.daily_schedule import has_unfinished, start_daily, send_digest
from src.connectors.remote_feed import UpworkConnector


class DailyScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "daily_test.db")
        init_db(self.db)

    def test_midnight_resumes_unfinished_and_duplicate_cron_is_ignored(self):
        set_user_setting(self.db, "sync_status", json.dumps({"progress": {"unfinished": True}}))
        start = Mock(return_value={"status": "queued"})
        start_daily(self.db, start)
        self.assertEqual(start_daily(self.db, start)["status"], "already_scheduled")
        start.assert_called_once_with(automatic=True, resume=True)

    def test_completed_queue_starts_fresh_despite_old_legacy_partial(self):
        set_user_setting(self.db, "sync_status", json.dumps({"progress": {"has_more": False, "unfinished": False}}))
        set_user_setting(self.db, "cloud_sync_run", json.dumps({"result": {"progress": {"unfinished": True}}}))
        self.assertFalse(has_unfinished(self.db))
        start = Mock(return_value={"status": "queued"})
        start_daily(self.db, start)
        start.assert_called_once_with(automatic=True, resume=False)

    def test_failed_start_can_retry_same_day(self):
        with self.assertRaises(RuntimeError):
            start_daily(self.db, Mock(side_effect=RuntimeError("network")))
        self.assertIsNone(get_user_setting(self.db, "daily_scrape_day"))
        start = Mock(return_value={"status": "queued"})
        start_daily(self.db, start)
        start.assert_called_once()

    def test_digest_once_per_day_failure_is_retryable(self):
        send = Mock(side_effect=[{"success": False}, {"success": True}])
        self.assertFalse(send_digest(self.db, send)["success"])
        self.assertTrue(send_digest(self.db, send)["success"])
        self.assertEqual(send_digest(self.db, send)["status"], "already_sent")
        self.assertEqual(send.call_count, 2)

    def test_resume_keeps_checkpoint_cycle_id(self):
        set_user_setting(self.db, "sync_batch_progress", json.dumps({"cycle_id": "unfinished-cycle"}))
        command = inbox.enqueue(self.db, resume=True, automatic=True)
        self.assertEqual(command["cycle_id"], "unfinished-cycle")
        self.assertNotEqual(command["id"], command["cycle_id"])

    def test_daily_worker_runs_only_unfinished_keyword(self):
        import hashlib
        from src.aggregator import Aggregator
        from src.connectors.base import BaseConnector
        from src.inbox_worker import run_claimed
        calls = []

        class Board(BaseConnector):
            platform = "Resume board"
            tier = 1

            def fetch(self, query="", location=""):
                calls.append(query)
                return []

        queries = ["python", "kotlin"]
        checkpoint = {"cycle_id": "yesterday", "signature": hashlib.sha256(json.dumps(queries).encode()).hexdigest(),
                      "boards": {"Resume board": {"cursor": 1, "retry": [], "next_at": 0}}}
        set_user_setting(self.db, "sync_batch_progress", json.dumps(checkpoint))
        inbox.enqueue(self.db, queries, automatic=True, resume=True)
        command = inbox.claim(self.db, "local", "pc")
        run_claimed(self.db, command, Aggregator(self.db, [Board()]))
        self.assertEqual(calls, ["kotlin"])
        self.assertEqual(inbox.read(self.db)["status"], "complete")

    def test_resumed_queue_includes_upwork_for_new_day(self):
        import hashlib
        from src.aggregator import Aggregator
        from src.inbox_worker import run_claimed
        checkpoint = {"cycle_id": "yesterday", "signature": hashlib.sha256(json.dumps(["developer"]).encode()).hexdigest(),
                      "boards": {"Upwork": {"cursor": 1, "retry": [], "next_at": 0, "daily_day": "old-day", "revision": 2}}}
        set_user_setting(self.db, "sync_batch_progress", json.dumps(checkpoint))
        inbox.enqueue(self.db, ["developer"], automatic=True, resume=True)
        command = inbox.claim(self.db, "local", "pc")
        board = UpworkConnector()
        with patch.dict(os.environ, {"FLCONSOLE_MCP_TOKEN": "test"}), patch(
                "src.connectors.upwork_flconsole.fetch_jobs", return_value=[]) as fetch:
            run_claimed(self.db, command, Aggregator(self.db, [board]))
        fetch.assert_called_once_with(board, limit=10)

    def test_upwork_daily_slot_not_consumed_by_manual_sync(self):
        connector = UpworkConnector()
        connector.db_path = self.db
        with patch.dict(os.environ, {"FLCONSOLE_MCP_TOKEN": "test"}), patch("src.connectors.upwork_flconsole.fetch_jobs", return_value=[]) as fetch:
            self.assertEqual(connector.fetch(), [])
            fetch.assert_not_called()
            connector.daily_sync = True
            connector.fetch()
            connector.fetch()
        fetch.assert_called_once_with(connector, limit=10)

    def test_midnight_during_manual_batch_runs_daily_upwork_before_completion(self):
        from src.aggregator import Aggregator
        from src.execution_dispatch import start
        from src.inbox_worker import run_claimed
        inbox.enqueue(self.db, ["developer"])
        command = inbox.claim(self.db, "local", "pc")
        aggregator = Aggregator(self.db, [UpworkConnector()])
        actual_run = aggregator.run_sync
        batches = []

        def overlap(**options):
            batches.append(aggregator.daily_run)
            result = actual_run(**options)
            if len(batches) == 1:
                start_daily(self.db, lambda **kwargs: start(self.db, **kwargs))
            return result

        with patch.dict(os.environ, {"GITHUB_ACTIONS_TOKEN": "test", "FLCONSOLE_MCP_TOKEN": "test"}), patch(
                "src.execution_dispatch.dispatch"), patch.object(aggregator, "run_sync", side_effect=overlap), patch(
                "src.connectors.upwork_flconsole.fetch_jobs", return_value=[]) as fetch:
            run_claimed(self.db, command, aggregator)
        self.assertEqual(batches, [False, True])
        fetch.assert_called_once()
        self.assertEqual(inbox.read(self.db)["status"], "complete")
        self.assertEqual(start_daily(self.db, Mock())["status"], "already_scheduled")

    def test_midnight_reuses_queued_manual_command_without_duplicate_dispatch(self):
        from src.aggregator import Aggregator
        from src.execution_dispatch import start
        from src.inbox_worker import run_claimed
        with patch.dict(os.environ, {"GITHUB_ACTIONS_TOKEN": "test", "FLCONSOLE_MCP_TOKEN": "test"}), patch(
                "src.execution_dispatch.dispatch") as dispatch, patch(
                "src.connectors.upwork_flconsole.fetch_jobs", return_value=[]) as fetch:
            manual = start(self.db, ["developer"])
            daily = start_daily(self.db, lambda **kwargs: start(self.db, **kwargs))
            self.assertEqual(manual["execution"]["id"], daily["execution"]["id"])
            self.assertFalse(inbox.read(self.db)["automatic"])
            command = inbox.claim(self.db, "local", "pc")
            run_claimed(self.db, command, Aggregator(self.db, [UpworkConnector()]))
        dispatch.assert_called_once()
        fetch.assert_called_once()


class DailyApiTests(unittest.TestCase):
    from tests.test_local_worker import TestLocalWorker as _Fixture
    setUp = _Fixture.setUp
    call = _Fixture.call

    def test_ten_am_digest_never_scrapes_even_if_auto_sync_paused(self):
        set_user_setting(self.db, "auto_sync_enabled", "0")
        with patch("scripts.daily_notifier.send_daily_email", return_value={"success": True}) as send, patch(
                "src.server.Aggregator.run_sync") as scrape, patch("src.execution_dispatch.dispatch") as dispatch:
            code, result = self.call("/api/notify/daily", admin=True)
            self.assertEqual(code, 200)
            self.assertTrue(result["success"])
            self.call("/api/notify/daily", admin=True)
        send.assert_not_called()
        scrape.assert_not_called()
        dispatch.assert_called_once()
        self.assertEqual(result["scan"]["window"], "24h")
        self.assertTrue(result["scan"]["digest"])

    def test_midnight_api_preserves_resume_cycle_and_schedules_only_once(self):
        set_user_setting(self.db, "sync_status", json.dumps({"progress": {"unfinished": True}}))
        set_user_setting(self.db, "sync_batch_progress", json.dumps({"cycle_id": "old-cycle"}))
        with patch.dict(os.environ, {"JOB_EXECUTOR": "database", "GITHUB_ACTIONS_TOKEN": "test-only"}), patch(
                "src.execution_dispatch.dispatch") as dispatch, patch("scripts.daily_notifier.send_daily_email") as send:
            code, result = self.call("/api/cron/sync", admin=True)
            self.assertEqual(code, 200)
            self.assertEqual(result["execution"]["cycle_id"], "old-cycle")
            self.call("/api/cron/sync", admin=True)
        dispatch.assert_called_once()
        send.assert_not_called()

    def test_vercel_has_exactly_one_scrape_and_one_digest_schedule(self):
        config = json.loads((Path(__file__).resolve().parents[1] / "vercel.json").read_text())
        self.assertEqual(config["crons"], [
            {"path": "/api/cron/sync", "schedule": "0 16 * * *"},
            {"path": "/api/notify/daily", "schedule": "0 2 * * *"},
        ])
