import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from src.models import MANILA, Job, is_today_or_yesterday, is_within_scrape_window, normalize_date, scrape_request_hours, scrape_window_days
from src.aggregator import Aggregator
from src.connectors.base import BaseConnector
from src.connectors.ph_jobs import JobStreetCatalogConnector
from src.database import init_db, get_jobs, insert_jobs, set_user_setting


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
                self.assertEqual(result["added"], 1)
                self.assertEqual(len(get_jobs(db)), 2)

    def test_dynamic_window_expands_for_missed_days_and_narrows_for_remaining_hours(self):
        class Board(BaseConnector):
            platform = "Dynamic board"
            tier = 1
            def fetch(self, query="", location=""):
                now = datetime.now(MANILA)
                today = now.date()
                return [
                    Job("Software Developer", "Today Co", "Remote", self.platform, 1, "https://example.org/d0", date_posted=str(today)),
                    Job("Software Developer", "Yesterday Co", "Remote", self.platform, 1, "https://example.org/d1", date_posted=str(today - timedelta(days=1))),
                    Job("Software Developer", "Three Days Co", "Remote", self.platform, 1, "https://example.org/d3", date_posted=str(today - timedelta(days=3))),
                    Job("Software Developer", "Old Co", "Remote", self.platform, 1, "https://example.org/d5", date_posted=str(today - timedelta(days=5))),
                ]

        for budget in (None, 5):
            with self.subTest(budget=budget), tempfile.TemporaryDirectory() as temp:
                db = os.path.join(temp, "dynamic_gap_test.db")
                init_db(db)
                three_days_ago = datetime.now(MANILA) - timedelta(days=3, hours=1)
                set_user_setting(db, "last_completed_scrape_at", str(three_days_ago.timestamp()))
                result = Aggregator(db, [Board()]).run_sync(queries=["developer"], budget_seconds=budget)
                self.assertEqual(result["added"], 3)

        now = datetime(2026, 11, 17, 15, 0, tzinfo=MANILA)
        since_3h = now - timedelta(hours=3)
        self.assertEqual(scrape_window_days(now, since=since_3h), 1)
        self.assertEqual(scrape_request_hours(now, since=since_3h), 3)
        self.assertTrue(is_within_scrape_window("2 hours ago", now, since=since_3h))
        self.assertFalse(is_within_scrape_window("4 hours ago", now, since=since_3h))
        self.assertTrue(is_within_scrape_window("2026-11-17", now, since=since_3h))
        self.assertFalse(is_within_scrape_window("2026-11-16", now, since=since_3h))

        since_4d = now - timedelta(days=4, hours=2)
        self.assertEqual(scrape_window_days(now, since=since_4d), 5)
        self.assertEqual(scrape_request_hours(now, since=since_4d), 98)
        self.assertTrue(is_within_scrape_window("2026-11-13", now, since=since_4d))
        self.assertFalse(is_within_scrape_window("2026-11-12", now, since=since_4d))

    def test_jobstreet_resumed_old_window_restarts_with_dynamic_days(self):
        connector = JobStreetCatalogConnector()
        connector.feed_state = {"page": 9, "days": 14, "full": True}
        response = MagicMock(status_code=200, text=json.dumps({"data": [], "totalCount": 0}))
        with patch.object(connector, "get_url", return_value=response) as fetch:
            connector.fetch()
        params = parse_qs(urlparse(fetch.call_args.args[0]).query)
        self.assertEqual(params["daterange"], ["1"])
        self.assertEqual(params["page"], ["1"])

        connector.window_since = (datetime.now(MANILA) - timedelta(days=2)).timestamp()
        with patch.object(connector, "get_url", return_value=response) as fetch:
            connector.fetch()
        params = parse_qs(urlparse(fetch.call_args.args[0]).query)
        self.assertEqual(params["daterange"], ["3"])

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
            adapter = JobSpyAdapter("Indeed", "indeed", 1)
            jobs = adapter.fetch()
            self.assertEqual(scrape.call_args.kwargs["hours_old"], scrape_request_hours())
            self.assertEqual(len(jobs), 1)
            adapter.window_since = (datetime.now(MANILA) - timedelta(days=1, minutes=30)).timestamp()
            jobs_gap = adapter.fetch()
            self.assertEqual(scrape.call_args.kwargs["hours_old"], 25)
            self.assertEqual(len(jobs_gap), 2)
