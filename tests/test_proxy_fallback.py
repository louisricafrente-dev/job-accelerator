import json
import os
import tempfile
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.aggregator import Aggregator
from src.connectors.jobspy_adapter import JobSpyAdapter
from src.connectors.remote_feed import ContraConnector, RemoteOKConnector
from src.database import init_db, set_user_setting
from src.proxy_manager import get_next_proxy, request_routes


class TestProxyFallback(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "proxy.db")
        init_db(self.db)
        self.pool = ["http://test-user:secret-one@one.example:80", "http://test-user:secret-two@two.example:80"]
        set_user_setting(self.db, "proxy_list", "\n".join(self.pool))
        self.board = RemoteOKConnector()
        Aggregator(self.db, [self.board])
        for p in (patch.dict(os.environ, {}, clear=True), patch("src.proxy_manager._unavailable_until", {}), patch("src.proxy_manager._rr_index", 0)):
            p.start()
            self.addCleanup(p.stop)

    def test_direct_timeout_uses_one_configured_proxy_without_env_mutation(self):
        response = Mock(text="ok")
        before = dict(os.environ)
        with patch("curl_cffi.requests.Session.get", side_effect=[TimeoutError("timed out"), response]) as send:
            self.assertIs(self.board.get_url("https://example.com", timeout=1), response)
        self.assertEqual([c.kwargs["proxy"] for c in send.call_args_list], ["", self.pool[0]])
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(self.board.connection_retries, 1)

    def test_failed_cloud_proxy_uses_second_and_is_quarantined(self):
        with patch.dict(os.environ, {"FORCE_PROXY": "1"}), patch("curl_cffi.requests.Session.get", side_effect=[TimeoutError("timed out"), Mock(text="ok")]) as send:
            self.board.get_url("https://example.com")
            self.assertEqual([c.kwargs["proxy"] for c in send.call_args_list], self.pool)
            self.assertEqual(get_next_proxy(self.db), self.pool[1])

    def test_cloud_feed_uses_direct_without_spending_proxy_bandwidth(self):
        with patch.dict(os.environ, {"VERCEL": "1"}), patch("src.database.is_turso_active", return_value=False), patch("curl_cffi.requests.Session.get", return_value=Mock(text="ok")) as send:
            self.board.get_url("https://example.com")
        self.assertEqual([c.kwargs["proxy"] for c in send.call_args_list], [""])

    def test_linkedin_starts_with_proxy_without_a_direct_rate_limit(self):
        board = JobSpyAdapter("LinkedIn", "linkedin", 1)
        Aggregator(self.db, [board])
        send = Mock(return_value="ok")
        self.assertEqual(board.request_with_fallback(send), "ok")
        send.assert_called_once_with(self.pool[0])

    def test_quota_error_stops_entire_pool_across_process_state(self):
        set_user_setting(self.db, "proxy_mode", "always")
        error = urllib.error.HTTPError("https://example.com", 402, "Payment Required", {}, None)
        with patch("curl_cffi.requests.Session.get", side_effect=error) as send:
            with self.assertRaisesRegex(RuntimeError, "quota exhausted"):
                self.board.get_url("https://example.com")
        self.assertEqual(send.call_count, 1)
        with patch("src.proxy_manager._unavailable_until", {}):
            self.assertIsNone(get_next_proxy(self.db))
            set_user_setting(self.db, "proxy_mode", "hybrid")
            self.assertEqual(request_routes(self.db), [None])
            set_user_setting(self.db, "proxy_list", "http://replacement:password@new.example:80")
            self.assertIsNotNone(get_next_proxy(self.db))

    def test_disabled_mode_never_spends_proxy_bandwidth(self):
        set_user_setting(self.db, "proxy_mode", "disabled")
        with patch("curl_cffi.requests.Session.get", side_effect=TimeoutError("timed out")) as send:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                self.board.get_url("https://example.com")
        self.assertEqual(send.call_count, 1)

    def test_access_blocks_do_not_rotate_or_quarantine_proxy(self):
        set_user_setting(self.db, "proxy_mode", "always")
        for code in (403, 404, 410, 429):
            error = urllib.error.HTTPError("https://example.com", code, "blocked", {"Retry-After": "30000"}, None)
            with self.subTest(code=code), patch("curl_cffi.requests.Session.get", side_effect=error) as send:
                with self.assertRaises(RuntimeError):
                    self.board.get_url("https://example.com")
                self.assertEqual(send.call_count, 1)
                self.assertEqual(self.board.retry_after, 30000)
        from src.proxy_manager import _unavailable_until
        self.assertEqual(_unavailable_until, {})

    def test_html_challenge_is_not_empty_success_or_rotated(self):
        response = Mock(text='<html><script src="/cdn-cgi/challenge-platform/test"></script></html>')
        with patch("curl_cffi.requests.Session.get", return_value=response) as send:
            with self.assertRaisesRegex(RuntimeError, "Cloudflare challenge"):
                self.board.get_url("https://example.com")
        self.assertEqual(send.call_count, 1)

    def test_body_timeout_also_falls_back_and_keeps_feed_results(self):
        direct = Mock()
        direct.__enter__ = Mock(return_value=direct)
        direct.__exit__ = Mock(return_value=False)
        direct.read.side_effect = TimeoutError("body timed out")
        proxied = Mock()
        proxied.__enter__ = Mock(return_value=proxied)
        proxied.__exit__ = Mock(return_value=False)
        proxied.read.return_value = json.dumps([{"position": "Junior Software Developer", "company": "Example", "location": "Worldwide", "url": "https://example.com/job", "date": "today"}]).encode()
        with patch("urllib.request.urlopen", return_value=direct), patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = proxied
            jobs = self.board.fetch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(self.board.connection_retries, 1)

    def test_jobspy_retries_empty_connection_error_with_saved_proxy(self):
        import pandas as pd
        failed = pd.DataFrame()
        failed.attrs["errors"] = {"indeed": "Connection timeout"}
        send = Mock(side_effect=[failed, pd.DataFrame()])
        board = JobSpyAdapter("Indeed", "indeed", 1)
        Aggregator(self.db, [board])
        with patch.dict("sys.modules", {"jobspy": SimpleNamespace(scrape_jobs=send)}):
            board.fetch()
        self.assertEqual(send.call_args_list[0].kwargs["proxies"], None)
        self.assertEqual(send.call_args_list[1].kwargs["proxies"], [self.pool[0]])

    def test_jobspy_logged_failure_is_not_reported_as_empty_success(self):
        import logging
        import pandas as pd
        def failed_scrape(**kwargs):
            logging.getLogger("JobSpy:LinkedIn").error("LinkedIn response status code 429")
            return pd.DataFrame()
        board = JobSpyAdapter("LinkedIn", "linkedin", 1)
        Aggregator(self.db, [board])
        with patch.dict("sys.modules", {"jobspy": SimpleNamespace(scrape_jobs=failed_scrape)}):
            self.assertEqual(board.fetch(), [])
        self.assertIn("429", board.last_error)
        self.assertFalse(logging.getLogger("JobSpy:LinkedIn").handlers)

    def test_proxy_credentials_are_redacted_from_errors(self):
        with patch("curl_cffi.requests.Session.get", side_effect=TimeoutError("failed proxy " + self.pool[0])):
            with self.assertRaises(RuntimeError) as error:
                self.board.get_url("https://example.com")
        self.assertNotIn("secret-one", str(error.exception))
        self.assertNotIn("test-user", str(error.exception))

    def test_concurrent_connectors_keep_their_saved_proxy_settings(self):
        other = str(Path(self.temp.name) / "other.db")
        init_db(other)
        set_user_setting(other, "proxy_mode", "always")
        set_user_setting(other, "proxy_list", "http://other:other-secret@other.example:80")
        set_user_setting(self.db, "proxy_mode", "disabled")
        with ThreadPoolExecutor(2) as pool:
            local, proxied = list(pool.map(request_routes, [self.db, other]))
        self.assertEqual(local, [None])
        self.assertEqual(proxied, ["http://other:other-secret@other.example:80"])

    def test_failed_feed_is_not_cached_as_a_success(self):
        board = ContraConnector()
        Aggregator(self.db, [board])
        with patch.object(ContraConnector, "_cached_jobs", None), patch.object(ContraConnector, "_last_fetch", 0), patch.object(board, "open_url", side_effect=RuntimeError("HTTP 403")) as send:
            board.fetch()
            board.fetch()
        self.assertEqual(send.call_count, 2)
        self.assertEqual(board.last_error, "HTTP 403")

    def test_blocked_source_does_not_stop_successful_source_or_lose_checkpoint(self):
        from src.models import Job
        from src.sync_batches import run_batch
        class GoodBoard(RemoteOKConnector):
            platform = "Good feed"
            def fetch(self, query="", location=""):
                return [Job("Junior Software Developer", "Example", "Remote", self.platform, 1, "https://example.com/job", date_posted="today")]
        good = GoodBoard()
        aggregator = Aggregator(self.db, [self.board, good])
        with patch.object(self.board, "open_url", side_effect=RuntimeError("HTTP 403")), patch.object(good, "fetch", wraps=good.fetch) as fetch:
            first = run_batch(aggregator, ["developer"], budget_seconds=2, cycle_id="same-run")
            second = run_batch(Aggregator(self.db, [self.board, good]), ["developer"], budget_seconds=2, cycle_id="same-run")
        self.assertEqual(first["added"], 1)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(second["progress"]["boards"]["Good feed"]["cursor"], 1)
        self.assertEqual(second["progress"]["boards"]["Remote OK"]["retry"], [0])

    def test_retry_after_is_preserved_in_the_saved_board_cooldown(self):
        import time
        from src.sync_batches import run_batch
        error = urllib.error.HTTPError("https://example.com", 429, "rate limit", {"Retry-After": "30000"}, None)
        started = time.time()
        with patch("urllib.request.urlopen", side_effect=error) as send:
            result = run_batch(Aggregator(self.db, [self.board]), ["developer"], budget_seconds=2)
        self.assertEqual(send.call_count, 1)
        self.assertGreaterEqual(result["progress"]["boards"]["Remote OK"]["next_at"], started + 30000)
