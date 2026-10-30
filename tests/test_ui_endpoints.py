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
        self.assertIn("btn-sync-restart", body)
        self.assertIn("btn-sync-play", body)
        self.assertIn("btn-sync-pause", body)
        self.assertIn("btn-sync-stop", body)
        self.assertIn("sync-progress-banner", body)
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

    def test_api_sync_media_actions(self):
        import json, io
        from src.auth import create_session_token

        token = create_session_token("admin", "admin", expiry_hours=24)
        for act in ("pause", "stop"):
            body_bytes = json.dumps({"action": act}).encode("utf-8")
            env = {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/sync",
                "QUERY_STRING": "",
                "wsgi.input": io.BytesIO(body_bytes),
                "CONTENT_LENGTH": str(len(body_bytes)),
                "CONTENT_TYPE": "application/json",
                "HTTP_AUTHORIZATION": f"Bearer {token}"
            }
            res = self.app._handle(env)
            body = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res)
            if hasattr(res, "close"):
                res.close()
            data = json.loads(body)
            self.assertEqual(data.get("status"), f"{act}d" if act == "pause" else "stopped")

    def test_gmail_messages_endpoint(self):
        import json
        from src.auth import create_session_token

        token = create_session_token("admin", "admin", expiry_hours=24)
        env = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/gmail/messages",
            "QUERY_STRING": "",
            "wsgi.input": None,
            "HTTP_AUTHORIZATION": f"Bearer {token}"
        }
        res = self.app._handle(env)
        body = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res)
        if hasattr(res, "close"):
            res.close()
        data = json.loads(body)
        self.assertIn("account", data)
        self.assertIn("messages", data)
        self.assertIn("stats", data)

    def test_pipeline_stage_filter_endpoint(self):
        import json
        from src.models import Job
        from src.database import insert_jobs, update_job_status
        from src.auth import create_session_token

        job1 = Job(title="Backend Dev", company="Alpha Corp", location="Remote", platform="LinkedIn", tier=1, job_url="https://linkedin.com/a1")
        insert_jobs(self.db_path, [job1])
        update_job_status(self.db_path, 1, status="applied", pipeline_stage="offer")

        token = create_session_token("admin", "admin", expiry_hours=24)
        env = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/jobs",
            "QUERY_STRING": "status=applied&pipeline_stage=offer",
            "wsgi.input": None,
            "HTTP_AUTHORIZATION": f"Bearer {token}"
        }
        res = self.app._handle(env)
        body = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res)
        if hasattr(res, "close"):
            res.close()
        data = json.loads(body)
        self.assertEqual(len(data["jobs"]), 1)
        self.assertEqual(data["jobs"][0]["pipeline_stage"], "offer")

    def test_portfolio_views_in_app_modal_and_endpoint(self):
        import json
        env_html = {"REQUEST_METHOD": "GET", "PATH_INFO": "/", "QUERY_STRING": "", "wsgi.input": None}
        res_html = self.app._handle(env_html)
        body_html = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res_html)
        if hasattr(res_html, "close"):
            res_html.close()
        self.assertIn('id="btn-portfolio-views"', body_html)
        self.assertIn('onclick="togglePortfolioViewsModal()"', body_html)
        self.assertIn('id="portfolio-views-modal"', body_html)
        self.assertNotIn('href="https://hits.sh/louisricafrente-dev.vercel.app/"', body_html)

        env_api = {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/portfolio/views", "QUERY_STRING": "", "wsgi.input": None}
        res_api = self.app._handle(env_api)
        body_api = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res_api)
        if hasattr(res_api, "close"):
            res_api.close()
        data = json.loads(body_api)
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("domain"), "louisricafrente-dev.vercel.app")
        self.assertGreater(int(data.get("total", 0)), 0)
        self.assertIsInstance(data.get("days"), list)

if __name__ == "__main__":
    unittest.main()

