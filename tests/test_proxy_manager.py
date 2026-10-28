import os
import unittest
from unittest.mock import patch
from src.proxy_manager import (
    parse_proxy_line,
    parse_proxy_list,
    format_proxy_for_display,
    get_proxy_settings,
    is_proxy_active,
    get_next_proxy,
    apply_proxy_environment,
)


TEST_PROXIES = ["http://test-user:test-pass@one.example:8080"]


class TestProxyManager(unittest.TestCase):
    def test_no_implicit_proxy_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_proxy_settings()["proxies"], [])
            self.assertEqual(get_proxy_settings()["raw"], "")

    def test_parse_and_format_proxy_line(self):
        line = "one.example:8080:test-user:test-pass"
        url = parse_proxy_line(line)
        self.assertEqual(url, "http://test-user:test-pass@one.example:8080")
        formatted = format_proxy_for_display(url)
        self.assertEqual(formatted, line)

    def test_parse_proxy_list(self):
        text = """
        # Comment
        one.example:8080:test-user:test-pass
        http://test-user:test-pass@two.example:8081
        
        # Duplicate
        one.example:8080:test-user:test-pass
        """
        parsed = parse_proxy_list(text)
        self.assertEqual(len(parsed), 2)

    def test_hybrid_mode_cloud_vs_local(self):
        with patch.dict(os.environ, {"PROXY_URL": TEST_PROXIES[0]}, clear=True):
            # Local laptop run without VERCEL env -> Inactive (bypassed to save data)
            self.assertFalse(is_proxy_active())
            self.assertIsNone(apply_proxy_environment())
            self.assertNotIn("HTTP_PROXY", os.environ)

            with patch.dict(os.environ, {"VERCEL": "1"}):
                self.assertFalse(is_proxy_active())
                self.assertIsNone(apply_proxy_environment())
            with patch.dict(os.environ, {"FORCE_PROXY": "1"}):
                self.assertTrue(is_proxy_active())
                self.assertIsNotNone(apply_proxy_environment())

    def test_always_and_disabled_modes(self):
        with patch("src.proxy_manager.get_proxy_settings", return_value={"mode": "disabled", "proxies": TEST_PROXIES}):
            with patch.dict(os.environ, {"VERCEL": "1"}):
                self.assertFalse(is_proxy_active())

        with patch("src.proxy_manager.get_proxy_settings", return_value={"mode": "always", "proxies": TEST_PROXIES}):
            with patch.dict(os.environ, {"PROXY_URL": TEST_PROXIES[0]}, clear=True):
                self.assertTrue(is_proxy_active())


if __name__ == "__main__":
    unittest.main()
