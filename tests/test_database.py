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
        self.assertIn("by_stage", stats)

    def test_filter_by_date(self):
        job_today = Job(
            title="Dev Today", company="Co", location="Remote", platform="LinkedIn",
            tier=1, job_url="https://job1", date_posted="2026-10-08"
        )
        job_old = Job(
            title="Dev Old", company="Co", location="Remote", platform="LinkedIn",
            tier=1, job_url="https://job2", date_posted="2026-09-01"
        )
        insert_jobs(self.db_path, [job_today, job_old])

        today_jobs = get_jobs(self.db_path, date_filter="today")
        self.assertEqual(len(today_jobs), 1)
        self.assertEqual(today_jobs[0]["title"], "Dev Today")

        all_jobs = get_jobs(self.db_path, date_filter="all")
        self.assertEqual(len(all_jobs), 2)

    def test_tokenized_multi_word_search(self):
        job = Job(
            title="Junior Frontend Developer (React / Next.js)",
            company="Acme Corp",
            location="Remote PH",
            platform="LinkedIn",
            tier=1,
            job_url="https://acme.com/job-token",
            date_posted="2026-10-08"
        )
        insert_jobs(self.db_path, [job])

        # Multi-word non-contiguous search: "junior" and "react" are not adjacent
        results = get_jobs(self.db_path, search="junior react")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["company"], "Acme Corp")

    def test_filter_has_salary(self):
        job1 = Job(title="Dev 1", company="A", location="PH", platform="LinkedIn", tier=1, job_url="https://j1", salary="₱50,000")
        job2 = Job(title="Dev 2", company="B", location="PH", platform="LinkedIn", tier=1, job_url="https://j2", salary="")
        insert_jobs(self.db_path, [job1, job2])
        res = get_jobs(self.db_path, has_salary=True)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["title"], "Dev 1")

    def test_filter_remote_only(self):
        job1 = Job(title="Remote Dev", company="A", location="Remote Worldwide", platform="LinkedIn", tier=1, job_url="https://j3")
        job2 = Job(title="Onsite Dev", company="B", location="Makati Office", platform="LinkedIn", tier=1, job_url="https://j4")
        insert_jobs(self.db_path, [job1, job2])
        res = get_jobs(self.db_path, remote_only=True)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["title"], "Remote Dev")

    def test_pipeline_stages_and_follow_up(self):
        job = Job(title="Backend Dev", company="Cloud Co", location="Remote", platform="Arc", tier=3, job_url="https://arc.dev/b1")
        insert_jobs(self.db_path, [job])
        jobs = get_jobs(self.db_path, status="new")
        job_id = jobs[0]["id"]

        # Mark applied with pipeline stage
        ok = update_job_status(self.db_path, job_id, status="applied", pipeline_stage="hr_screening", notes="Recruiter: John Doe", follow_up_date="2026-10-15")
        self.assertTrue(ok)

        applied = get_jobs(self.db_path, status="applied")
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]["pipeline_stage"], "hr_screening")
        self.assertEqual(applied[0]["notes"], "Recruiter: John Doe")
        self.assertEqual(applied[0]["follow_up_date"], "2026-10-15")

        # Advance stage to tech_exam
        ok2 = update_job_status(self.db_path, job_id, pipeline_stage="tech_exam", notes="Take-home exam sent")
        self.assertTrue(ok2)
        applied2 = get_jobs(self.db_path, status="applied")
        self.assertEqual(applied2[0]["pipeline_stage"], "tech_exam")
        self.assertEqual(applied2[0]["notes"], "Take-home exam sent")

    def test_export_jobs_csv(self):
        from src.database import export_jobs_csv
        job1 = Job(title="React Dev", company="Acme, Inc.", location="Remote", platform="LinkedIn", tier=1, job_url="https://acme.com", salary="$70k")
        job2 = Job(title="Python Dev", company="Beta LLC", location="Remote", platform="Indeed", tier=1, job_url="https://beta.com")
        insert_jobs(self.db_path, [job1, job2])
        jobs = get_jobs(self.db_path, status="new")
        target_id = [j["id"] for j in jobs if j["title"] == "React Dev"][0]
        update_job_status(self.db_path, target_id, status="applied", pipeline_stage="offer", notes="Great offer")

        csv_content = export_jobs_csv(self.db_path, status="applied")
        self.assertIn("Title,Company,Location,Platform", csv_content)
        self.assertIn('"Acme, Inc."', csv_content)
        self.assertIn("React Dev", csv_content)
        self.assertIn("offer", csv_content)
        # job2 wasn't applied, should not appear in applied csv
        self.assertNotIn("Beta LLC", csv_content)

if __name__ == "__main__":
    unittest.main()

