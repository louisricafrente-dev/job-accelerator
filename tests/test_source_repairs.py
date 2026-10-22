import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.connectors.ph_jobs import BossjobConnector, JobStreetConnector
from src.connectors.remote_feed import UpworkConnector


class TestSourceRepairs(unittest.TestCase):
    def test_bossjob_uses_current_public_search_and_original_publication_date(self):
        today = datetime.now(timezone.utc).date()
        records = [{"id": 123, "job_title": "Junior Software Developer", "company_name": "Example", "job_country": "Philippines",
                    "job_location": "Manila", "job_url": "/job/software-developer-manila-123", "published_at": str(today),
                    "salary_range_value": "PHP 30-40K"},
                   {"id": 124, "job_title": "Junior Software Developer", "job_url": "/job/old-124", "job_country": "Philippines",
                    "published_at": str(today - timedelta(days=40)), "updated_at": str(today)}]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"code": 0, "data": {"jobs": records}}).encode()
        with patch("urllib.request.urlopen", return_value=response) as fetch:
            jobs = BossjobConnector().fetch()
        self.assertIn("/bossjob-api-server/jobs/search?", fetch.call_args.args[0].full_url)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].job_url, "https://bossjob.ph/en/job/software-developer-manila-123")
        self.assertEqual(jobs[0].salary, "PHP 30-40K")

    def test_jobstreet_slash_keyword_does_not_create_nested_url_path(self):
        response = MagicMock(status_code=200, text="<html></html>")
        with patch("curl_cffi.requests.Session.get", return_value=response) as fetch:
            JobStreetConnector().fetch("HTML / CSS")
        self.assertEqual(fetch.call_args.args[0], "https://ph.jobstreet.com/html-css-jobs?page=1")

    def test_upwork_does_not_retry_retired_rss_without_authorized_feed(self):
        board = UpworkConnector()
        with patch.dict(os.environ, {"UPWORK_FEED_URL": ""}), patch("curl_cffi.requests.Session.get") as fetch:
            self.assertEqual(board.fetch(), [])
        fetch.assert_not_called()
        self.assertIn("Configuration required:", board.last_error)

    def test_curl_transport_uses_supported_session_options(self):
        import inspect
        from curl_cffi.requests import Session
        self.assertIn("proxy", inspect.signature(Session.request).parameters)
        self.assertNotIn("trust_env", inspect.signature(Session.request).parameters)
        # Session construction is real: an unsupported option fails before any mock network call.
        response = MagicMock(status_code=200, text="ok")
        with patch.object(Session, "get", return_value=response):
            self.assertIs(JobStreetConnector().get_url("https://example.com", timeout=1), response)
