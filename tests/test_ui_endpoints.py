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

        # test style.css
        env_css = {"REQUEST_METHOD": "GET", "PATH_INFO": "/static/style.css", "QUERY_STRING": "", "wsgi.input": None}
        res_css = self.app._handle(env_css)
        body_css = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res_css)
        if hasattr(res_css, "close"):
            res_css.close()
        self.assertIn(".pipeline-hub-header", body_css)
        self.assertIn(".btn-pitch", body_css)
        self.assertIn(".toast-message", body_css)

if __name__ == "__main__":
    unittest.main()

