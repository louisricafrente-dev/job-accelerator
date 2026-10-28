import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.database import init_db, insert_jobs, get_jobs, get_stats, update_job_status
from src.models import Job


class UsageQueryTests(unittest.TestCase):
    def test_stats_match_tracking_counts_with_one_query(self):
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "usage_test.db")
            init_db(db)
            insert_jobs(db, [
                Job("Junior Python Developer", "One", "Remote", "Example", 1, "https://example.com/1", experience_level="Junior / Entry"),
                Job("Junior Kotlin Developer", "Two", "Remote", "Example", 1, "https://example.com/2", experience_level="Junior / Entry"),
                Job("Virtual Assistant", "Three", "Remote", "Example", 1, "https://example.com/3", role_category="Virtual Assistant"),
            ])
            rows = get_jobs(db)
            python = next(row for row in rows if "Python" in row["title"])
            kotlin = next(row for row in rows if "Kotlin" in row["title"])
            update_job_status(db, python["id"], "applied", pipeline_stage="interview")
            update_job_status(db, kotlin["id"], "saved", notes="Keep")
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            statements = []
            conn.set_trace_callback(statements.append)
            with patch("src.database.get_db_connection", return_value=conn):
                stats = get_stats(db)
            self.assertEqual(len(statements), 1)
            self.assertEqual(stats["total"], 3)
            self.assertEqual(stats["new"], 1)
            self.assertEqual(stats["saved"], 1)
            self.assertEqual(stats["applied"], 1)
            self.assertEqual(stats["by_stage"], {"interview": 1})
            self.assertEqual(stats["va"], 1)
