import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from src.models import MANILA, scrape_date_window, scrape_request_hours
from src.connectors.ph_jobs import KalibrrConnector, JobStreetCatalogConnector, BossjobConnector
from src.connectors.remote_feed import FreelancerConnector, RemotiveConnector, HimalayasConnector
from src.connectors.jobspy_adapter import JobSpyAdapter


class TestRawDateRequests(unittest.TestCase):
    def test_request_window_tracks_manila_midnight_and_rounds_hours_up(self):
        for hour, minute, expected in [(0, 0, 24), (0, 1, 25), (12, 0, 36), (23, 59, 48)]:
            now = datetime(2026, 10, 30, hour, minute, tzinfo=MANILA)
            start, end = scrape_date_window(now.astimezone(timezone.utc))
            self.assertEqual(start, datetime(2026, 10, 29, tzinfo=MANILA))
            self.assertEqual(end, datetime(2026, 10, 31, tzinfo=MANILA))
            self.assertEqual(scrape_request_hours(now), expected)

    @staticmethod
    def kalibrr_item(i, date):
        return {"id": str(i), "name": "Software Developer", "activation_date": date,
                "company_info": {"code": "example", "name": "Example"},
                "google_location": {"address_components": {"country": "Philippines"}}}

    def test_kalibrr_stops_old_catalogue_with_no_second_page(self):
        c = KalibrrConnector()
        start, _ = scrape_date_window()
        rows = [self.kalibrr_item(i, (start-timedelta(days=1)).isoformat()) for i in range(c.PAGE_SIZE)]
        response = io.BytesIO(json.dumps({"jobs": rows, "count": 10000}).encode())
        with patch.object(c, "open_url", return_value=response) as fetch:
            jobs = c.fetch()
        params = parse_qs(urlsplit(fetch.call_args.args[0].full_url).query)
        self.assertEqual(params["sort_field"], ["activation_date"])
        self.assertEqual(params["sort_direction"], ["desc"])
        self.assertEqual(params["limit"], ["50"])
        self.assertEqual(jobs, [])
        self.assertFalse(c.has_more)
        self.assertEqual(c.next_feed_state["offset"], 0)

    def test_kalibrr_mixed_page_keeps_fresh_jobs_and_continues(self):
        c = KalibrrConnector()
        start, _ = scrape_date_window()
        rows = [self.kalibrr_item(i, start.isoformat() if i == 0 else (start-timedelta(days=1)).isoformat())
                for i in range(c.PAGE_SIZE)]
        with patch.object(c, "open_url", return_value=io.BytesIO(json.dumps({"jobs": rows, "count": 10000}).encode())):
            jobs = c.fetch()
        self.assertEqual(len(jobs), 1)
        self.assertTrue(c.has_more)
        self.assertEqual(c.next_feed_state["offset"], 50)

    def test_kalibrr_uses_manila_date_before_stopping(self):
        c = KalibrrConnector()
        start, _ = scrape_date_window()
        # Yesterday midnight in Manila is still the preceding UTC calendar date.
        raw = start.astimezone(timezone.utc).isoformat()
        rows = [self.kalibrr_item(1, raw)]
        with patch.object(c, "open_url", return_value=io.BytesIO(json.dumps({"jobs": rows, "count": 1}).encode())):
            self.assertEqual(len(c.fetch()), 1)

    def test_kalibrr_discards_old_checkpoint_and_preserves_same_window(self):
        c = KalibrrConnector()
        start, _ = scrape_date_window()
        for marker, offset in [("2020-01-01", 0), (start.date().isoformat(), 150)]:
            c.feed_state = {"window_start": marker, "offset": 150}
            with patch.object(c, "open_url", return_value=io.BytesIO(b'{"jobs": [], "count": 0}')) as fetch:
                c.fetch()
            params = parse_qs(urlsplit(fetch.call_args.args[0].full_url).query)
            self.assertEqual(params["offset"], [str(offset)])

    def test_jobstreet_rollover_restarts_at_first_recent_page(self):
        c = JobStreetCatalogConnector()
        c.feed_state = {"days": 2, "window_start": "2020-01-01", "page": 15}
        with patch.object(c, "get_url", return_value=MagicMock(status_code=200, text='{"data": [], "totalCount": 0}')) as fetch:
            c.fetch()
        params = parse_qs(urlsplit(fetch.call_args.args[0]).query)
        self.assertEqual(params["page"], ["1"])
        self.assertEqual(params["daterange"], ["2"])

    def test_freelancer_passes_both_calendar_bounds_to_server(self):
        c = FreelancerConnector()
        start, end = scrape_date_window()
        with patch.object(c, "open_url", return_value=io.BytesIO(b'{"result": {"projects": []}}')) as fetch:
            c.fetch("react developer")
        params = parse_qs(urlsplit(fetch.call_args.args[0].full_url).query)
        self.assertEqual(params["from_time"], [str(int(start.timestamp()))])
        self.assertEqual(params["to_time"], [str(int(end.timestamp())-1)])
        self.assertEqual(params["query"], ["react developer"])

    def test_unfiltered_feeds_request_small_recent_slice(self):
        for c, response, expected in [
            (RemotiveConnector(), b'{"jobs": []}', {"limit": ["100"]}),
            (HimalayasConnector(), b'{"jobs": []}', {"sort": ["recent"], "page": ["1"]}),
            (BossjobConnector(), b'{"code": 0, "data": {"jobs": []}}', {"size": ["30"], "sort": ["1"], "page": ["1"]}),
        ]:
            with self.subTest(platform=c.platform), patch.object(c, "open_url", return_value=io.BytesIO(response)) as fetch:
                c.fetch()
            params = parse_qs(urlsplit(fetch.call_args.args[0].full_url).query)
            for key, value in expected.items():
                self.assertEqual(params[key], value)

    def test_ziprecruiter_primary_cannot_bypass_jobspy_date_request(self):
        import pandas as pd
        scrape = MagicMock(return_value=pd.DataFrame())
        c = JobSpyAdapter("ZipRecruiter", "zip_recruiter", 2)
        with patch.dict("sys.modules", {"jobspy": SimpleNamespace(__file__="jobspy/__init__.py", scrape_jobs=scrape)}), \
                patch.object(c, "_fetch_ziprecruiter_ldjson", return_value=[]):
            c.fetch()
        scrape.assert_called_once()
        self.assertEqual(scrape.call_args.kwargs["hours_old"], scrape_request_hours())

    def test_ziprecruiter_fallback_also_requests_day_filter(self):
        c = JobSpyAdapter("ZipRecruiter", "zip_recruiter", 2)
        with patch.object(c, "get_url", return_value=MagicMock(status_code=200, text="")) as fetch:
            c._fetch_ziprecruiter_ldjson()
        self.assertEqual(fetch.call_count, 2)
        for call in fetch.call_args_list:
            params = parse_qs(urlsplit(call.args[0]).query)
            self.assertEqual(params["days"], ["2"])
            self.assertIn("search", params)

