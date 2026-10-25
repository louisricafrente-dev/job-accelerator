import unittest
from unittest.mock import patch, MagicMock
from src.connectors.remote_feed import RemoteOKConnector, WeWorkRemotelyConnector
from src.connectors.ph_jobs import KalibrrConnector, BossjobConnector
from src.connectors.jobspy_adapter import JobSpyAdapter

class TestConnectors(unittest.TestCase):
    @patch("src.connectors.remote_feed.is_within_15_days", return_value=True)
    @patch("urllib.request.urlopen")
    def test_remoteok_parsing(self, mock_urlopen, mock_is_within):
        mock_response = MagicMock()
        mock_response.read.return_value = b'''[
            {"legal": "disclaimer"},
            {
                "id": "123",
                "position": "Junior Full Stack Engineer",
                "company": "RemoteCorp",
                "location": "Worldwide",
                "url": "https://remoteok.com/remote-jobs/123",
                "salary_min": 50000,
                "salary_max": 70000,
                "date": "2026-10-08T12:00:00Z"
            }
        ]'''
        mock_urlopen.return_value.__enter__.return_value = mock_response

        connector = RemoteOKConnector()
        jobs = connector.fetch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Junior Full Stack Engineer")
        self.assertEqual(jobs[0].experience_level, "Junior / Entry")
        self.assertEqual(jobs[0].tier, 3)

    @patch("src.connectors.remote_feed.is_within_15_days", return_value=True)
    @patch("urllib.request.urlopen")
    def test_weworkremotely_parsing(self, mock_urlopen, mock_is_within):
        mock_response = MagicMock()
        mock_response.read.return_value = b'''<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>GitLab: Senior Go Developer</title>
              <link>https://weworkremotely.com/jobs/1</link>
              <pubDate>Thu, 08 Oct 2026 12:00:00 +0000</pubDate>
            </item>
          </channel>
        </rss>'''
        mock_urlopen.return_value.__enter__.return_value = mock_response

        connector = WeWorkRemotelyConnector()
        jobs = connector.fetch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "GitLab")
        self.assertEqual(jobs[0].title, "Senior Go Developer")
        self.assertEqual(jobs[0].experience_level, "Senior / Lead")

    @patch("urllib.request.urlopen")
    def test_connector_network_error_isolation(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection Timeout")
        connector = KalibrrConnector()
        # Must return empty list, NOT crash
        jobs = connector.fetch()
        self.assertEqual(jobs, [])

    @patch("urllib.request.urlopen")
    def test_connector_logs_error_on_failure(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Rate limit 429")
        connector = KalibrrConnector()
        with self.assertLogs("connectors", level="ERROR") as cm:
            jobs = connector.fetch()
            self.assertEqual(jobs, [])
            self.assertTrue(any("Rate limit 429" in msg for msg in cm.output))

    def test_jobspy_adapter_fallback_when_uninstalled(self):
        # Should not crash if jobspy not installed
        adapter = JobSpyAdapter("LinkedIn", "linkedin", tier=1)
        with patch.dict("sys.modules", {"jobspy": None}):
            jobs = adapter.fetch()
            self.assertIsInstance(jobs, list)

    @patch("urllib.request.urlopen")
    def test_onlinejobs_parsing(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'''
        <div class="jobpost-cat-box">
            <h4>Full Stack Web Developer<span class="badge">Full Time</span></h4>
            <p class="fs-13" data-temp="2026-10-12 10:00:00">Posted on 2026-10-12</p>
            <dd class="col">$1,500/month</dd>
            <div class="desc">Company: Apex Digital Labs. We are hiring a full stack developer... <a href="/jobseekers/job/apex-123">See More</a></div>
        </div>
        '''
        mock_urlopen.return_value.__enter__.return_value = mock_response

        from src.connectors.ph_jobs import OnlineJobsConnector
        connector = OnlineJobsConnector()
        jobs = connector.fetch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Full Stack Web Developer")
        self.assertEqual(jobs[0].company, "Apex Digital Labs")
        self.assertEqual(jobs[0].salary, "$1,500/month")
        self.assertEqual(jobs[0].tier, 1)
        self.assertEqual(jobs[0].platform, "OnlineJobs.ph")
        self.assertEqual(jobs[0].job_url, "https://www.onlinejobs.ph/jobseekers/job/apex-123")

    @patch("urllib.request.urlopen")
    def test_wellfound_parsing_and_filtering(self, mock_urlopen):
        import json
        import time
        from src.connectors.remote_feed import WellfoundConnector

        # Reset cache
        WellfoundConnector._cached_jobs = None
        WellfoundConnector._last_fetch = 0

        now_ts = int(time.time())
        apollo_state = {
            "data": {
                "StartupResult:101": {
                    "name": "Stripe Partner Tech",
                    "highlightedJobListings": [{"__ref": "JobListingSearchResult:201"}, {"__ref": "JobListingSearchResult:202"}]
                },
                # Job 1: Remote Worldwide -> Should pass
                "JobListingSearchResult:201": {
                    "id": "201",
                    "title": "Junior Android Developer",
                    "slug": "junior-android-developer",
                    "compensation": "$80k - $100k",
                    "remote": True,
                    "locationNames": ["Remote Worldwide"],
                    "liveStartAt": now_ts,
                    "description": "Building mobile apps with Kotlin and Jetpack Compose"
                },
                # Job 2: Onsite Mumbai -> Foreign onsite, must be filtered out!
                "JobListingSearchResult:202": {
                    "id": "202",
                    "title": "Software Engineer",
                    "slug": "software-engineer",
                    "compensation": "$30k",
                    "remote": False,
                    "locationNames": ["Mumbai, India"],
                    "liveStartAt": now_ts,
                    "description": "Onsite Mumbai backend development"
                }
            }
        }

        html = f"""
        <html>
            <script id="__NEXT_DATA__" type="application/json">
            {{"props": {{"pageProps": {{"apolloState": {json.dumps(apollo_state)}}}}}}}
            </script>
        </html>
        """
        mock_response = MagicMock()
        mock_response.read.return_value = html.encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        connector = WellfoundConnector()
        # Mock ROLES to single test role to keep test fast
        with patch.object(connector, "ROLES", ["android-developer"]):
            jobs = connector.fetch()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Junior Android Developer")
        self.assertEqual(jobs[0].company, "Stripe Partner Tech")
        self.assertEqual(jobs[0].platform, "Wellfound")
        self.assertEqual(jobs[0].location, "Remote Worldwide")
        self.assertEqual(jobs[0].job_url, "https://wellfound.com/jobs/201-junior-android-developer")

    @patch("urllib.request.urlopen")
    def test_contra_parsing(self, mock_urlopen):
        import json
        from src.connectors.remote_feed import ContraConnector

        ContraConnector._cached_jobs = None
        ContraConnector._last_fetch = 0

        vike_context = {
            "publicAppConfiguration": {
                "relayRecordMap": {
                    "Record:1": {
                        "__typename": "Opportunity",
                        "title": "Full Stack React Developer Project",
                        "slug": "react-dev-project-123"
                    }
                }
            }
        }
        html = f"""
        <html>
            <script id="vike_pageContext" type="application/json">
            {json.dumps(vike_context)}
            </script>
        </html>
        """
        mock_response = MagicMock()
        mock_response.read.return_value = html.encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        connector = ContraConnector()
        jobs = connector.fetch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Full Stack React Developer Project")
        self.assertEqual(jobs[0].company, "Direct Client (Contra)")
        self.assertEqual(jobs[0].platform, "Contra")
        self.assertEqual(jobs[0].job_url, "https://contra.com/opportunity/react-dev-project-123")

    @patch("curl_cffi.requests.Session.get")
    def test_flexjobs_parsing(self, mock_cffi_get):
        from src.connectors.remote_feed import FlexJobsConnector

        FlexJobsConnector._cached_jobs = None
        FlexJobsConnector._last_fetch = 0

        html = """
        <html>
            <ul class="job-list">
                <li class="job">
                    <a class="job-title" href="/jobs/telecommuting-software-dev-999">Remote Web Application Developer</a>
                    <span class="job-company">HealthTech Innovations</span>
                </li>
            </ul>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_cffi_get.return_value = mock_resp

        connector = FlexJobsConnector()
        jobs = connector.fetch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Remote Web Application Developer")
        self.assertEqual(jobs[0].company, "HealthTech Innovations")
        self.assertEqual(jobs[0].platform, "FlexJobs")
        self.assertEqual(jobs[0].job_url, "https://www.flexjobs.com/jobs/telecommuting-software-dev-999")

if __name__ == "__main__":
    unittest.main()
