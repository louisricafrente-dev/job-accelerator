import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.aggregator import Aggregator
from src.connectors.base import BaseConnector
from src.connectors.remote_feed import RemoteOKConnector, ArcConnector, UpworkConnector
from src.database import get_jobs, init_db
from src.models import Job, MANILA, is_within_15_days, normalize_date


class TestSyncErrors(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = os.path.join(self.temp.name, "sync_errors_test.db")
        init_db(self.db)

    def test_query_exception_is_not_success(self):
        class BrokenQuery(BaseConnector):
            platform = "Broken query"

            def fetch(self, query="", location=""):
                raise RuntimeError("upstream unavailable")

        result = Aggregator(self.db, [BrokenQuery()]).run_sync(["virtual assistant"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["telemetry"]["Broken query"]["status"], "error")

    def test_reported_failure_survives_later_success_and_keeps_jobs(self):
        class MixedQuery(BaseConnector):
            platform = "Mixed query"

            def fetch(self, query="", location=""):
                if query == "react developer":
                    self.last_error = "rate limited"
                    return []
                self.last_error = ""
                return [Job("Junior Android Developer", "Example", "Remote", self.platform,
                            1, "https://example.com/job", date_posted="today")]

        result = Aggregator(self.db, [MixedQuery()]).run_sync(["react developer", "virtual assistant"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["added"], 1)
        self.assertEqual(len(get_jobs(self.db)), 1)

    def test_failed_feed_is_retried_and_can_recover(self):
        connector = RemoteOKConnector()
        aggregator = Aggregator(self.db, [connector])
        with patch("urllib.request.urlopen", side_effect=RuntimeError("mock outage")) as fetch:
            for _ in range(2):
                result = aggregator.run_sync()
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["telemetry"][connector.platform]["status"], "error")
            self.assertEqual(fetch.call_count, 2)
        with patch("urllib.request.urlopen") as fetch:
            fetch.return_value.__enter__.return_value.read.return_value = b"[]"
            self.assertEqual(aggregator.run_sync()["status"], "partial")
            self.assertEqual(aggregator.run_sync()["status"], "partial")
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(connector.last_error, "")

    def test_thrown_feed_error_is_not_cached(self):
        class BrokenFeed(BaseConnector):
            platform = "Broken feed"
            is_feed = True

            def fetch(self, query="", location=""):
                raise RuntimeError("feed outage")

        aggregator = Aggregator(self.db, [BrokenFeed()])
        for _ in range(2):
            self.assertEqual(aggregator.run_sync()["status"], "partial")
        self.assertFalse(aggregator._cache)

    def test_http_failures_are_reported_by_scrapers(self):
        from src.connectors.ph_jobs import JobStreetConnector
        for connector in (ArcConnector(), UpworkConnector(), JobStreetConnector()):
            with self.subTest(platform=connector.platform), patch.dict(os.environ, {"UPWORK_FEED_URL": "https://example.com/authorized-feed", "FLCONSOLE_MCP_TOKEN": ""}), patch("curl_cffi.requests.Session.get") as fetch:
                fetch.return_value.raise_for_status.side_effect = RuntimeError("HTTP 429")
                self.assertEqual(connector.fetch(), [])
                self.assertEqual(connector.last_error, "HTTP 429")

    def test_bossjob_outage_never_imports_other_sites_as_bossjob(self):
        from src.connectors.ph_jobs import BossjobConnector
        connector = BossjobConnector()
        with patch("urllib.request.urlopen", side_effect=RuntimeError("HTTP 404")) as fetch:
            self.assertEqual(connector.fetch(), [])
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(connector.last_error, "HTTP 404")

    def test_jobspy_reported_errors_are_not_empty_success(self):
        from src.connectors.jobspy_adapter import JobSpyAdapter
        from types import SimpleNamespace
        import pandas as pd
        frame = pd.DataFrame()
        frame.attrs["errors"] = {"indeed": "HTTP 429"}
        with patch.dict("sys.modules", {"jobspy": SimpleNamespace(scrape_jobs=lambda **kwargs: frame)}):
            connector = JobSpyAdapter("Indeed", "indeed", 1)
            self.assertEqual(connector.fetch(), [])
            self.assertIn("429", connector.last_error)


class TestRelativeTimes(unittest.TestCase):
    reference = datetime(2026, 10, 20, 0, 30, tzinfo=MANILA)

    def test_hours_and_minutes_cross_dates(self):
        cases = {
            "48 hours ago": "2026-10-18",
            "posted 2 hrs ago": "2026-10-19",
            "1h ago": "2026-10-19",
            "90 minutes ago": "2026-10-19",
            "45 mins ago": "2026-10-19",
            "0 hours ago": "2026-10-20",
            "400 hours ago": "2026-10-03",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_date(raw, ref_date=self.reference), expected)

    def test_stale_hour_and_minute_ages_are_rejected(self):
        for raw in ("400 hours ago", "24000 minutes ago"):
            with self.subTest(raw=raw):
                self.assertFalse(is_within_15_days(raw, ref_date=self.reference))
        self.assertTrue(is_within_15_days("360 hours ago", ref_date=self.reference))

    def test_today_aliases_do_not_match_arbitrary_text(self):
        for raw in ("today", "just posted"):
            self.assertEqual(normalize_date(raw, ref_date=self.reference), "2026-10-20")
        for raw in ("renewed 20 days ago", "new 20 days ago"):
            self.assertEqual(normalize_date(raw, ref_date=self.reference), "2026-09-30")
        for raw in ("hourly", "minutes", "999999999999999999999 hours ago"):
            self.assertEqual(normalize_date(raw, ref_date=self.reference), "")


if __name__ == "__main__":
    unittest.main()


class TestScrapingRelevance(unittest.TestCase):
    def test_volume_unit_is_not_machine_learning(self):
        from src.classifier import is_relevant_opportunity
        self.assertFalse(is_relevant_opportunity("Perfume Box Design", "Outer-box concept for a 50 ml-100 ml perfume"))
        self.assertTrue(is_relevant_opportunity("Junior ML Engineer", "Build machine learning models"))

    def test_physical_engineering_needs_an_explicit_software_role(self):
        from src.classifier import is_relevant_opportunity
        self.assertFalse(is_relevant_opportunity("Civil Engineer"))
        self.assertFalse(is_relevant_opportunity("Mechanical Engineer", "Use cloud software"))
        self.assertTrue(is_relevant_opportunity("Software Developer - Civil Engineering Tools"))
