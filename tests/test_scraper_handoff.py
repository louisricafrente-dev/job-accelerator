import hashlib
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src import execution_inbox as inbox
from src.aggregator import Aggregator
from src.connectors.base import BaseConnector, NEW_PLATFORMS_7DAY_CUTOFF, default_new_platform_window
from src.connectors.ph_jobs import FounditPHConnector
from src.database import get_jobs, get_user_setting, init_db, set_user_setting
from src.execution_dispatch import telemetry
from src.inbox_worker import run_claimed
from src.models import Job, MANILA


class ScraperHandoffTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = str(Path(self.directory.name) / "scraper_handoff_test.db")
        init_db(self.db)

    def test_new_platform_dates_survive_both_ingestion_paths_and_revert(self):
        today = datetime.now(MANILA).date()
        dates = [str(today - timedelta(days=n)) for n in (0, 1, 3, 6, -1, 7)] + ["", "recently"]
        for budget in (None, 3):
            for days in (7, 2):
                with self.subTest(budget=budget, days=days), tempfile.TemporaryDirectory() as directory:
                    db = str(Path(directory) / "window_test.db")
                    init_db(db)
                    board = FounditPHConnector()
                    # Exercise both the legacy and budgeted orchestration paths without HTTP.
                    board.checkpointed_query = False
                    jobs = [Job("Software Developer", "Example " + str(i), "Remote", board.platform, 1,
                                "https://example.org/job/" + str(i), date_posted=date)
                            for i, date in enumerate(dates)]
                    with patch("src.connectors.base.default_new_platform_window", return_value=days), patch.object(
                            board, "fetch", return_value=jobs):
                        self.assertEqual(board.window_days, days)
                        result = Aggregator(db, [board]).run_sync(queries=["developer"], budget_seconds=budget)
                    expected = dates[:4] if days == 7 else dates[:2]
                    self.assertEqual(result["added"], len(expected))
                    self.assertCountEqual([job["date_posted"] for job in get_jobs(db)], expected)

    def test_standard_source_still_rejects_three_day_old_job(self):
        class Board(BaseConnector):
            platform = "Standard source"
            is_feed = True

            def fetch(self, **kwargs):
                return [Job("Software Developer", "Example", "Remote", self.platform, 1,
                            "https://example.org/old", date_posted=str(datetime.now(MANILA).date() - timedelta(days=3)))]

        result = Aggregator(self.db, [Board()]).run_sync(queries=["developer"], budget_seconds=3)
        self.assertEqual(result["added"], 0)

    def test_new_platform_window_cutoff_is_inclusive(self):
        with patch("src.connectors.base.time.time", return_value=NEW_PLATFORMS_7DAY_CUTOFF):
            self.assertEqual(default_new_platform_window(), 7)
        with patch("src.connectors.base.time.time", return_value=NEW_PLATFORMS_7DAY_CUTOFF + 1):
            self.assertEqual(default_new_platform_window(), 2)

    def test_cloud_takeover_keeps_checkpoint_even_before_restart_consumption_is_saved(self):
        calls = []

        class Board(BaseConnector):
            platform = "Resume source"

            def fetch(self, query="", **kwargs):
                calls.append(query)
                return []

        queries = ["python", "kotlin"]
        command = inbox.enqueue(self.db, queries, restart=True)
        local = inbox.claim(self.db, "local", "pc")
        # Simulate a crash after checkpoint persistence, before the worker's totals update.
        checkpoint = {"cycle_id": command["id"],
                      "signature": hashlib.sha256(json.dumps(queries).encode()).hexdigest(),
                      "boards": {"Resume source": {"cursor": 1, "retry": [], "next_at": 0}}}
        set_user_setting(self.db, "sync_batch_progress", json.dumps(checkpoint))
        cloud = inbox.claim(self.db, "cloud", "github", now=local["lease_until"] + 1)
        self.assertTrue(cloud["restart"])
        result = run_claimed(self.db, cloud, Aggregator(self.db, [Board()]))
        self.assertEqual(calls, ["kotlin"])
        saved = inbox.read(self.db)
        self.assertEqual(saved["status"], "complete")
        self.assertFalse(saved["restart"])
        self.assertEqual(result["status"], "ok")

    def test_new_restart_command_still_resets_old_checkpoint(self):
        calls = []

        class Board(BaseConnector):
            platform = "Restart source"

            def fetch(self, query="", **kwargs):
                calls.append(query)
                return []

        queries = ["python", "kotlin"]
        checkpoint = {"cycle_id": "previous-command",
                      "signature": hashlib.sha256(json.dumps(queries).encode()).hexdigest(),
                      "boards": {"Restart source": {"cursor": 2, "retry": [], "next_at": time.time() + 3600}}}
        set_user_setting(self.db, "sync_batch_progress", json.dumps(checkpoint))
        inbox.enqueue(self.db, queries, restart=True)
        command = inbox.claim(self.db, "local", "pc")
        with patch("src.sync_batches.QUERY_DELAY_SECONDS", 0):
            run_claimed(self.db, command, Aggregator(self.db, [Board()]))
        self.assertEqual(calls, queries)
        self.assertFalse(inbox.read(self.db)["restart"])

    def test_status_origin_is_independent_of_local_liveness(self):
        for executor in ("local", "cloud", None):
            for status in ("running", "partial", "complete", "error"):
                with self.subTest(executor=executor, status=status):
                    command = {"id": "status-test", "executor": executor, "status": status,
                               "lease_until": time.time() + 180, "expires_at": time.time() + 7200}
                    set_user_setting(self.db, inbox.KEY, json.dumps(command))
                    result = telemetry(self.db)
                    self.assertEqual(result["local_request"]["status"], status if executor == "local" else "")
                    self.assertEqual(result["cloud_run"]["status"], status if executor == "cloud" else "")
                    self.assertEqual(result["local_worker"]["online"], executor == "local" and status == "running")

