import unittest
from unittest.mock import patch, MagicMock
import json
import time
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.daily_schedule import day as get_manila_day


class CloudCronGuardsTests(unittest.TestCase):

    @patch("scripts.cloud_cron_sync.is_turso_active", return_value=True)
    @patch("scripts.cloud_cron_sync.init_db")
    @patch("scripts.cloud_cron_sync.get_user_setting")
    @patch("src.execution_inbox.read")
    @patch("src.aggregator.Aggregator.run_sync")
    def test_cloud_cron_yields_when_local_worker_running(self, mock_run_sync, mock_inbox_read, mock_get_setting, mock_init, mock_turso):
        from scripts.cloud_cron_sync import run
        mock_get_setting.return_value = "1"
        mock_inbox_read.return_value = {
            "status": "running",
            "executor": "local",
            "lease_until": time.time() + 100
        }
        with patch("sys.argv", ["cloud_cron_sync.py"]):
            run()
        mock_run_sync.assert_not_called()

    @patch("scripts.cloud_cron_sync.is_turso_active", return_value=True)
    @patch("scripts.cloud_cron_sync.init_db")
    @patch("scripts.cloud_cron_sync.get_user_setting")
    @patch("src.execution_inbox.read")
    @patch("src.aggregator.Aggregator.run_sync")
    def test_cloud_cron_yields_when_cloud_worker_running(self, mock_run_sync, mock_inbox_read, mock_get_setting, mock_init, mock_turso):
        from scripts.cloud_cron_sync import run
        mock_get_setting.return_value = "1"
        mock_inbox_read.return_value = {
            "status": "running",
            "executor": "cloud",
            "lease_until": time.time() + 100
        }
        with patch("sys.argv", ["cloud_cron_sync.py"]):
            run()
        mock_run_sync.assert_not_called()

    @patch("scripts.daily_notifier.get_user_setting")
    @patch("scripts.daily_notifier.generate_digest_data")
    def test_daily_notifier_skips_when_already_sent_today(self, mock_gen_data, mock_get_setting):
        from scripts.daily_notifier import send_daily_email
        today = get_manila_day()
        mock_get_setting.return_value = today
        res = send_daily_email("test.db", force=False)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("status"), "already_sent")
        mock_gen_data.assert_not_called()


if __name__ == "__main__":
    unittest.main()
