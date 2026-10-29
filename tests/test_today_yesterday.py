import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from src.models import MANILA, Job, is_today_or_yesterday, normalize_date
from src.aggregator import Aggregator
from src.connectors.base import BaseConnector
from src.connectors.ph_jobs import JobStreetCatalogConnector
from src.database import init_db, get_jobs, insert_jobs


class TestTodayYesterday(unittest.TestCase):
    def test_calendar_boundaries_and_unknown_dates(self):
        for instant in (datetime(2026, 10, 29, 0, 1, tzinfo=MANILA),
                        datetime(2026, 10, 29, 23, 59, tzinfo=MANILA)):
            for raw in ("2026-10-29", "2026-10-28", "today", "yesterday"):
                self.assertTrue(is_today_or_yesterday(raw, instant), raw)
            for raw in ("2026-10-27", "2026-10-30", "2 days ago", "15 days ago", "", None, "garbage", "recently"):
                self.assertFalse(is_today_or_yesterday(raw, instant), raw)

    def test_utc_and_relative_dates_use_manila_midnight(self):
        instant = datetime(2026, 10, 28, 16, 30, tzinfo=timezone.utc)
        self.assertTrue(is_today_or_yesterday("2026-10-27T16:00:00Z", instant))
        self.assertFalse(is_today_or_yesterday("2026-10-27T15:59:59Z", instant))
        self.assertTrue(is_today_or_yesterday("24 hours ago", instant))
        self.assertFalse(is_today_or_yesterday("25 hours ago", instant))
        self.assertEqual(normalize_date("2026-10-28T16:30:00Z"), "2026-10-29")
        self.assertEqual(normalize_date(1793205000), datetime.fromtimestamp(1793205000, MANILA).date().isoformat())

    def test_both_sync_paths_reject_old_unknown_future_and_keep_history(self):
        class Board(BaseConnector):
            platform = "Date policy board"
            tier = 1
            def fetch(self, query="", location=""):
                today = datetime.now(MANILA).date()
                return [Job("Software Developer", "Company " + str(i), "Remote", self.platform, 1,
                            "https://example.org/job/" + str(i), date_posted=raw)
                        for i, raw in enumerate((str(today), str(today-timedelta(days=1)),
                                                str(today-timedelta(days=2)), str(today+timedelta(days=1)), ""))]
        for budget in (None, 5):
            with self.subTest(budget=budget), tempfile.TemporaryDirectory() as temp:
                db = os.path.join(temp, "date_test.db")
                init_db(db)
                insert_jobs(db, [Job("Software Developer", "Historical", "Remote", "Old", 1,
                                    "https://example.org/history", date_posted="2026-01-01")])
                result = Aggregator(db, [Board()]).run_sync(queries=["developer"], budget_seconds=budget)
                self.assertEqual(result["added"], 2)
                self.assertEqual(len(get_jobs(db)), 3)

    def test_jobstreet_resumed_old_window_restarts_with_two_days(self):
        connector = JobStreetCatalogConnector()
        connector.feed_state = {"page": 9, "days": 14, "full": True}
        response = MagicMock(status_code=200, text=json.dumps({"data": [], "totalCount": 0}))
        with patch.object(connector, "get_url", return_value=response) as fetch:
            connector.fetch()
        params = parse_qs(urlparse(fetch.call_args.args[0]).query)
        self.assertEqual(params["daterange"], ["2"])
        self.assertEqual(params["page"], ["1"])

    def test_jobspy_request_is_bounded_but_calendar_filter_is_stricter(self):
        import pandas as pd
        from types import SimpleNamespace
        from src.connectors.jobspy_adapter import JobSpyAdapter
        today = datetime.now(MANILA).date()
        records = [{"title": "Software Developer", "company": "Example", "location": "Philippines",
                    "job_url": "https://example.org/" + str(i), "date_posted": str(today-timedelta(days=i)),
                    "description": "Build software"} for i in range(3)]
        scrape = MagicMock(return_value=pd.DataFrame(records))
        with patch.dict("sys.modules", {"jobspy": SimpleNamespace(scrape_jobs=scrape)}):
            jobs = JobSpyAdapter("Indeed", "indeed", 1).fetch()
        self.assertEqual(scrape.call_args.kwargs["hours_old"], 48)
        self.assertEqual(len(jobs), 2)
