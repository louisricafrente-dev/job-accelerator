import unittest
import tempfile
import os
from src.database import init_db
from src.server import create_app

class TestUIEndpoints(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "ui_test.db")
        init_db(self.db_path)
        self.app = create_app(self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_index_html_served(self):
        env = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/",
            "QUERY_STRING": "",
            "wsgi.input": None
        }
        res = self.app._handle(env)
        body = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res)
        if hasattr(res, "close"):
            res.close()
        self.assertIn("Job Application Accelerator", body)
        self.assertIn("sync-btn", body)
        self.assertIn("user-stack-input", body)
        self.assertIn("skill-chips-container", body)
        self.assertIn("filter-by-skills-btn", body)
        self.assertIn("skills-only-checkbox", body)
        self.assertIn("pipeline-hub-header", body)
        self.assertIn("btn-export-csv", body)
        self.assertIn("toast-container", body)

    def test_static_assets_served(self):
        # test app.js
        env_js = {"REQUEST_METHOD": "GET", "PATH_INFO": "/static/app.js", "QUERY_STRING": "", "wsgi.input": None}
        res_js = self.app._handle(env_js)
        body_js = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res_js)
        if hasattr(res_js, "close"):
            res_js.close()
        self.assertIn("generateTailoredPitch", body_js)
        self.assertIn("copyTailoredPitch", body_js)
        self.assertIn("PIPELINE_STAGES", body_js)
        self.assertIn("PRESET_SKILLS", body_js)
        self.assertIn("renderSkillChips", body_js)
        self.assertIn("toggleSkill", body_js)

        # test style.css
        env_css = {"REQUEST_METHOD": "GET", "PATH_INFO": "/static/style.css", "QUERY_STRING": "", "wsgi.input": None}
        res_css = self.app._handle(env_css)
        body_css = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res_css)
        if hasattr(res_css, "close"):
            res_css.close()
        self.assertIn(".pipeline-hub-header", body_css)
        self.assertIn(".btn-pitch", body_css)
        self.assertIn(".toast-message", body_css)
        self.assertIn(".skill-chip", body_css)
        self.assertIn(".btn-filter-skills", body_css)

    def test_api_jobs_returns_parsed_sources(self):
        import json
        from src.models import Job
        from src.database import insert_jobs
        from src.auth import create_session_token

        job1 = Job(title="Fullstack Engineer", company="OmniCorp", location="Remote", platform="LinkedIn", tier=1, job_url="https://linkedin.com/1")
        job2 = Job(title="Fullstack Engineer", company="OmniCorp", location="Remote", platform="JobStreet", tier=1, job_url="https://jobstreet.com/2")
        insert_jobs(self.db_path, [job1, job2])

        token = create_session_token("admin", "admin", expiry_hours=24)
        env = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/jobs",
            "QUERY_STRING": "status=new",
            "wsgi.input": None,
            "HTTP_AUTHORIZATION": f"Bearer {token}"
        }
        res = self.app._handle(env)
        body = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res)
        if hasattr(res, "close"):
            res.close()
        data = json.loads(body)
        self.assertEqual(len(data["jobs"]), 1)
        job = data["jobs"][0]
        self.assertIsInstance(job["sources"], list)
        self.assertEqual(len(job["sources"]), 2)
        platforms = {s["platform"] for s in job["sources"]}
        self.assertEqual(platforms, {"LinkedIn", "JobStreet"})

if __name__ == "__main__":
    unittest.main()

