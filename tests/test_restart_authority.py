import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src import execution_inbox as inbox
from src.aggregator import Aggregator
from src.database import (init_db, set_user_setting, get_user_setting, set_sync_checkpoint,
                          insert_jobs, get_jobs, acquire_sync_lease)
from src.execution_dispatch import start, telemetry
from src.inbox_worker import run_claimed, run_cloud, run_local
from tests.test_inbox_worker import Feed, listing


class RestartAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = str(Path(self.directory.name) / "restart_authority_test.db")
        init_db(self.db)

    def test_restart_replaces_queued_and_running_commands(self):
        for running in (False, True):
            with self.subTest(running=running):
                first = inbox.enqueue(self.db, ["old"], restart=True)
                owner = inbox.claim(self.db, "local", "old-pc") if running else None
                latest = inbox.enqueue(self.db, ["new"], restart=True)
                self.assertNotEqual(first["id"], latest["id"])
                self.assertEqual(latest["queries"], ["new"])
                self.assertEqual(latest["status"], "queued")
                self.assertTrue(latest["restart"])
                if owner:
                    self.assertFalse(inbox.owned(self.db, owner))
                    self.assertFalse(inbox.update_owned(self.db, owner, {"status": "ok"}))
                    self.assertFalse(inbox.cancel(self.db, status="paused", claimed=owner))
                self.assertEqual(inbox.enqueue(self.db)["id"], latest["id"], "ordinary Sync remains idempotent")

    def test_restart_preserves_daily_intent_without_turning_manual_request_automatic(self):
        inbox.enqueue(self.db, automatic=True)
        latest = inbox.enqueue(self.db, restart=True)
        self.assertFalse(latest["automatic"])
        self.assertTrue(latest["daily_requested"])

    def test_old_progress_is_hidden_until_latest_cycle_persists(self):
        old = inbox.enqueue(self.db, ["python"])
        old_owner = inbox.claim(self.db, "local", "old-pc")
        stale = {"cycle_id": old["id"], "progress": {"completed_searches": 1000},
                 "last_result": {"status": "partial", "added": 42, "progress": {"completed_searches": 1000}},
                 "logs": ["old progress"], "telemetry": {"Old source": {"status": "complete"}}}
        set_user_setting(self.db, "sync_status", json.dumps(stale))
        latest = inbox.enqueue(self.db, ["python"], restart=True)
        pending = telemetry(self.db)
        self.assertEqual(pending["execution"]["id"], latest["id"])
        self.assertTrue(pending["awaiting_checkpoint"])
        self.assertIsNone(pending["progress"])
        self.assertEqual(pending["last_result"]["total_fetched"], 0)
        self.assertNotIn("progress", pending["last_result"])
        self.assertEqual(pending["telemetry"], {})
        guard = {**old_owner, "key": inbox.KEY}
        set_sync_checkpoint(self.db, "stale checkpoint", json.dumps(stale), execution_guard=guard)
        self.assertIsNone(get_user_setting(self.db, "sync_batch_progress"))
        self.assertTrue(telemetry(self.db)["awaiting_checkpoint"])
        current = inbox.claim(self.db, "local", "new-pc")
        self.assertTrue(telemetry(self.db)["awaiting_checkpoint"], "claim alone does not make old progress current")
        run_claimed(self.db, current, Aggregator(self.db, [Feed()]))
        active = telemetry(self.db)
        self.assertFalse(active["awaiting_checkpoint"])
        self.assertEqual(active["cycle_id"], latest["id"])
        self.assertNotEqual(active["progress"]["completed_searches"], 1000)

    def test_delayed_local_and_old_cloud_follow_new_command_only(self):
        old = inbox.enqueue(self.db, ["old"])
        latest = inbox.enqueue(self.db, ["new"], restart=True)
        with patch("src.inbox_worker.run_claimed") as execute:
            run_cloud(self.db, old["id"], Aggregator(self.db, []))
            execute.assert_not_called()
            stop = threading.Event()

            def accepted(db, command, aggregator, key):
                self.assertEqual(command["id"], latest["id"])
                self.assertTrue(command["restart"])
                stop.set()

            execute.side_effect = accepted
            run_local(self.db, Aggregator(self.db, []), stop=stop)
            execute.assert_called_once()

    def test_late_fetch_cannot_save_jobs_or_checkpoint_after_restart(self):
        first = inbox.enqueue(self.db, ["developer"])
        owner = inbox.claim(self.db, "local", "old-pc")
        old_guard = {**owner, "key": inbox.KEY}
        latest_ids = []

        class LateFeed(Feed):
            def fetch(inner, **kwargs):
                latest_ids.append(inbox.enqueue(self.db, ["developer"], restart=True)["id"])
                return [listing()]

        run_claimed(self.db, owner, Aggregator(self.db, [LateFeed()]))
        self.assertEqual(get_jobs(self.db), [])
        self.assertEqual(inbox.read(self.db)["id"], latest_ids[0])
        self.assertNotEqual(latest_ids[0], first["id"])
        checkpoint = get_user_setting(self.db, "sync_batch_progress")
        set_sync_checkpoint(self.db, "late", "late", execution_guard=old_guard)
        insert_jobs(self.db, [listing()], execution_guard=old_guard)
        self.assertEqual(get_user_setting(self.db, "sync_batch_progress"), checkpoint)
        self.assertEqual(get_jobs(self.db), [])
        current = inbox.claim(self.db, "local", "latest-pc")
        run_claimed(self.db, current, Aggregator(self.db, [Feed()]))
        self.assertEqual(len(get_jobs(self.db)), 1)
        self.assertEqual(telemetry(self.db)["cycle_id"], latest_ids[0])

    def test_old_dispatch_in_flight_does_not_block_new_restart_supervisor(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS_TOKEN": "test"}), patch("src.execution_dispatch.dispatch") as dispatch:
            first = start(self.db)
            # Simulate the old global dispatch lock and a still-held command-specific lock.
            lease = str(int(time.time()) + 30) + "|old"
            acquire_sync_lease(self.db, lease, int(time.time()), key="execution_dispatch")
            acquire_sync_lease(self.db, lease, int(time.time()), key="execution_dispatch:" + first["execution"]["id"])
            latest = start(self.db, restart=True)
            self.assertNotEqual(first["execution"]["id"], latest["execution"]["id"])
            self.assertEqual(dispatch.call_count, 2)
            self.assertEqual(dispatch.call_args.args[0], latest["execution"]["id"])

    def test_pause_before_worker_ack_does_not_resurrect_old_progress(self):
        set_user_setting(self.db, "sync_status", json.dumps({"cycle_id": "old", "progress": {"completed_searches": 1000}}))
        inbox.enqueue(self.db, restart=True)
        inbox.cancel(self.db, status="paused")
        status = telemetry(self.db)
        self.assertFalse(status["is_syncing"])
        self.assertIsNone(status["progress"])

    def test_newer_scheduled_result_is_not_replaced_by_old_partial_command(self):
        inbox.enqueue(self.db)
        owner = inbox.claim(self.db, "local", "old-pc")
        inbox.update_owned(self.db, owner, {"status": "partial", "added": 477})
        latest = {"cycle_id": "cloud-cron-new", "completed_at": time.time() + 1,
                  "executor": "cloud", "last_result": {"status": "partial", "added": 143}}
        set_user_setting(self.db, "sync_status", json.dumps(latest))
        status = telemetry(self.db)
        self.assertEqual(status["last_result"], latest["last_result"])
        self.assertEqual(status["execution"], {})
        self.assertFalse(status["is_syncing"])


class RestartAuthorityApiTests(unittest.TestCase):
    from tests.test_local_worker import TestLocalWorker as _Fixture
    setUp = _Fixture.setUp
    call = _Fixture.call

    def test_restart_api_supersedes_running_command_and_returns_latest_id(self):
        with patch.dict(os.environ, {"JOB_EXECUTOR": "database", "GITHUB_ACTIONS_TOKEN": "test"}), patch(
                "src.execution_dispatch.dispatch") as dispatch:
            _, first = self.call("/api/sync", "POST", {"keywords": ["old"]}, admin=True)
            old_owner = inbox.claim(self.db, "local", "old-pc")
            code, latest = self.call("/api/sync", "POST", {"action": "restart", "keywords": ["new"]}, admin=True)
            self.assertEqual(code, 200)
            self.assertNotEqual(latest["execution"]["id"], first["execution"]["id"])
            self.assertFalse(inbox.owned(self.db, old_owner))
            _, status = self.call("/api/sync/status", admin=True)
            self.assertEqual(status["execution"]["id"], latest["execution"]["id"])
            self.assertTrue(status["awaiting_checkpoint"])
            self.assertEqual(dispatch.call_count, 2)
