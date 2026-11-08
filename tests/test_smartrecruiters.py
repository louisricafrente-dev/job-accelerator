from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from src.connectors.smartrecruiters import SmartRecruitersConnector
from src.models import MANILA


class SmartRecruitersTests(TestCase):
    def test_public_feed_filters_before_detail_fetch_and_keeps_partial_results(self):
        today = datetime.now(MANILA).date()
        current = {"id": "123", "name": "Junior Software Engineer", "releasedDate": today.isoformat()}
        old = {**current, "id": "456", "releasedDate": (today - timedelta(days=8)).isoformat()}
        unrelated = {**current, "id": "789", "name": "Retail Cashier"}
        detail = {
            **current,
            "company": {"name": "Example"},
            "location": {"country": "ph", "fullLocation": "Manila, Philippines", "remote": True},
            "postingUrl": "https://jobs.smartrecruiters.com/Example/123-junior-software-engineer",
            "jobAd": {"sections": {"jobDescription": {"text": "<p>Build software.</p>"}}},
        }

        def response(_, url):
            if "/Unavailable/" in url:
                raise ValueError("HTTP 429")
            if url.endswith("/123"):
                return detail
            self.assertEqual(parse_qs(urlsplit(url).query)["country"], ["ph"])
            return {"content": [current, old, unrelated], "totalFound": 3}

        board = SmartRecruitersConnector()
        with patch("src.connectors.smartrecruiters.COMPANIES", ("Example", "Unavailable")), \
                patch.object(board, "_read_json", side_effect=response) as read:
            jobs = board.fetch()
        self.assertEqual(read.call_count, 3)
        self.assertEqual([job.job_url for job in jobs], [detail["postingUrl"]])
        self.assertEqual(jobs[0].description, "Build software.")
        self.assertEqual(board.last_raw_count, 3)
        self.assertEqual(board.last_error, "")
        self.assertIn("Unavailable", board.coverage_warning)

    def test_all_unavailable_reports_error(self):
        board = SmartRecruitersConnector()
        with patch("src.connectors.smartrecruiters.COMPANIES", ("Unavailable",)), \
                patch.object(board, "_read_json", side_effect=ValueError("HTTP 503")):
            self.assertEqual(board.fetch(), [])
        self.assertEqual(board.last_raw_count, 0)
        self.assertIn("HTTP 503", board.last_error)
