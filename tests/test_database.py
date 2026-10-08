import unittest
import os
import tempfile
from src.models import Job, hash_job, clean_url
from src.database import init_db, insert_jobs, get_jobs, update_job_status, get_stats

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_jobs.db")
        init_db(self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_clean_url_and_hashing(self):
        url1 = "https://ph.indeed.com/viewjob?jk=12345&utm_source=feed&utm_medium=email"
        url2 = "https://ph.indeed.com/viewjob?jk=12345"
        self.assertEqual(clean_url(url1), "https://ph.indeed.com/viewjob?jk=12345")
        h1 = hash_job("Indeed", "Acme Corp", "Junior Developer", url1)
        h2 = hash_job("Indeed", "acme corp ", "JUNIOR DEVELOPER", url2)
        self.assertEqual(h1, h2)

    def test_insert_preserves_status_on_conflict(self):
        job = Job(
            title="Junior Python Dev",
            company="Tech Corp",
            location="Remote PH",
            platform="LinkedIn",
            tier=1,
            job_url="https://linkedin.com/jobs/view/999",
            salary="PHP 40k-60k",
            role_category="Web/Software Dev",
            experience_level="Junior / Entry",
            date_posted="2026-10-08",
            status="new"
        )
        added, skipped = insert_jobs(self.db_path, [job])
        self.assertEqual(added, 1)
        self.assertEqual(skipped, 0)

        # User marks job as applied
        jobs = get_jobs(self.db_path, status="new")
        self.assertEqual(len(jobs), 1)
        job_id = jobs[0]["id"]
        update_job_status(self.db_path, job_id, "applied", notes="Applied via resume v2")

        # Re-fetch during next sync cycle
        added2, skipped2 = insert_jobs(self.db_path, [job])
        self.assertEqual(added2, 0)
        self.assertEqual(skipped2, 1)

        # Status must remain 'applied'
        applied_jobs = get_jobs(self.db_path, status="applied")
        self.assertEqual(len(applied_jobs), 1)
        self.assertEqual(applied_jobs[0]["status"], "applied")
        self.assertEqual(applied_jobs[0]["notes"], "Applied via resume v2")

    def test_get_stats(self):
        job1 = Job(title="Job 1", company="A", location="PH", platform="Kalibrr", tier=1, job_url="https://kalibrr.com/1", experience_level="Junior / Entry")
        job2 = Job(title="Job 2", company="B", location="Remote", platform="Remote OK", tier=3, job_url="https://remoteok.com/2", experience_level="Mid-Level")
        insert_jobs(self.db_path, [job1, job2])
        stats = get_stats(self.db_path)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["new"], 2)
        self.assertEqual(stats["applied"], 0)
        self.assertEqual(stats["by_level"].get("Junior / Entry"), 1)
        self.assertEqual(stats["by_level"].get("Mid-Level"), 1)

if __name__ == "__main__":
    unittest.main()
