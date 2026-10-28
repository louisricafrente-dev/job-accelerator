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
        today = datetime.now(timezone.utc).date().isoformat()
        payload = {"data": [{"id": "95451582", "title": "Junior Frontend Developer", "teaser": "Build React and HTML / CSS web apps",
                             "listingDate": today, "salaryLabel": "PHP 35,000", "advertiser": {"description": "ePLDT"},
                             "locations": [{"label": "Makati City, Metro Manila"}]}]}
        response = MagicMock(status_code=200, text=json.dumps(payload))
        with patch("curl_cffi.requests.Session.get", return_value=response) as fetch:
            jobs = JobStreetConnector().fetch("HTML / CSS")
        self.assertIn("https://ph.jobstreet.com/api/jobsearch/v5/search?", fetch.call_args.args[0])
        self.assertIn("keywords=HTML+%2F+CSS", fetch.call_args.args[0])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].job_url, "https://ph.jobstreet.com/job/95451582")

    def test_upwork_does_not_retry_retired_rss_without_authorized_feed(self):
        board = UpworkConnector()
        with patch.dict(os.environ, {"UPWORK_FEED_URL": "", "FLCONSOLE_MCP_TOKEN": ""}), patch("curl_cffi.requests.Session.get") as fetch:
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


    def test_jobstreet_paginates_even_when_first_page_is_all_senior(self):
        from urllib.parse import parse_qs, urlsplit
        today = datetime.now(timezone.utc).date().isoformat()
        def response(url, **kwargs):
            params = parse_qs(urlsplit(url).query)
            self.assertEqual(params['keywords'], ['QA Automation'])
            page = int(params['page'][0])
            rows = ([{'id': str(i), 'title': 'Senior Developer', 'listingDate': today} for i in range(50)]
                    if page == 1 else [{'id': '100', 'title': 'Junior QA Engineer', 'listingDate': today}])
            return MagicMock(status_code=200, text=json.dumps({'data': rows}))
        with patch.object(JobStreetConnector, 'get_url', side_effect=response) as fetch:
            jobs = JobStreetConnector().fetch('QA Automation')
        self.assertFalse(JobStreetConnector.is_feed)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual([j.title for j in jobs], ['Junior QA Engineer'])

    def test_jobstreet_bounds_repeated_pages(self):
        today = datetime.now(timezone.utc).date().isoformat()
        rows = [{'id': str(i), 'title': 'Junior Developer', 'listingDate': today} for i in range(50)]
        with patch.object(JobStreetConnector, 'get_url', return_value=MagicMock(status_code=200, text=json.dumps({'data': rows}))) as fetch:
            self.assertEqual(len(JobStreetConnector().fetch('developer')), 50)
        self.assertEqual(fetch.call_count, 2)

    def test_fallbacks_do_not_invent_publication_dates(self):
        from src.connectors.jobspy_adapter import JobSpyAdapter
        from src.connectors.remote_feed import FlexJobsConnector, ContraConnector
        from src.models import is_within_15_days
        html = '<script type="application/ld+json">' + json.dumps({'itemListElement': [
            {'name': 'Junior Web Developer', 'url': 'https://www.ziprecruiter.com/c/example/Job/dev'}]}) + '</script>'
        with patch.object(JobSpyAdapter, 'get_url', return_value=MagicMock(status_code=200, text=html)):
            jobs = JobSpyAdapter('ZipRecruiter', 'zip_recruiter', 2)._fetch_ziprecruiter_ldjson()
        self.assertEqual(jobs[0].date_posted, '')
        self.assertFalse(is_within_15_days(jobs[0].date_posted))
        xml = b'<urlset><url><loc>https://www.flexjobs.com/gjw/example/junior-web-developer/123</loc><lastmod>2026-10-25</lastmod></url></urlset>'
        with patch.object(FlexJobsConnector, 'get_url', return_value=MagicMock(status_code=200, content=xml)):
            jobs = FlexJobsConnector()._fetch_gjw_sitemap()
        self.assertEqual(jobs[0].date_posted, '', 'Sitemap modification is not a publication date')
        ContraConnector._cached_jobs = None
        context = {'publicAppConfiguration': {'relayRecordMap': {'1': {
            '__typename': 'Opportunity', 'title': 'Junior Web Developer', 'slug': 'dev', 'datePosted': '2020-01-01'}}}}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = ('<script id="vike_pageContext">' + json.dumps(context) + '</script>').encode()
        with patch.object(ContraConnector, 'open_url', return_value=response):
            jobs = ContraConnector().fetch()
        self.assertEqual(jobs[0].date_posted, '2020-01-01')
        self.assertFalse(is_within_15_days(jobs[0].date_posted))
        ContraConnector._cached_jobs = None
