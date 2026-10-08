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
        # Should return index.html content
        body = "".join(item if isinstance(item, str) else item.decode("utf-8") for item in res)
        self.assertIn("Job Application Accelerator", body)
        self.assertIn("sync-btn", body)

if __name__ == "__main__":
    unittest.main()
