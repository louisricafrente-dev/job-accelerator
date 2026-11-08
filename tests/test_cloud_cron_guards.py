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

    def test_queued_cron_supervises_worker_and_preserves_partial_result(self):
        from scripts.cloud_cron_sync import run
        command = {"id": "scheduled", "status": "queued"}
        result = {"status": "partial", "added": 3, "progress": {"unfinished": True}}
        with patch("scripts.cloud_cron_sync.is_turso_active", return_value=True), \
                patch("scripts.cloud_cron_sync.init_db"), \
                patch("scripts.cloud_cron_sync.get_user_setting", return_value="1"), \
                patch("src.execution_inbox.enqueue", return_value=command), \
                patch("src.execution_inbox.read", return_value={**command, "status": "partial", "result": result}), \
                patch("src.inbox_worker.run_cloud", return_value=result) as supervise, \
                patch("scripts.cloud_cron_sync.Aggregator"), patch("sys.argv", ["cloud_cron_sync.py"]):
            run()
        self.assertEqual(supervise.call_args.args[1], command["id"])

    def test_cron_database_failure_fails_the_workflow(self):
        from scripts.cloud_cron_sync import run
        command = {"id": "scheduled", "status": "queued"}
        with patch("scripts.cloud_cron_sync.is_turso_active", return_value=True), \
                patch("scripts.cloud_cron_sync.init_db"), \
                patch("scripts.cloud_cron_sync.get_user_setting", return_value="1"), \
                patch("src.execution_inbox.enqueue", return_value=command), \
                patch("src.execution_inbox.read", return_value={**command, "status": "error"}), \
                patch("src.inbox_worker.run_cloud", return_value={"status": "error"}), \
                patch("scripts.cloud_cron_sync.Aggregator"), patch("sys.argv", ["cloud_cron_sync.py"]):
            with self.assertRaises(SystemExit):
                run()

    @patch("scripts.cloud_cron_sync.is_turso_active", return_value=True)
    @patch("scripts.cloud_cron_sync.init_db")
    @patch("scripts.cloud_cron_sync.get_user_setting")
    @patch("src.execution_inbox.enqueue")
    @patch("src.inbox_worker.run_cloud", return_value=None)
    def test_cloud_cron_supervises_existing_local_worker(self, supervise, enqueue, mock_get_setting, mock_init, mock_turso):
        from scripts.cloud_cron_sync import run
        mock_get_setting.return_value = "1"
        enqueue.return_value = {
            "id": "local-cycle",
            "status": "running",
            "executor": "local",
            "lease_until": time.time() + 100
        }
        with patch("sys.argv", ["cloud_cron_sync.py"]), patch("src.execution_inbox.read", return_value={"id": "local-cycle", "status": "complete"}), patch("scripts.cloud_cron_sync.Aggregator"):
            run()
        self.assertEqual(supervise.call_args.args[1], "local-cycle")

    def test_cron_resumes_only_same_manila_day_partial_checkpoint(self):
        from scripts.cloud_cron_sync import run
        command = {"id": "scheduled", "status": "queued"}
        now = time.time()
        for requested_at, completed, expected in ((now, 2, True), (now - 86400, 2, False), (now, 3, False)):
            previous = {"id": "previous", "status": "partial", "requested_at": requested_at}
            saved = {"progress": {"completed_searches": completed, "total_searches": 3, "unfinished": True}}
            with self.subTest(expected=expected), patch("scripts.cloud_cron_sync.is_turso_active", return_value=True), \
                    patch("scripts.cloud_cron_sync.init_db"), patch("scripts.cloud_cron_sync.get_user_setting", return_value="1"), \
                    patch("src.daily_schedule.get_user_setting", return_value=json.dumps(saved)), patch("scripts.cloud_cron_sync.Aggregator"), \
                    patch("src.execution_inbox.enqueue", return_value=command) as enqueue, \
                    patch("src.execution_inbox.read", side_effect=[previous, {**command, "status": "complete"}]), \
                    patch("src.inbox_worker.run_cloud", return_value=None), patch("sys.argv", ["cloud_cron_sync.py"]):
                run()
            self.assertIs(enqueue.call_args.kwargs["resume"], expected)

    @patch("scripts.cloud_cron_sync.is_turso_active", return_value=True)
    @patch("scripts.cloud_cron_sync.init_db")
    @patch("scripts.cloud_cron_sync.get_user_setting")
    @patch("src.execution_inbox.enqueue")
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
