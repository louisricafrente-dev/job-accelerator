import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("polling_worker", Path(__file__).resolve().parents[1] / "scripts/local_worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class TestWorkerPolling(unittest.TestCase):
    def test_idle_loop_registers_once_and_picks_up_command_after_wait(self):
        stop = Mock()
        request = {"id": "queued-command"}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(worker, "LOCAL_DATA", Path(directory)), \
                patch.object(worker, "load_token"), patch.object(worker, "init_db"), \
                patch.object(worker, "get_user_setting", return_value=""), \
                patch("src.aggregator.Aggregator"), patch.object(worker.threading, "Thread"), \
                patch.object(worker.threading, "Event", return_value=stop), \
                patch.object(worker, "heartbeat") as heartbeat, \
                patch.object(worker, "api_call", side_effect=[{"request": None}, {"request": None}, {"request": request}, KeyboardInterrupt]), \
                patch.object(worker, "run_request", return_value=None) as run:
            worker.run_worker()
        heartbeat.assert_called_once()
        self.assertEqual([call.args[0] for call in stop.wait.call_args_list], [30, 30])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], request)
        stop.set.assert_called_once()

    def test_heartbeat_thread_keeps_active_lease_alive_every_15_seconds(self):
        stop = Mock()
        stop.wait.side_effect = [False, False, True]
        with patch.object(worker, "heartbeat") as heartbeat:
            worker.keep_alive("worker", ["active-command"], stop)
        self.assertEqual(heartbeat.call_count, 2)
        heartbeat.assert_called_with("worker", "active-command", None)
        self.assertTrue(all(call.args == (15,) for call in stop.wait.call_args_list))

    def test_failed_startup_heartbeat_is_retried(self):
        stop = Mock()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(worker, "LOCAL_DATA", Path(directory)), \
                patch.object(worker, "load_token"), patch.object(worker, "init_db"), \
                patch.object(worker, "get_user_setting", return_value=""), \
                patch("src.aggregator.Aggregator"), patch.object(worker.threading, "Thread"), \
                patch.object(worker.threading, "Event", return_value=stop), \
                patch.object(worker, "heartbeat", side_effect=[OSError("offline"), None]) as heartbeat, \
                patch.object(worker, "api_call", side_effect=KeyboardInterrupt):
            worker.run_worker()
        self.assertEqual(heartbeat.call_count, 2)
        stop.wait.assert_called_once_with(15)
