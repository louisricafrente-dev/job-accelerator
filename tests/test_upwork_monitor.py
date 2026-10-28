import asyncio
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from src.database import init_db, set_user_setting
from src.upwork_monitor import claim, poll_cloud, process, start


class UpworkMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "daily_upwork_test.db")
        init_db(self.db)

    def test_only_daily_queue_can_claim_and_only_once(self):
        self.assertFalse(claim(self.db, "local"))
        self.assertFalse(claim(self.db, "cloud"))
        self.assertTrue(claim(self.db, "daily"))
        self.assertFalse(claim(self.db, "daily"))

    def test_pause_blocks_daily_claim(self):
        set_user_setting(self.db, "auto_sync_enabled", "0")
        self.assertFalse(claim(self.db, "daily"))

    def test_slot_reopens_next_manila_day(self):
        self.assertTrue(claim(self.db, "daily"))
        tomorrow = (datetime.now(ZoneInfo("Asia/Manila")) + timedelta(days=1)).replace(hour=0, minute=1)
        with patch("src.upwork_monitor.datetime") as clock, patch("src.upwork_monitor.time.time", return_value=tomorrow.timestamp()):
            clock.now.return_value = tomorrow
            self.assertTrue(claim(self.db, "daily"))
            self.assertFalse(claim(self.db, "daily"))

    def test_old_callbacks_do_not_fetch_or_publish(self):
        def complete(coroutine):
            try:
                coroutine.send(None)
            except StopIteration as result:
                return result.value
            self.fail("Retired monitor unexpectedly waited on network")
        with patch("src.connectors.upwork_flconsole.fetch_jobs") as fetch:
            self.assertEqual(poll_cloud(self.db)["status"], "disabled")
            self.assertEqual(complete(start(self.db))["status"], "disabled")
            complete(process(self.db, {"run_id": "old", "step": 1}))
        fetch.assert_not_called()
