import unittest
import tempfile
import os
from unittest.mock import MagicMock
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
                experience_level="Junior / Entry"
            )
        ]
        aggregator = Aggregator(self.db_path, connectors=[mock_connector])
        stats = aggregator.run_sync(queries=["software engineer"])
        self.assertEqual(stats["added"], 1)
        self.assertEqual(len(get_jobs(self.db_path)), 1)
        self.assertEqual(stats["platforms"]["MockBoard"], 1)

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
        started = aggregator.start_background_sync()
        self.assertTrue(started)
        # Give thread a brief moment to finish
        time.sleep(0.15)
        self.assertFalse(aggregator.is_syncing)

if __name__ == "__main__":
    unittest.main()

