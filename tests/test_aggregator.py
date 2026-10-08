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

if __name__ == "__main__":
    unittest.main()
