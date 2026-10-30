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
            result = Aggregator(self.db, [self.board]).run_sync(queries=keywords, budget_seconds=3)
            if not result["progress"]["has_more"]:
                break
        self.assertEqual(self.board.calls, keywords)
        self.assertEqual(len(get_jobs(self.db, limit=500)), 295)
        self.assertEqual(result["progress"]["completed_searches"], 295)
        self.run_batch(keywords)
        self.assertEqual(len(self.board.calls), 295, "finished board must respect refresh cooldown")

    def test_saved_large_matrix_edit_includes_appended_keywords(self):
        keywords = [f"keyword-{i}" for i in range(25)]
        set_user_setting(self.db, "target_stack", ",".join(keywords))
        Aggregator(self.db, [self.board]).run_sync(budget_seconds=100)
        self.assertEqual(self.board.calls, keywords)
        keywords += ["Rust / WebAssembly", "Elixir developer", "QA Automation", "IT Support"]
        set_user_setting(self.db, "target_stack", ",".join(keywords))
        self.board.calls.clear()
        result = Aggregator(self.db, [self.board]).run_sync(budget_seconds=100)
        self.assertEqual(self.board.calls, keywords[-4:])
        self.assertEqual(result["progress"]["keywords"], len(keywords))
        self.assertEqual(result["progress"]["completed_searches"], len(keywords))
        self.assertFalse(result["progress"]["has_more"])

    def test_matrix_reorder_and_new_cycle_reuse_only_successful_queries(self):
        from src.sync_batches import run_batch
        run_batch(Aggregator(self.db, [self.board]), ["a", "b", "c"], budget_seconds=3, workers=1, cycle_id="first")
        self.assertEqual(self.board.calls, ["a", "b"])
        result = run_batch(Aggregator(self.db, [self.board]), ["new", "c", "b", "a"], budget_seconds=100, workers=1, cycle_id="edited")
        self.assertEqual(self.board.calls, ["a", "b", "new", "c"])
        self.assertEqual(result["progress"]["completed_searches"], 4)
        self.assertNotIn("completed_queries", result["progress"]["boards"][self.board.platform])

    def test_matrix_cache_expires_and_connector_revision_invalidates_it(self):
        from src.sync_batches import run_batch
        run_batch(Aggregator(self.db, [self.board]), ["a", "b"], budget_seconds=100, workers=1, cycle_id="first")
        self.clock.value += 6 * 3600 + 1
        run_batch(Aggregator(self.db, [self.board]), ["a", "b", "c"], budget_seconds=100, workers=1, cycle_id="expired")
        self.assertEqual(self.board.calls, ["a", "b", "a", "b", "c"])
        self.board.revision = 2
        run_batch(Aggregator(self.db, [self.board]), ["a", "b", "c"], budget_seconds=100, workers=1, cycle_id="revised")
        self.assertEqual(self.board.calls[-3:], ["a", "b", "c"])
        self.assertEqual(len(self.board.calls), 8)

    def test_failed_query_is_not_cached_when_matrix_changes(self):
        self.run_batch(["a", "b", "c"])
        self.board.error = "temporary outage"
        self.run_batch(["a", "b", "c"])
        self.board.error = ""
        self.clock.value += 15 * 60 + 1
        result = self.run_batch(["c", "a", "b", "new"], budget=100)
        self.assertEqual(self.board.calls, ["a", "b", "c", "c", "new"])
        self.assertEqual(result["progress"]["completed_searches"], 4)

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

    def test_cooldown_does_not_advance_last_success_and_survives_restart(self):
        self.run_batch(["a", "b", "c", "d"])
        last_success = json.loads(get_user_setting(self.db, "sync_status"))["last_sync_time"]
        self.board.error = "HTTP 404"
        self.clock.value += 10
        failed = self.run_batch(["a", "b", "c", "d"])
        calls = list(self.board.calls)
        retry_at = failed["progress"]["boards"][self.board.platform]["blocked_until"]
        self.assertGreaterEqual(retry_at - self.clock.time(), 6 * 3600 - 1)
        self.clock.value += 60
        waiting = self.run_batch(["a", "b", "c", "d"])
        self.assertEqual(self.board.calls, calls)
        self.assertEqual(json.loads(get_user_setting(self.db, "sync_status"))["last_sync_time"], last_success)
        self.assertEqual(waiting["telemetry"][self.board.platform]["error"], "HTTP 404")
        self.clock.value = retry_at - 2000000000 + 1
        self.board.error = ""
        recovered = self.run_batch(["a", "b", "c", "d"], budget=20)
        self.assertFalse(recovered["progress"]["has_more"])
        self.assertEqual(self.board.calls, ["a", "b", "c", "d", "c"])

    def test_completed_board_is_reported_complete_after_restart(self):
        self.run_batch(["a"])
        result = self.run_batch(["a"])
        self.assertEqual(result["telemetry"][self.board.platform]["status"], "complete")

    def test_fresh_cycle_reuses_recent_queries_while_respecting_blocked_source(self):
        from src.sync_batches import run_batch
        blocked = Board(self.clock)
        blocked.platform = "Blocked"
        blocked.error = "HTTP 403"
        first = run_batch(Aggregator(self.db, [self.board, blocked]), ["a", "b"], budget_seconds=30, workers=1, cycle_id="first")
        self.assertFalse(first["progress"]["has_more"])
        self.assertTrue(first["progress"]["unfinished"])
        self.assertEqual(first["progress"]["deferred_boards"][0]["platform"], "Blocked")
        second = run_batch(Aggregator(self.db, [self.board, blocked]), ["a", "b"], budget_seconds=30, workers=1, cycle_id="second")
        self.assertEqual(self.board.calls, ["a", "b"])
        self.assertEqual(blocked.calls, ["a"])
        self.assertFalse(second["progress"]["has_more"])

    def test_resume_retries_recovered_source_without_restarting_completed_source(self):
        from src.sync_batches import run_batch
        blocked = Board(self.clock)
        blocked.platform = "Blocked"
        blocked.error = "HTTP 403"
        run_batch(Aggregator(self.db, [self.board, blocked]), ["a"], budget_seconds=30, workers=1, cycle_id="same")
        self.clock.value += 21601
        blocked.error = ""
        result = run_batch(Aggregator(self.db, [self.board, blocked]), ["a"], budget_seconds=30, workers=1, cycle_id="same", resume=True)
        self.assertEqual(self.board.calls, ["a"])
        self.assertEqual(blocked.calls, ["a", "a"])
        self.assertFalse(result["progress"]["unfinished"])

    def test_endpoint_revision_clears_stale_404_but_not_an_access_block(self):
        from src.sync_batches import run_batch
        self.board.error = "HTTP 404"
        run_batch(Aggregator(self.db, [self.board]), ["a"], cycle_id="old", workers=1)
        self.board.revision = 2
        self.board.error = ""
        result = run_batch(Aggregator(self.db, [self.board]), ["a"], cycle_id="new", workers=1)
        self.assertFalse(result["progress"]["unfinished"])
        self.clock.value += 6 * 3600 + 1
        self.board.error = "HTTP 403"
        run_batch(Aggregator(self.db, [self.board]), ["a"], cycle_id="blocked", workers=1)
        self.board.revision = 3
        calls = len(self.board.calls)
        run_batch(Aggregator(self.db, [self.board]), ["a"], cycle_id="still-blocked", workers=1)
        self.assertEqual(len(self.board.calls), calls)

    def test_feed_to_query_revision_restarts_at_first_keyword(self):
        from src.sync_batches import run_batch
        self.board.is_feed = True
        run_batch(Aggregator(self.db, [self.board]), ["qa", "support"], cycle_id="same", workers=1)
        self.board.calls.clear()
        self.board.is_feed = False
        self.board.revision = 2
        run_batch(Aggregator(self.db, [self.board]), ["qa", "support"], cycle_id="same", workers=1)
        self.assertEqual(self.board.calls, ["qa", "support"])

    def test_legacy_poll_timestamp_is_not_a_successful_fetch(self):
        set_user_setting(self.db, "sync_status", json.dumps({"last_sync_time": self.clock.time()}))
        self.run_batch(["a"], budget=0)
        self.assertEqual(json.loads(get_user_setting(self.db, "sync_status"))["last_sync_time"], 0)

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

    def test_remotive_fetches_one_bounded_recent_feed(self):
        from src.connectors.remote_feed import RemotiveConnector
        from datetime import datetime, timezone
        from unittest.mock import MagicMock
        data = {"jobs": [{"title": "Junior Android Developer", "url": f"https://remotive.example/{i}",
                           "publication_date": datetime.now(timezone.utc).date().isoformat()}
                          for i in range(100)]}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(data).encode()
        with patch("urllib.request.urlopen", return_value=response) as fetch:
            jobs = RemotiveConnector().fetch()
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[0].full_url, "https://remotive.com/api/remote-jobs?limit=200")
        self.assertEqual(len(jobs), 100)

    def test_two_matrix_edits_preserve_rate_limit_cooldown(self):
        self.board.error = "HTTP 429"
        self.run_batch(["a"])
        self.run_batch(["b"])
        result = self.run_batch(["c"])
        self.assertEqual(self.board.calls, ["a"])
        self.assertFalse(result["progress"]["has_more"])
        self.assertTrue(result["progress"]["unfinished"])
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
