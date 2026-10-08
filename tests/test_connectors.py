import unittest
from unittest.mock import patch, MagicMock
from src.connectors.remote_feed import RemoteOKConnector, WeWorkRemotelyConnector
from src.connectors.ph_jobs import KalibrrConnector, BossjobConnector
from src.connectors.jobspy_adapter import JobSpyAdapter

class TestConnectors(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_remoteok_parsing(self, mock_urlopen):
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

    @patch("urllib.request.urlopen")
    def test_weworkremotely_parsing(self, mock_urlopen):
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

    def test_jobspy_adapter_fallback_when_uninstalled(self):
        # Should not crash if jobspy not installed
        adapter = JobSpyAdapter("LinkedIn", "linkedin", tier=1)
        with patch.dict("sys.modules", {"jobspy": None}):
            jobs = adapter.fetch()
            self.assertIsInstance(jobs, list)

if __name__ == "__main__":
    unittest.main()
