import os
import unittest
from datetime import datetime
from src.models import MANILA
from unittest.mock import patch

from src.connectors.remote_feed import UpworkConnector


class UpworkFlconsoleTests(unittest.TestCase):
    def test_maps_provider_job_to_canonical_upwork_link(self):
        record = {"upwork_id": "022114011265936675730", "title": "PHP Web Developer",
                  "description": "Build PHP and MySQL web applications", "job_type": "hourly",
                  "hourly_rate_from": 20, "hourly_rate_to": 30, "publish_at": datetime.now(MANILA).isoformat()}
        with patch.dict(os.environ, {"FLCONSOLE_MCP_TOKEN": "test"}), patch(
                "src.connectors.upwork_flconsole.rpc", return_value={"jobs": [record]}) as rpc:
            connector = UpworkConnector()
            jobs = connector.fetch("unrelated matrix keyword")
        self.assertTrue(connector.is_feed)
        self.assertEqual(jobs[0].job_url, "https://www.upwork.com/jobs/~022114011265936675730")
        self.assertEqual(jobs[0].salary, "USD 20-30/hr")
        self.assertEqual(jobs[0].date_posted, datetime.now(MANILA).date().isoformat())
        self.assertEqual(rpc.call_args.args[1]["limit"], 30)

    def test_failure_is_not_reported_as_successful_empty_feed_or_leaked(self):
        with patch.dict(os.environ, {"FLCONSOLE_MCP_TOKEN": "secret"}), patch(
                "src.connectors.upwork_flconsole.rpc", side_effect=ValueError("secret")):
            connector = UpworkConnector()
            self.assertEqual(connector.fetch(), [])
        self.assertIn("failed", connector.last_error)
        self.assertNotIn("secret", connector.last_error)

    def test_malformed_provider_response_fails(self):
        with patch.dict(os.environ, {"FLCONSOLE_MCP_TOKEN": "test"}), patch(
                "src.connectors.upwork_flconsole.rpc", return_value={}):
            connector = UpworkConnector()
            self.assertEqual(connector.fetch(), [])
        self.assertTrue(connector.last_error)
