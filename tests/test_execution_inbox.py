import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from src.database import init_db
from src.execution_inbox import enqueue, claim, read, update_owned, cancel


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = str(Path(self.directory.name) / "inbox_test.db")
        init_db(self.db)

    def test_local_ack_then_renew_complete(self):
        command = enqueue(self.db, ["developer"], now=100)
        self.assertEqual(enqueue(self.db, now=101)["id"], command["id"])
        owned = claim(self.db, "local", "pc", now=160)
        self.assertIsNotNone(owned)
        self.assertIsNone(claim(self.db, "cloud", "gh", now=200))
        self.assertTrue(update_owned(self.db, owned, now=200))
        self.assertTrue(update_owned(self.db, owned, {"status": "ok", "added": 2}, now=201))
        self.assertEqual(read(self.db)["status"], "complete")

    def test_offline_fallback_deadline_and_single_winner(self):
        enqueue(self.db, now=100)
        self.assertIsNone(claim(self.db, "cloud", "gh", now=189))
        self.assertIsNone(claim(self.db, "local", "pc", now=190))
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda n: claim(self.db, "cloud", str(n), now=190), range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_expired_owner_cannot_complete_after_takeover(self):
        enqueue(self.db, now=100)
        stale = claim(self.db, "local", "pc", now=110)
        current = claim(self.db, "cloud", "gh", now=291)
        self.assertIsNotNone(current)
        self.assertFalse(update_owned(self.db, stale, {"status": "ok"}, now=292))
        self.assertTrue(update_owned(self.db, current, {"status": "error"}, now=292))
        self.assertEqual(read(self.db)["status"], "error")

    def test_cancel_fences_late_completion_and_namespace_isolation(self):
        enqueue(self.db, key="integration:unique", now=100)
        self.assertEqual(read(self.db), {})
        owned = claim(self.db, "local", "pc", key="integration:unique", now=101)
        self.assertTrue(cancel(self.db, key="integration:unique"))
        self.assertFalse(update_owned(self.db, owned, {"status": "ok"}, key="integration:unique", now=102))
