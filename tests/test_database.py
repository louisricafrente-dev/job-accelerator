import unittest
import os
import tempfile
from src.models import Job, hash_job, clean_url
from src.database import init_db, insert_jobs, get_jobs, update_job_status, get_stats

class TestDatabase(unittest.TestCase):
    def test_description_classification_and_legacy_backfill_preserve_tracking(self):
        job = Job(title="Developer II", company="Example", location="Philippines", platform="Indeed", tier=1,
                  job_url="https://example.com/jobs/entry", experience_level="Mid-Level",
                  description="Fresh graduates are welcome. Python: 3 years (Required)")
        insert_jobs(self.db_path, [job])
        row = get_jobs(self.db_path, status="new")[0]
        self.assertEqual(row["experience_level"], "Junior / Entry")
        update_job_status(self.db_path, row["id"], "saved", notes="Keep my note")
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE jobs SET experience_level = 'Mid-Level'")
        init_db(self.db_path)
        row = get_jobs(self.db_path, status="saved")[0]
        self.assertEqual(row["experience_level"], "Junior / Entry")
        self.assertEqual(row["notes"], "Keep my note")
        self.assertEqual(get_jobs(self.db_path, status="saved", experience_level="Mid-Level"), [])
        self.assertEqual(len(get_jobs(self.db_path, status="saved", experience_level="Junior / Entry")), 1)

    def test_application_handling_lifecycle(self):
        job = Job(title="Junior Developer", company="Example", location="Philippines", platform="Indeed", tier=1, job_url="https://example.com/handling")
        insert_jobs(self.db_path, [job])
        row = get_jobs(self.db_path, status="new")[0]
        jid = row["id"]
        update_job_status(self.db_path, jid, status="saved")
        self.assertEqual(get_jobs(self.db_path, status="saved")[0]["application_handling"], "")
        update_job_status(self.db_path, jid, application_handling="needs_human", notes="Employer login required")
        init_db(self.db_path)
        row = get_jobs(self.db_path, status="saved")[0]
        self.assertEqual(row["application_handling"], "needs_human")
        self.assertFalse(row["applied_at"])
        update_job_status(self.db_path, jid, application_handling="in_progress", notes="AI run active")
        row = get_jobs(self.db_path, status="saved")[0]
        self.assertEqual(row["application_handling"], "in_progress")
        self.assertEqual(row["notes"], "AI run active")
        self.assertFalse(row["applied_at"])
        update_job_status(self.db_path, jid, application_handling="applied_ai")
        row = get_jobs(self.db_path, status="applied")[0]
        self.assertEqual(row["application_handling"], "applied_ai")
        self.assertTrue(row["applied_at"])
        insert_jobs(self.db_path, [job])
        self.assertEqual(get_jobs(self.db_path, status="applied")[0]["application_handling"], "applied_ai")
        update_job_status(self.db_path, jid, status="saved")
        update_job_status(self.db_path, jid, status="applied")
        self.assertEqual(get_jobs(self.db_path, status="applied")[0]["application_handling"], "applied_human")
        with self.assertRaises(ValueError):
            update_job_status(self.db_path, jid, application_handling="banana")
        with self.assertRaises(ValueError):
            update_job_status(self.db_path, jid, status="saved", application_handling="applied_ai")
        update_job_status(self.db_path, jid, status="in_progress")
        self.assertEqual(get_jobs(self.db_path, status="in_progress")[0]["status"], "in_progress")

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
        import datetime
        today_str = datetime.date.today().isoformat()
        job_today = Job(
            title="Dev Today", company="Co", location="Remote", platform="LinkedIn",
            tier=1, job_url="https://job1", date_posted=today_str
        )
        job_old = Job(
            title="Dev Old", company="Co", location="Remote", platform="LinkedIn",
            tier=1, job_url="https://job2", date_posted="2026-01-01"
        )
        insert_jobs(self.db_path, [job_today, job_old])

        today_jobs = get_jobs(self.db_path, date_filter="today")
        self.assertEqual(len(today_jobs), 1)
        self.assertEqual(today_jobs[0]["title"], "Dev Today")

        all_jobs = get_jobs(self.db_path, date_filter="all")
        self.assertEqual(len(all_jobs), 2)

    def test_normalize_date_and_rfc_exclusion_in_7days_filter(self):
        import datetime
        today = datetime.date.today()
        recent_date = (today - datetime.timedelta(days=2)).isoformat()
        ancient_date_rfc = "Mon, 28 Sep 2026"  # Over 13 days ago

        job_recent = Job(
            title="Recent Dev", company="Alpha", location="Remote", platform="LinkedIn",
            tier=1, job_url="https://job-recent", date_posted=recent_date
        )
        job_ancient_rfc = Job(
            title="Old RFC Dev", company="Beta", location="Remote", platform="Foundit",
            tier=2, job_url="https://job-ancient", date_posted=ancient_date_rfc
        )
        insert_jobs(self.db_path, [job_recent, job_ancient_rfc])

        # Past 7 days filter must include recent and EXCLUDE ancient RFC date
        seven_day_jobs = get_jobs(self.db_path, date_filter="7days")
        self.assertEqual(len(seven_day_jobs), 1)
        self.assertEqual(seven_day_jobs[0]["title"], "Recent Dev")

    def test_cross_platform_duplicate_aggregation_sources(self):
        job1 = Job(
            title="Senior Go Developer",
            company="Accenture PH",
            location="BGC Taguig",
            platform="Indeed",
            tier=1,
            job_url="https://indeed.com/view/accenture-go",
            salary="₱90k-₱120k",
            date_posted="2026-10-08"
        )
        job2 = Job(
            title="Senior Go Developer",
            company="Accenture PH",
            location="BGC Taguig",
            platform="Glassdoor",
            tier=1,
            job_url="https://glassdoor.com/view/accenture-go",
            salary="₱95k-₱130k",
            date_posted="2026-10-09"
        )

        added1, skipped1 = insert_jobs(self.db_path, [job1])
        self.assertEqual(added1, 1)
        self.assertEqual(skipped1, 0)

        # Inserting duplicate from another platform merges sources
        added2, skipped2 = insert_jobs(self.db_path, [job2])
        self.assertEqual(added2, 0)
        self.assertEqual(skipped2, 1)

        # Database should still contain only 1 listing, with both sources preserved
        jobs = get_jobs(self.db_path, search="Accenture")
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(len(job["sources"]), 2)
        platforms = {s["platform"] for s in job["sources"]}
        self.assertEqual(platforms, {"Indeed", "Glassdoor"})
        urls = {s["url"] for s in job["sources"]}
        self.assertEqual(urls, {"https://indeed.com/view/accenture-go", "https://glassdoor.com/view/accenture-go"})

    def test_saved_jobs_with_7days_filter(self):
        import datetime
        today = datetime.date.today()
        recent_date = (today - datetime.timedelta(days=3)).isoformat()
        old_date = (today - datetime.timedelta(days=20)).isoformat()

        job_recent = Job(title="Saved Recent", company="Co1", location="Remote", platform="LinkedIn", tier=1, job_url="https://s1", date_posted=recent_date)
        job_old = Job(title="Saved Old", company="Co2", location="Remote", platform="JobStreet", tier=1, job_url="https://s2", date_posted=old_date)

        insert_jobs(self.db_path, [job_recent, job_old])
        all_new = get_jobs(self.db_path, status="new")
        for j in all_new:
            update_job_status(self.db_path, j["id"], status="saved")

        # In Saved tab, with 'all' date filter, shows 2 jobs
        all_saved = get_jobs(self.db_path, status="saved", date_filter="all")
        self.assertEqual(len(all_saved), 2)

        # In Saved tab, with '7days' date filter, excludes the 20-day-old job
        filtered_saved = get_jobs(self.db_path, status="saved", date_filter="7days")
        self.assertEqual(len(filtered_saved), 1)
        self.assertEqual(filtered_saved[0]["title"], "Saved Recent")

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
    def test_granular_software_development_role_filters(self):
        jobs = [
            Job(title="Junior Frontend React Dev", company="A", location="Remote", platform="LinkedIn", tier=1, job_url="https://a.com"),
            Job(title="Senior Backend Python Dev", company="B", location="Remote", platform="Indeed", tier=1, job_url="https://b.com"),
            Job(title="Full Stack Software Engineer", company="C", location="Remote", platform="Arc", tier=3, job_url="https://c.com"),
            Job(title="Mobile Flutter Developer", company="D", location="Remote", platform="Kalibrr", tier=1, job_url="https://d.com"),
            Job(title="Cloud / DevOps Engineer", company="E", location="Remote", platform="Glassdoor", tier=4, job_url="https://e.com"),
            Job(title="QA Automation Engineer", company="F", location="Remote", platform="Upwork", tier=4, job_url="https://f.com"),
            Job(title="Data Scientist", company="G", location="Remote", platform="Remote OK", tier=3, job_url="https://g.com", role_category="Data/AI/ML"),
        ]
        insert_jobs(self.db_path, jobs)

        self.assertEqual(len(get_jobs(self.db_path, role_category="Frontend")), 1)
        self.assertEqual(len(get_jobs(self.db_path, role_category="Backend")), 1)
        self.assertEqual(len(get_jobs(self.db_path, role_category="Full Stack")), 1)
        self.assertEqual(len(get_jobs(self.db_path, role_category="Mobile")), 1)
        self.assertEqual(len(get_jobs(self.db_path, role_category="DevOps / Cloud")), 1)
        self.assertEqual(len(get_jobs(self.db_path, role_category="QA / Testing")), 1)
        self.assertEqual(len(get_jobs(self.db_path, role_category="Data/AI/ML")), 1)
        self.assertEqual(len(get_jobs(self.db_path, role_category="Web/Software Dev")), 6)

    def test_role_filters_do_not_treat_both_as_every_specialty(self):
        titles = ["React Native Developer", "Frontend JavaScript Developer", "Data Scientist",
                  "Data Engineer", "Business Analyst", "AI Engineer", "QA Automation Engineer - Java",
                  "IT Support Analyst", "Security Analyst", "BIOS Engineer", "Claims Analyst",
                  "Virtual Assistant", "Civil Engineer", "CNC Programmer", "China Mobile Bulk SMS Routing provider"]
        insert_jobs(self.db_path, [Job(title=t, company="Example", location="Philippines", platform="Indeed",
                    tier=1, job_url=f"https://example.com/{i}", role_category="Both") for i, t in enumerate(titles)])
        def titles_for(role):
            return {j["title"] for j in get_jobs(self.db_path, role_category=role)}
        self.assertEqual(titles_for("Mobile"), {"React Native Developer"})
        self.assertEqual(titles_for("Frontend"), {"Frontend JavaScript Developer"})
        self.assertEqual(titles_for("Backend"), set())
        self.assertEqual(titles_for("Data Science"), {"Data Scientist"})
        self.assertEqual(titles_for("AI / ML"), {"AI Engineer"})
        self.assertEqual(titles_for("IT Support"), {"IT Support Analyst"})
        self.assertEqual(titles_for("Cybersecurity"), {"Security Analyst"})
        self.assertEqual(titles_for("Virtual Assistant"), {"Virtual Assistant"})
        self.assertNotIn("Virtual Assistant", titles_for("Tech & IT"))
        self.assertNotIn("Civil Engineer", titles_for("Tech & IT"))
        self.assertNotIn("CNC Programmer", titles_for("Tech & IT"))
        self.assertNotIn("BIOS Engineer", titles_for("Mobile"))
        data = titles_for("Data & Analytics")
        self.assertIn("Business Analyst", data)
        self.assertNotIn("IT Support Analyst", data)
        self.assertNotIn("Security Analyst", data)
        rows = get_jobs(self.db_path, role_category="Data & Analytics", limit=2, with_total=True)
        self.assertEqual(rows[0]["matching_total"], len(data))

    def test_archived_job_revived_on_newer_date_repost(self):
        # 1. Candidate archives an older posting
        job_old = Job(
            title="Senior React Engineer",
            company="Acme Cloud",
            location="Remote PH",
            platform="Indeed",
            tier=1,
            job_url="https://indeed.com/acme-1",
            date_posted="2026-10-02"
        )
        insert_jobs(self.db_path, [job_old])
        jobs = get_jobs(self.db_path, status="new")
        self.assertEqual(len(jobs), 1)
        job_id = jobs[0]["id"]

        # User archives (ignores) the job
        update_job_status(self.db_path, job_id, status="ignored")
        self.assertEqual(len(get_jobs(self.db_path, status="new")), 0)
        self.assertEqual(len(get_jobs(self.db_path, status="ignored")), 1)

        # 2. Company re-posts the job with a brand new, fresh date
        job_fresh = Job(
            title="Senior React Engineer",
            company="Acme Cloud",
            location="Remote PH",
            platform="Indeed",
            tier=1,
            job_url="https://indeed.com/acme-1",
            date_posted="2026-10-10"
        )
        added, skipped = insert_jobs(self.db_path, [job_fresh])
        self.assertEqual(added, 1)
        self.assertEqual(skipped, 0)

        # Job is revived to 'new' and appears in Inbox with updated date
        revived = get_jobs(self.db_path, status="new")
        self.assertEqual(len(revived), 1)
        self.assertEqual(revived[0]["status"], "new")
        self.assertEqual(revived[0]["date_posted"], "2026-10-10")

    def test_archived_job_revived_on_new_platform_source(self):
        # 1. Candidate archives a posting from LinkedIn
        job_li = Job(
            title="Node.js Architect",
            company="FinTech Global",
            location="Manila",
            platform="LinkedIn",
            tier=1,
            job_url="https://linkedin.com/fintech-1",
            date_posted="2026-10-08"
        )
        insert_jobs(self.db_path, [job_li])
        j_id = get_jobs(self.db_path, status="new")[0]["id"]
        update_job_status(self.db_path, j_id, status="ignored")

        # 2. Same job is discovered on JobStreet with a new link
        job_js = Job(
            title="Node.js Architect",
            company="FinTech Global",
            location="Manila",
            platform="JobStreet",
            tier=1,
            job_url="https://jobstreet.com.ph/fintech-2",
            date_posted="2026-10-08"
        )
        added, skipped = insert_jobs(self.db_path, [job_js])
        self.assertEqual(added, 1)
        self.assertEqual(skipped, 0)

        # Revived to Inbox with both platforms aggregated
        revived = get_jobs(self.db_path, status="new")
        self.assertEqual(len(revived), 1)
        self.assertEqual(revived[0]["status"], "new")
        self.assertEqual(len(revived[0]["sources"]), 2)

    def test_archived_job_remains_ignored_if_identical_unchanged(self):
        job = Job(
            title="Junior QA Specialist",
            company="TestLab Inc",
            location="Remote",
            platform="Kalibrr",
            tier=1,
            job_url="https://kalibrr.com/qa-1",
            date_posted="2026-10-07"
        )
        insert_jobs(self.db_path, [job])
        j_id = get_jobs(self.db_path, status="new")[0]["id"]
        update_job_status(self.db_path, j_id, status="ignored")

        # Re-fetching identical listing with same date & platform does not un-archive
        added, skipped = insert_jobs(self.db_path, [job])
        self.assertEqual(added, 0)
        self.assertEqual(skipped, 1)

        self.assertEqual(len(get_jobs(self.db_path, status="new")), 0)
        self.assertEqual(len(get_jobs(self.db_path, status="ignored")), 1)

    def test_user_settings_persistence(self):
        from src.database import get_user_setting, set_user_setting
        # Default fallback
        val = get_user_setting(self.db_path, "target_stack", "Default Stack")
        self.assertEqual(val, "Default Stack")

        # Set value
        res = set_user_setting(self.db_path, "target_stack", "Kotlin, Jetpack Compose, React")
        self.assertTrue(res)

        # Retrieve value
        val2 = get_user_setting(self.db_path, "target_stack")
        self.assertEqual(val2, "Kotlin, Jetpack Compose, React")

        # Overwrite value
        set_user_setting(self.db_path, "target_stack", "Next.js, TypeScript")
        val3 = get_user_setting(self.db_path, "target_stack")
        self.assertEqual(val3, "Next.js, TypeScript")

        # Test get_all_user_settings
        from src.database import get_all_user_settings
        set_user_setting(self.db_path, "remote_only", "1")
        all_settings = get_all_user_settings(self.db_path)
        self.assertEqual(all_settings["target_stack"], "Next.js, TypeScript")
        self.assertEqual(all_settings["remote_only"], "1")

    def test_same_platform_same_timeline_keeps_requisitions(self):
        """Different same-board URLs retain separate tracking even on the same date."""
        job1 = Job(
            title="Junior Full Stack Developer",
            company="Microgenesis Business Systems",
            location="Manila, Philippines",
            platform="JobStreet",
            tier=1,
            job_url="https://www.jobstreet.com.ph/job/95102667",
            date_posted="2026-10-14",
            status="saved"
        )
        added, skipped = insert_jobs(self.db_path, [job1])
        self.assertEqual(added, 1)

        # Mark as saved using the job's integer id
        jobs_initial = get_jobs(self.db_path, search="Microgenesis")
        self.assertEqual(len(jobs_initial), 1)
        update_job_status(self.db_path, jobs_initial[0]["id"], status="saved")

        # Second job with different JobStreet ID, but same company, title, platform, and date
        job2 = Job(
            title="Junior Full Stack Developer",
            company="Microgenesis Business Systems",
            location="Manila, Philippines",
            platform="JobStreet",
            tier=1,
            job_url="https://www.jobstreet.com.ph/job/95253020",
            date_posted="2026-10-14"
        )
        added2, skipped2 = insert_jobs(self.db_path, [job2])
        self.assertEqual(added2, 1)
        self.assertEqual(skipped2, 0)
        jobs = get_jobs(self.db_path, search="Microgenesis")
        self.assertEqual(len(jobs), 2)
        self.assertEqual(next(j for j in jobs if j["job_url"] == job1.job_url)["status"], "saved")
        self.assertEqual(next(j for j in jobs if j["job_url"] == job2.job_url)["status"], "new")

    def test_same_platform_diff_timeline_repost(self):
        """Reposts on the same platform with different dates should be treated as new opportunities."""
        job1 = Job(
            title="Associate Software Engineer",
            company="Finastra Philippines Inc",
            location="Manila, Philippines",
            platform="JobStreet",
            tier=1,
            job_url="https://www.jobstreet.com.ph/job/95117343",
            date_posted="2026-09-01"
        )
        added, skipped = insert_jobs(self.db_path, [job1])
        self.assertEqual(added, 1)

        # Repost weeks later with a newer date and new URL
        job2 = Job(
            title="Associate Software Engineer",
            company="Finastra Philippines Inc",
            location="Manila, Philippines",
            platform="JobStreet",
            tier=1,
            job_url="https://www.jobstreet.com.ph/job/95213180",
            date_posted="2026-10-16"
        )
        added2, skipped2 = insert_jobs(self.db_path, [job2])
        self.assertEqual(added2, 1)

        # Both records exist because timelines are different
        jobs = get_jobs(self.db_path, search="Finastra")
        self.assertEqual(len(jobs), 2)

    def test_cross_platform_deduplication_indeed_glassdoor(self):
        """Cross-platform duplicate jobs (e.g. Indeed and Glassdoor) with varying location syntax must merge into single card with multi-sources."""
        job_indeed = Job(
            title="Full Stack Software Developer",
            company="ADI Recruitment",
            location="Mandaluyong, P00, Philippines",
            platform="Indeed",
            tier=1,
            job_url="https://ph.indeed.com/viewjob?jk=fe3edcc600772987",
            salary="PHP 70k - 90k",
            date_posted="2026-10-15"
        )
        added1, skipped1 = insert_jobs(self.db_path, [job_indeed])
        self.assertEqual(added1, 1)
        self.assertEqual(skipped1, 0)

        # Same requisition arriving from Glassdoor with slightly different location string
        job_glassdoor = Job(
            title="Full Stack Software Developer",
            company="ADI Recruitment",
            location="Mandaluyong City, Philippines",
            platform="Glassdoor",
            tier=1,
            job_url="https://www.glassdoor.com/job-listing/j?jl=1010296536545",
            salary="PHP 70k - 90k",
            date_posted="2026-10-16"
        )
        added2, skipped2 = insert_jobs(self.db_path, [job_glassdoor])
        self.assertEqual(added2, 0)
        self.assertEqual(skipped2, 1)

        # Exactly 1 combined record in database
        jobs = get_jobs(self.db_path, search="ADI Recruitment")
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(len(job["sources"]), 2)
        platforms = {s["platform"] for s in job["sources"]}
        self.assertEqual(platforms, {"Indeed", "Glassdoor"})
        # Date should be updated to latest
        self.assertEqual(job["date_posted"], "2026-10-16")

    def test_filter_15days(self):
        """15days filter must include jobs up to 15 days ago and exclude older ones."""
        import datetime
        today = datetime.date.today()
        d14 = (today - datetime.timedelta(days=14)).isoformat()
        d15 = (today - datetime.timedelta(days=15)).isoformat()
        d16 = (today - datetime.timedelta(days=16)).isoformat()

        j14 = Job(title="Dev 14d", company="Co1", location="PH", platform="Indeed", tier=1, job_url="https://j14", date_posted=d14)
        j15 = Job(title="Dev 15d", company="Co2", location="PH", platform="Glassdoor", tier=1, job_url="https://j15", date_posted=d15)
        j16 = Job(title="Dev 16d", company="Co3", location="PH", platform="LinkedIn", tier=1, job_url="https://j16", date_posted=d16)
        insert_jobs(self.db_path, [j14, j15, j16])

        jobs_15d = get_jobs(self.db_path, date_filter="15days")
        titles_15d = {j["title"] for j in jobs_15d}
        self.assertIn("Dev 14d", titles_15d)
        self.assertIn("Dev 15d", titles_15d)
        self.assertNotIn("Dev 16d", titles_15d)

    def test_recently_detected_and_saved(self):
        """Terms like 'Posted recently' or 'Recently' should be normalized and retained within 15 days."""
        job_recent = Job(
            title="Junior Cloud Engineer",
            company="CloudTech",
            location="Remote",
            platform="Indeed",
            tier=1,
            job_url="https://cloudtech-recent",
            date_posted="Posted recently"
        )
        insert_jobs(self.db_path, [job_recent])
        jobs = get_jobs(self.db_path, search="CloudTech", date_filter="15days")
        self.assertEqual(len(jobs), 1)
        self.assertTrue(bool(jobs[0]["date_posted"]))

if __name__ == "__main__":
    unittest.main()


