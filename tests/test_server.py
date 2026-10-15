import unittest
import tempfile
import os
import json
import io
from src.database import init_db, insert_jobs, get_jobs
from src.models import Job
from src.server import create_app
from src.auth import create_session_token

class TestServer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "server_test.db")
        init_db(self.db_path)
        self.admin_token = create_session_token("admin", "admin", expiry_hours=24)
        insert_jobs(self.db_path, [
            Job(
                title="Junior AI Engineer",
                company="OpenLab",
                location="Remote",
                platform="Remote OK",
                tier=3,
                job_url="https://remoteok.com/job/ai",
                experience_level="Junior / Entry",
                role_category="Data/AI/ML",
                status="new"
            ),
            Job(
                title="Senior Fullstack Dev",
                company="BigCorp",
                location="Manila",
                platform="LinkedIn",
                tier=1,
                job_url="https://linkedin.com/jobs/view/2",
                experience_level="Senior / Lead",
                role_category="Web/Software Dev",
                status="new"
            )
        ])
        self.app = create_app(self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def _request(self, method, path, query_string="", body=None):
        env = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query_string,
            "wsgi.input": io.BytesIO(json.dumps(body).encode("utf-8")) if body else io.BytesIO(b""),
            "CONTENT_LENGTH": str(len(json.dumps(body))) if body else "0",
            "CONTENT_TYPE": "application/json" if body else "",
            "HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"
        }
        res = self.app._handle(env)
        body_str = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res)
        return json.loads(body_str)

    def test_get_jobs_filtered_by_level(self):
        data = self._request("GET", "/api/jobs", "experience_level=Junior / Entry")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["jobs"][0]["company"], "OpenLab")

    def test_update_job_status(self):
        jobs = get_jobs(self.db_path)
        job_id = jobs[0]["id"]
        res = self._request("POST", f"/api/jobs/{job_id}/status", body={"status": "applied", "notes": "Applied via portal"})
        self.assertTrue(res["success"])
        updated = get_jobs(self.db_path, status="applied")
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["notes"], "Applied via portal")

    def test_get_stats(self):
        stats = self._request("GET", "/api/stats")
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["new"], 2)
        self.assertEqual(stats["applied"], 0)

    def test_get_jobs_filtered_by_date(self):
        data = self._request("GET", "/api/jobs", "date_filter=today")
        self.assertIn("jobs", data)

    def test_get_jobs_filtered_by_salary_and_remote(self):
        data_sal = self._request("GET", "/api/jobs", "has_salary=1")
        self.assertIn("jobs", data_sal)
        data_rem = self._request("GET", "/api/jobs", "remote_only=1")
        self.assertIn("jobs", data_rem)
        self.assertEqual(data_rem["count"], 1)
        self.assertEqual(data_rem["jobs"][0]["location"], "Remote")

    def test_sync_with_custom_keywords(self):
        res = self._request("POST", "/api/sync", body={"keywords": ["python", "junior"]})
        self.assertIn("added", res)
        self.assertIn("platforms", res)

    def test_sync_background_and_status_endpoint(self):
        # Trigger background sync
        res = self._request("POST", "/api/sync", body={"background": True})
        self.assertEqual(res["status"], "started")
        self.assertTrue(res["is_syncing"])

        # Query status endpoint
        status_res = self._request("GET", "/api/sync/status")
        self.assertIn("is_syncing", status_res)
        self.assertIn("last_result", status_res)

    def test_update_job_stage_and_follow_up(self):
        jobs = get_jobs(self.db_path)
        job_id = jobs[0]["id"]
        res = self._request("POST", f"/api/jobs/{job_id}/status", body={
            "status": "applied",
            "stage": "tech_exam",
            "notes": "HackerRank due Friday",
            "follow_up_date": "2026-10-12"
        })
        self.assertTrue(res["success"])
        applied = get_jobs(self.db_path, status="applied")
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]["pipeline_stage"], "tech_exam")
        self.assertEqual(applied[0]["notes"], "HackerRank due Friday")
        self.assertEqual(applied[0]["follow_up_date"], "2026-10-12")

    def test_export_csv_endpoint(self):
        jobs = get_jobs(self.db_path)
        self._request("POST", f"/api/jobs/{jobs[0]['id']}/status", body={"status": "applied", "stage": "final_interview"})

        env = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/jobs/export/csv",
            "QUERY_STRING": "status=applied",
            "wsgi.input": io.BytesIO(b""),
            "CONTENT_LENGTH": "0",
            "CONTENT_TYPE": "",
            "HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"
        }
        res = self.app._handle(env)
        body_str = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res)
        self.assertIn("Title,Company,Location,Platform", body_str)
        self.assertIn("final_interview", body_str)

    def test_settings_stack_endpoints(self):
        # 1. Default stack retrieval
        res = self._request("GET", "/api/settings/stack")
        self.assertIn("stack", res)
        self.assertIn("Kotlin", res["stack"])

        # 2. Update stack
        post_res = self._request("POST", "/api/settings/stack", body={
            "stack": "React, TypeScript, Next.js, MySQL"
        })
        self.assertTrue(post_res["success"])
        self.assertEqual(post_res["stack"], "React, TypeScript, Next.js, MySQL")

        # 3. Retrieve updated stack
        get_res2 = self._request("GET", "/api/settings/stack")
        self.assertEqual(get_res2["stack"], "React, TypeScript, Next.js, MySQL")

    def test_general_settings_api(self):
        # 1. Get all settings (defaults)
        res = self._request("GET", "/api/settings")
        self.assertIn("target_stack", res)
        self.assertIn("Kotlin", res["target_stack"])

        # 2. Save multiple toggle and filter settings
        post_res = self._request("POST", "/api/settings", body={
            "remote_only": "1",
            "hide_senior": "1",
            "date_filter": "24h",
            "role": "Mobile",
            "experience_levels": "Junior / Entry,Mid-Level"
        })
        self.assertTrue(post_res["success"])
        self.assertEqual(post_res["settings"]["remote_only"], "1")
        self.assertEqual(post_res["settings"]["hide_senior"], "1")
        self.assertEqual(post_res["settings"]["date_filter"], "24h")
        self.assertEqual(post_res["settings"]["role"], "Mobile")
        self.assertEqual(post_res["settings"]["experience_levels"], "Junior / Entry,Mid-Level")

        # 3. Verify retrieval persists
        get_res2 = self._request("GET", "/api/settings")
        self.assertEqual(get_res2["remote_only"], "1")
        self.assertEqual(get_res2["date_filter"], "24h")
        self.assertEqual(get_res2["role"], "Mobile")

if __name__ == "__main__":
    unittest.main()

