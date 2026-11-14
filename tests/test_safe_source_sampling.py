import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from src.connectors.ph_jobs import BossjobConnector
from src.connectors.remote_feed import RemoteOKConnector
from src.models import normalize_date, is_today_or_yesterday


class TestSafeSourceSampling(unittest.TestCase):
    def test_normalizing_first_cannot_turn_unknown_dates_into_today(self):
        for raw in ("recently", "recent", "Posted recently", "posted recent", "new", "active today",
                    "2026-10-30 garbage", "2026-99-01"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_date(raw), "")
                self.assertFalse(is_today_or_yesterday(normalize_date(raw)))
        self.assertEqual(normalize_date("today", datetime(2026, 10, 28, 16, 30, tzinfo=timezone.utc)), "2026-10-29")

    def boss_page(self, board, page, *, useful=True, total=10):
        item = {"id": page, "job_title": "Software Developer", "job_country": "Philippines",
                "published_at": "today" if useful else "2020-01-01", "job_url": f"/job/{page}"}
        payload = {"code": 0, "data": {"jobs": [item], "total_pages": total}}
        with patch.object(board, "open_url", return_value=io.BytesIO(json.dumps(payload).encode())):
            jobs = board.fetch("developer")
        self.assertFalse(board.last_error)
        board.query_state = dict(board.next_query_state)
        return jobs

    def test_bossjob_reaches_provider_end_past_old_page_cap(self):
        board = BossjobConnector()
        for page in range(1, 11):
            jobs = self.boss_page(board, page, useful=page == 10)
            self.assertEqual(board.has_more, page < 10)
            self.assertEqual(len(jobs), int(page == 10))
        self.assertEqual(board.coverage_warning, "")

    def test_urllib_size_limit_stops_reading_and_does_not_retry(self):
        board = RemoteOKConnector()
        board.MAX_RESPONSE_BYTES = 8
        stream = io.BytesIO(b"x" * 100)
        stream.close = Mock(return_value=None)
        with patch("urllib.request.urlopen", return_value=stream) as send:
            with self.assertRaisesRegex(RuntimeError, "size limit"):
                board.open_url("https://example.com")
        self.assertEqual(stream.tell(), 9)
        self.assertEqual(send.call_count, 1)

    def test_curl_chunks_are_reassembled_and_oversize_aborts_without_retry(self):
        board = RemoteOKConnector()
        board.MAX_RESPONSE_BYTES = 8
        response = Mock(text="valid")
        def small(url, **kwargs):
            kwargs["content_callback"](b"abc")
            kwargs["content_callback"](b"def")
            return response
        with patch("curl_cffi.requests.Session.get", side_effect=small):
            self.assertEqual(board.get_url("https://example.com").content, b"abcdef")
        def big(url, **kwargs):
            kwargs["content_callback"](b"12345678")
            kwargs["content_callback"](b"9")
        with patch("curl_cffi.requests.Session.get", side_effect=big) as send:
            with self.assertRaisesRegex(RuntimeError, "size limit"):
                board.get_url("https://example.com")
        self.assertEqual(send.call_count, 1)
