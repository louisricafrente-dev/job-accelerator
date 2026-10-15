import unittest
import tempfile
import os
import json
from src.database import init_db, get_jobs, get_stats
from src.seed import seed_sample_data
from src.server import create_app
from src.auth import create_session_token

class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "e2e_test.db")
        init_db(self.db_path)
        self.admin_token = create_session_token("admin", "admin", expiry_hours=24)
        self.app = create_app(self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def _api_get(self, path, query_string=""):
        env = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": path,
            "QUERY_STRING": query_string,
            "wsgi.input": None,
            "HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"
        }
        res = self.app._handle(env)
        body = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res)
        return json.loads(body)

    def test_full_pipeline_seed_and_filter(self):
        # 1. Seed data
        count = seed_sample_data(self.db_path)
        self.assertGreaterEqual(count, 12, "Should seed jobs across all 12 platforms")

        # 2. Query stats
        stats = self._api_get("/api/stats")
        self.assertEqual(stats["total"], count)
        self.assertGreater(stats["by_level"].get("Junior / Entry", 0), 0)

        # 3. Query with Junior filter
        res_junior = self._api_get("/api/jobs", "experience_level=Junior / Entry")
        self.assertGreater(res_junior["count"], 0)
        for job in res_junior["jobs"]:
            self.assertEqual(job["experience_level"], "Junior / Entry")

        # 4. Check 12 platforms represented
        all_jobs = get_jobs(self.db_path, limit=200)
        platforms = {j["platform"] for j in all_jobs}
        self.assertIn("LinkedIn", platforms)
        self.assertIn("Kalibrr", platforms)
        self.assertIn("Remote OK", platforms)
        self.assertIn("Upwork", platforms)

    def test_e2e_application_tracking_and_csv_export(self):
        seed_sample_data(self.db_path)
        jobs = get_jobs(self.db_path, status="new")
        target_job = jobs[0]

        # Apply and set stage
        import io
        post_env = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": f"/api/jobs/{target_job['id']}/status",
            "QUERY_STRING": "",
            "wsgi.input": io.BytesIO(json.dumps({
                "status": "applied",
                "stage": "hr_screening",
                "notes": "Talked to Recruiter Maria, next round Thursday"
            }).encode("utf-8")),
            "CONTENT_LENGTH": "150",
            "CONTENT_TYPE": "application/json",
            "HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"
        }
        res_post = self.app._handle(post_env)
        body_post = json.loads("".join(item if isinstance(item, str) else item.decode("utf-8") for item in res_post))
        self.assertTrue(body_post["success"])

        # Check stats
        stats = self._api_get("/api/stats")
        self.assertEqual(stats["applied"], 1)
        self.assertEqual(stats["by_stage"].get("hr_screening"), 1)

        # Download CSV export
        csv_env = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/jobs/export/csv",
            "QUERY_STRING": "status=applied",
            "wsgi.input": None,
            "HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"
        }
        res_csv = self.app._handle(csv_env)
        csv_text = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res_csv)
        self.assertIn("Title,Company,Location,Platform", csv_text)
        self.assertIn("hr_screening", csv_text)
        self.assertIn("Talked to Recruiter Maria", csv_text)

if __name__ == "__main__":
    unittest.main()

