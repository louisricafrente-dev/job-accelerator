import os
import tempfile
import unittest
import runpy
import subprocess
from pathlib import Path
from unittest.mock import patch

from src.database import init_db, insert_jobs, get_jobs, update_job_status
from src.models import Job


class TestWorkflowIsolation(unittest.TestCase):
    def test_same_day_requisitions_and_cross_board_bridge_stay_independent(self):
        with tempfile.TemporaryDirectory() as temp:
            db = os.path.join(temp, "identity_test.db")
            init_db(db)
            board_a = Job("Android Developer", "Example", "Manila", "Indeed", 1, "https://indeed.example/a", date_posted="2026-10-20")
            first = Job("Android Developer", "Example", "Manila", "LinkedIn", 1, "https://linkedin.example/111", date_posted="2026-10-20")
            second = Job("Android Developer", "Example", "Manila", "LinkedIn", 1, "https://linkedin.example/222", date_posted="2026-10-20")
            self.assertEqual(insert_jobs(db, [board_a, first, second]), (2, 1))
            rows = get_jobs(db)
            self.assertEqual(len(rows), 2)
            a = next(row for row in rows if row["job_url"] == board_a.job_url)
            b = next(row for row in rows if row["job_url"] == second.job_url)
            update_job_status(db, a["id"], status="applied", notes="Application A")
            update_job_status(db, b["id"], status="saved", notes="Separate B")
            self.assertEqual(insert_jobs(db, [first, second]), (0, 2))
            rows = get_jobs(db)
            self.assertEqual(len(rows), 2)
            self.assertEqual(next(row for row in rows if row["id"] == a["id"])["status"], "applied")
            self.assertEqual(next(row for row in rows if row["id"] == b["id"])["status"], "saved")
            self.assertEqual(next(row for row in rows if row["id"] == a["id"])["notes"], "Application A")
            self.assertEqual(next(row for row in rows if row["id"] == b["id"])["notes"], "Separate B")
            self.assertIsNotNone(next(row for row in rows if row["id"] == a["id"])["applied_at"])
            self.assertIsNone(next(row for row in rows if row["id"] == b["id"])["applied_at"])

    def test_late_preference_write_cannot_overwrite_newer_value(self):
        from src.database import set_user_setting, get_user_setting, get_all_user_settings
        with tempfile.TemporaryDirectory() as temp:
            db = os.path.join(temp, "revision_test.db")
            init_db(db)
            set_user_setting(db, "view_filters", "old legacy value")
            set_user_setting(db, "view_filters", "newest", revision=200)
            set_user_setting(db, "view_filters", "late stale request", revision=100)
            self.assertEqual(get_user_setting(db, "view_filters"), "newest")
            self.assertEqual(get_all_user_settings(db)["view_filters"], "newest")
            set_user_setting(db, "view_filters", "newest", revision=200)
            self.assertEqual(get_user_setting(db, "view_filters"), "newest")

    def test_deploy_does_not_start_when_checks_fail(self):
        script = Path(__file__).resolve().parents[1] / "scripts/deploy.py"
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "checks")) as run, patch("shutil.which") as find_cli:
            with self.assertRaises(subprocess.CalledProcessError):
                runpy.run_path(str(script), run_name="__main__")
            self.assertEqual(run.call_count, 1)
            find_cli.assert_not_called()

    def test_view_filters_persist_through_settings_api(self):
        from src.server import create_app
        from src.auth import create_session_token
        from tests.test_server_auth import wsgi_request
        import json
        with tempfile.TemporaryDirectory() as temp:
            db = os.path.join(temp, "filters_test.db")
            init_db(db)
            app = create_app(db)
            cookie = "job_accel_session=" + create_session_token("admin", "filters-test")
            filters = json.dumps({"saved": {"date": "all"}, "applied": {"date": "today"}})
            saved = wsgi_request(app, "POST", "/api/settings", {"view_filters": filters}, cookie=cookie)
            self.assertEqual(saved["status"], 200)
            restored = wsgi_request(app, "GET", "/api/settings", cookie=cookie)
            self.assertEqual(restored["json"]["view_filters"], filters)

    def test_status_changes_only_affect_selected_requisition(self):
        with tempfile.TemporaryDirectory() as temp:
            db = os.path.join(temp, "workflow_test.db")
            init_db(db)
            insert_jobs(db, [Job("Android Developer", "Example", "Manila", "LinkedIn", 1,
                                 f"https://example.com/{i}", date_posted=date)
                             for i, date in enumerate(("2026-10-10", "2026-10-16"))])
            rows = sorted(get_jobs(db), key=lambda row: row["id"])
            first, second = [row["id"] for row in rows]
            update_job_status(db, first, status="applied", pipeline_stage="final_interview", notes="Keep this")
            for status in ("saved", "ignored", "new", "applied"):
                with self.subTest(status=status):
                    before = next(row for row in get_jobs(db) if row["id"] == first)
                    self.assertTrue(update_job_status(db, second, status=status))
                    after = next(row for row in get_jobs(db) if row["id"] == first)
                    self.assertEqual(before, after)
            update_job_status(db, second, status="new")
            update_job_status(db, first, status="applied")
            self.assertEqual(next(row for row in get_jobs(db) if row["id"] == second)["status"], "new")
            self.assertFalse(update_job_status(db, 99999, status="saved"))
