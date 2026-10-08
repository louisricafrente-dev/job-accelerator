import unittest
import tempfile
import os
import json
import io
from src.database import init_db, insert_jobs, get_jobs
from src.models import Job
from src.server import create_app

class TestServer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "server_test.db")
        init_db(self.db_path)
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
            "CONTENT_TYPE": "application/json" if body else ""
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

if __name__ == "__main__":
    unittest.main()
