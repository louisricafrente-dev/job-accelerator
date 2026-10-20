import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.aggregator import Aggregator
from src.connectors.base import BaseConnector
from src.database import init_db, get_jobs, get_user_setting, set_user_setting
from src.models import Job
from src.sync_batches import PROGRESS_KEY


class Clock:
    value = 0

    def monotonic(self):
        return self.value

    def time(self):
        return 2000000000 + self.value


class Board(BaseConnector):
    platform = "Batch board"
    tier = 1

    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.error = ""

    def fetch(self, query="", location=""):
        self.calls.append(query)
        self.clock.value += 2
        if self.error:
            raise RuntimeError(self.error)
        return [Job("Junior Android Developer", "Example", "Remote", self.platform, 1,
                    f"https://example.com/{query or 'feed'}", date_posted="today")]


class TestSyncBatches(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = os.path.join(self.temp.name, "batch_test.db")
        init_db(self.db)
        self.clock = Clock()
        self.board = Board(self.clock)
        for name, value in (("time.monotonic", self.clock.monotonic), ("time.time", self.clock.time), ("QUERY_DELAY_SECONDS", 0)):
            patcher = patch("src.sync_batches." + name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_batch(self, keywords, board=None, budget=3):
        from src.sync_batches import run_batch
        return run_batch(Aggregator(self.db, [board or self.board]), keywords, budget_seconds=budget, workers=1)

    def test_all_295_keywords_eventually_complete_without_restarting(self):
        keywords = [f"keyword-{i}" for i in range(295)]
        for _ in range(150):
            result = self.run_batch(keywords)
            if not result["progress"]["has_more"]:
                break
        self.assertEqual(self.board.calls, keywords)
        self.assertEqual(len(get_jobs(self.db, limit=500)), 295)
        self.assertEqual(result["progress"]["completed_searches"], 295)
        self.run_batch(keywords)
        self.assertEqual(len(self.board.calls), 295, "finished board must respect refresh cooldown")

    def test_budget_saves_progress_and_results_between_instances(self):
        first = self.run_batch(["a", "b", "c", "d"])
        self.assertEqual(first["progress"]["completed_searches"], 2)
        self.assertEqual(len(get_jobs(self.db)), 2)
        self.assertTrue(first["progress"]["has_more"])
        second = self.run_batch(["a", "b", "c", "d"])
        self.assertEqual(self.board.calls, ["a", "b", "c", "d"])
        self.assertFalse(second["progress"]["has_more"])

    def test_matrix_change_resets_queries_but_not_feed_cooldown(self):
        feed = Board(self.clock)
        feed.platform = "Feed"
        feed.is_feed = True
        self.run_batch(["a"], board=feed)
        self.run_batch(["different"], board=feed)
        self.assertEqual(len(feed.calls), 1)
        self.clock.value += 6 * 3600 + 1
        self.run_batch(["different"], board=feed)
        self.assertEqual(len(feed.calls), 2)

    def test_blocked_board_is_deferred_and_retry_is_preserved(self):
        self.board.error = "HTTP 429"
        result = self.run_batch(["a", "b"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["progress"]["completed_searches"], 0)
        self.run_batch(["a", "b"])
        self.assertEqual(self.board.calls, ["a"])
        self.clock.value += 6 * 3600 + 1
        self.board.error = ""
        self.run_batch(["a", "b"], budget=10)
        self.assertEqual(self.board.calls, ["a", "b", "a"])

    def test_ingestion_failure_does_not_advance_the_checkpoint(self):
        with patch("src.sync_batches.insert_jobs", side_effect=RuntimeError("offline database")):
            result = self.run_batch(["a", "b"])
        self.assertEqual(result["status"], "error")
        checkpoint = json.loads(get_user_setting(self.db, PROGRESS_KEY))
        self.assertEqual(checkpoint["boards"][self.board.platform]["cursor"], 0)

    def test_feed_does_not_repeat_for_each_keyword(self):
        self.board.is_feed = True
        result = self.run_batch(["a", "b", "c"], budget=100)
        self.assertEqual(self.board.calls, [""])
        self.assertEqual(result["added"], 1)

    def test_force_cannot_bypass_shared_refresh_cooldown(self):
        self.run_batch(["a"])
        Aggregator(self.db, [self.board]).run_sync(["a"], force=True, budget_seconds=10)
        self.assertEqual(self.board.calls, ["a"])

    def test_board_rotation_survives_short_runs(self):
        from src.sync_batches import run_batch
        second = Board(self.clock)
        second.platform = "Second board"
        for _ in range(2):
            run_batch(Aggregator(self.db, [self.board, second]), ["a", "b"], budget_seconds=1, workers=1)
        self.assertEqual(self.board.calls, ["a"])
        self.assertEqual(second.calls, ["a"])

    def test_saved_results_survive_checkpoint_write_failure(self):
        from src.sync_batches import set_sync_checkpoint as real_write
        writes = 0

        def crash_after_ingestion(db, checkpoint, status):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise RuntimeError("simulated instance failure")
            return real_write(db, checkpoint, status)

        with patch("src.sync_batches.set_sync_checkpoint", side_effect=crash_after_ingestion):
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                self.run_batch(["a", "b"])
        self.assertEqual(len(get_jobs(self.db)), 1)
        self.run_batch(["a", "b"], budget=10)
        self.assertEqual(len(get_jobs(self.db)), 2, "re-fetch after a crash must not duplicate saved jobs")

    def test_remotive_fetches_one_unfiltered_feed_without_lowering_result_count(self):
        from src.connectors.remote_feed import RemotiveConnector
        from datetime import datetime, timezone
        from unittest.mock import MagicMock
        data = {"jobs": [{"title": "Junior Android Developer", "url": f"https://remotive.example/{i}",
                           "publication_date": datetime.now(timezone.utc).date().isoformat()}
                          for i in range(250)]}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(data).encode()
        with patch("urllib.request.urlopen", return_value=response) as fetch:
            jobs = RemotiveConnector().fetch()
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[0].full_url, "https://remotive.com/api/remote-jobs")
        self.assertEqual(len(jobs), 250)

    def test_two_matrix_edits_preserve_rate_limit_cooldown(self):
        self.board.error = "HTTP 429"
        self.run_batch(["a"])
        self.run_batch(["b"])
        result = self.run_batch(["c"])
        self.assertEqual(self.board.calls, ["a"])
        self.assertTrue(result["progress"]["has_more"])
        self.assertFalse(result["progress"]["can_continue"])
        self.clock.value += 6 * 3600 + 1
        self.board.error = ""
        self.run_batch(["c"])
        self.assertEqual(self.board.calls, ["a", "c"])

    def test_budget_stop_exposes_automatic_continuation(self):
        result = self.run_batch(["a", "b", "c", "d"])
        self.assertTrue(result["progress"]["can_continue"])
        result = self.run_batch(["a", "b", "c", "d"])
        self.assertFalse(result["progress"]["can_continue"])

    def test_completed_boards_share_one_checkpoint_without_losing_results(self):
        from concurrent.futures import wait as wait_all
        from src.sync_batches import run_batch, set_sync_checkpoint as real_write, insert_jobs as real_insert
        boards = [Board(self.clock) for _ in range(12)]
        for index, board in enumerate(boards):
            board.platform = f"Board {index}"
        checkpoints = []

        def record(db, checkpoint, status):
            checkpoints.append(json.loads(checkpoint))
            return real_write(db, checkpoint, status)

        with patch("src.sync_batches.wait", side_effect=lambda pending, **kwargs: wait_all(pending)), patch(
            "src.sync_batches.set_sync_checkpoint", side_effect=record
        ), patch("src.sync_batches.insert_jobs", wraps=real_insert) as ingest:
            result = run_batch(Aggregator(self.db, boards), ["android"], budget_seconds=100)
        self.assertEqual(ingest.call_count, 1, "completed boards must share one ingestion batch")
        self.assertEqual(result["progress"]["completed_searches"], 12)
        self.assertEqual(len(result["platforms"]), 12)
        self.assertEqual(len(checkpoints), 3, "initial, completed group, final checkpoints")
        saved = json.loads(get_user_setting(self.db, PROGRESS_KEY))
        self.assertTrue(all(state["cursor"] == 1 for state in saved["boards"].values()))
        self.assertEqual(len(get_jobs(self.db)), 1)

    def test_same_cloud_cycle_does_not_restart_completed_boards_during_other_cooldowns(self):
        from src.sync_batches import run_batch
        aggregator = Aggregator(self.db, [self.board])
        first = run_batch(aggregator, ["a"], budget_seconds=10, cycle_id="run-1")
        self.assertFalse(first["progress"]["has_more"])
        self.clock.value += 6 * 3600 + 1
        run_batch(aggregator, ["a"], budget_seconds=10, cycle_id="run-1")
        self.assertEqual(self.board.calls, ["a"])
        run_batch(aggregator, ["a"], budget_seconds=10, cycle_id="run-2")
        self.assertEqual(self.board.calls, ["a", "a"])
