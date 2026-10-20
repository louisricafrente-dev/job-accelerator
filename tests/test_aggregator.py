import unittest
import tempfile
import os
from unittest.mock import MagicMock, patch
from src.database import init_db, get_jobs
from src.models import Job
from src.aggregator import Aggregator

class TestAggregator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "agg_test.db")
        init_db(self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_run_orchestrator(self):
        mock_connector = MagicMock()
        mock_connector.platform = "MockBoard"
        mock_connector.tier = 1
        mock_connector.fetch.return_value = [
            Job(
                title="Junior Web Dev",
                company="Mock Inc",
                location="Remote",
                platform="MockBoard",
                tier=1,
                job_url="https://mockboard.com/jobs/1",
                experience_level="Junior / Entry",
                date_posted="today"
            )
        ]
        aggregator = Aggregator(self.db_path, connectors=[mock_connector])
        stats = aggregator.run_sync(queries=["software engineer"])
        self.assertEqual(stats["added"], 1)
        self.assertEqual(len(get_jobs(self.db_path)), 1)
        self.assertEqual(stats["platforms"]["MockBoard"], 1)

    def test_14_day_and_matrix_filtering(self):
        mock_connector = MagicMock()
        mock_connector.platform = "MockBoard"
        mock_connector.tier = 1
        mock_connector.fetch.return_value = [
            # 1. Matching role, within 14 days -> should be ACCEPTED
            Job(title="React Developer", company="Fresh Co", location="Remote", platform="MockBoard", tier=1, job_url="https://m1", date_posted="today"),
            # 2. Senior role -> should be REJECTED (Senior / Lead)
            Job(title="Senior Architect", company="Lead Corp", location="Remote", platform="MockBoard", tier=1, job_url="https://m2", date_posted="today"),
            # 3. Stale date (20 days ago) -> should be REJECTED (>14 days)
            Job(title="Frontend Engineer", company="Old Co", location="Remote", platform="MockBoard", tier=1, job_url="https://m3", date_posted="2026-09-01"),
            # 4. Non-tech role -> should be REJECTED (Non-tech)
            Job(title="Chief Accountant", company="Tax Corp", location="Remote", platform="MockBoard", tier=1, job_url="https://m4", date_posted="today"),
            # 5. Non-entry VA -> should be REJECTED
            Job(title="Executive Assistant (5 years exp)", company="VA Corp", location="Remote", platform="MockBoard", tier=1, job_url="https://m5", date_posted="today"),
            # 6. Entry VA with training -> should be ACCEPTED
            Job(title="Virtual Assistant (Paid Training)", company="Train Corp", location="Remote", platform="MockBoard", tier=1, job_url="https://m6", date_posted="yesterday"),
        ]
        aggregator = Aggregator(self.db_path, connectors=[mock_connector])
        stats = aggregator.run_sync(queries=["software engineer"])
        self.assertEqual(stats["added"], 2)
        jobs = get_jobs(self.db_path, include_va=True)
        self.assertEqual(len(jobs), 2)
        titles = {j["title"] for j in jobs}
        self.assertEqual(titles, {"React Developer", "Virtual Assistant (Paid Training)"})

    def test_sync_lock_prevents_spam(self):
        mock_connector = MagicMock()
        mock_connector.platform = "SlowBoard"
        mock_connector.tier = 1
        mock_connector.fetch.return_value = []

        aggregator = Aggregator(self.db_path, connectors=[mock_connector])
        # Simulate an ongoing sync holding the lock
        aggregator._sync_lock.acquire()
        aggregator.is_syncing = True

        # Second sync attempt should immediately return already_syncing without throwing
        result = aggregator.run_sync()
        self.assertEqual(result["status"], "already_syncing")
        self.assertTrue(result["is_syncing"])
        self.assertEqual(result["added"], 0)

        # Release simulated lock
        aggregator.is_syncing = False
        aggregator._sync_lock.release()

    def test_connector_caching_avoids_repeated_network_calls(self):
        mock_connector = MagicMock()
        mock_connector.platform = "CachedBoard"
        mock_connector.tier = 1
        mock_connector.fetch.return_value = [
            Job(title="Dev 1", company="Corp", location="Remote", platform="CachedBoard", tier=1, job_url="https://c1")
        ]

        aggregator = Aggregator(self.db_path, connectors=[mock_connector])
        stats1 = aggregator.run_sync()
        self.assertEqual(mock_connector.fetch.call_count, 1)

        # Second run within 5 minutes should use cache and NOT call fetch again
        stats2 = aggregator.run_sync()
        self.assertEqual(mock_connector.fetch.call_count, 1)
        self.assertEqual(stats2["status"], "ok")

    def test_background_sync_launch(self):
        import time
        mock_connector = MagicMock()
        mock_connector.platform = "BgBoard"
        mock_connector.tier = 1
        mock_connector.fetch.return_value = []

        aggregator = Aggregator(self.db_path, connectors=[mock_connector])
        import threading
        real_thread = threading.Thread
        workers = []
        def capture_worker(*args, **kwargs):
            worker = real_thread(*args, **kwargs)
            workers.append(worker)
            return worker
        with patch("src.aggregator.threading.Thread", side_effect=capture_worker):
            started = aggregator.start_background_sync()
        self.assertTrue(started)
        self.assertEqual(len(workers), 1)
        workers[0].join(timeout=5)
        self.assertFalse(workers[0].is_alive(), "Background sync did not finish")
        self.assertFalse(aggregator.is_syncing)

if __name__ == "__main__":
    unittest.main()

