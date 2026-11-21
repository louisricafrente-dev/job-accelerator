import ast
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import tempfile
import threading
import time
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import src.aggregator as aggregator_mod
from src import execution_inbox as inbox
from src.connectors.direct_ats import AshbyConnector, GreenhouseConnector, WorkableConnector
from src.connectors.ph_jobs import BossjobConnector
from src.connectors.remote_feed import HimalayasConnector
from src.connectors.smartrecruiters import COMPANIES as SR_COMPANIES
from src.connectors.talent_ph import TalentPHConnector
from src.connectors.web3_career import Web3CareerConnector
from src.database import init_db
from src.inbox_worker import run_local
from src.models import MANILA


class DirectATSAndTalentPHTests(TestCase):
    def test_greenhouse_prefilters_rechecks_description_and_handles_partial_failure(self):
        today = datetime.now(MANILA).date()
        today_iso = f"{today.isoformat()}T08:00:00+08:00"
        old_iso = f"{(today - timedelta(days=8)).isoformat()}T08:00:00+08:00"

        list_rows = [
            {
                "id": 101,
                "title": "Software Engineer",
                "location": {"name": "Manila, Philippines"},
                "first_published": today_iso,
                "absolute_url": "https://job-boards.greenhouse.io/xendit/jobs/101",
            },
            {
                "id": 102,
                "title": "Graduate Software Engineer",
                "location": {"name": "Home based - Worldwide"},
                "first_published": today_iso,
                "absolute_url": "https://job-boards.greenhouse.io/canonical/jobs/102",
            },
            {
                "id": 103,
                "title": "Backend Engineer",
                "location": {"name": "Remote"},
                "first_published": today_iso,
                "absolute_url": "https://job-boards.greenhouse.io/example/jobs/103",
            },
            {
                "id": 104,
                "title": "Frontend Developer",
                "location": {"name": "Remote, United States"},
                "first_published": today_iso,
                "absolute_url": "https://job-boards.greenhouse.io/example/jobs/104",
            },
            {
                "id": 105,
                "title": "Senior Accountant",
                "location": {"name": "Manila, Philippines"},
                "first_published": today_iso,
                "absolute_url": "https://job-boards.greenhouse.io/example/jobs/105",
            },
            {
                "id": 106,
                "title": "Android Developer",
                "location": {"name": "Manila, Philippines"},
                "first_published": old_iso,
                "absolute_url": "https://job-boards.greenhouse.io/example/jobs/106",
            },
        ]

        details = {
            "101": {
                "id": 101,
                "title": "Software Engineer",
                "company_name": "Xendit",
                "location": {"name": "Manila, Philippines"},
                "first_published": today_iso,
                "absolute_url": "https://job-boards.greenhouse.io/xendit/jobs/101",
                "content": "&lt;p&gt;Build &amp; scale APIs in Manila.&lt;/p&gt;",
            },
            "102": {
                "id": 102,
                "title": "Graduate Software Engineer",
                "company_name": "Canonical",
                "location": {"name": "Home based - Worldwide"},
                "first_published": today_iso,
                "absolute_url": "https://job-boards.greenhouse.io/canonical/jobs/102",
                "content": "<p>Linux engineering role open worldwide.</p>",
            },
            "103": {
                "id": 103,
                "title": "Backend Engineer",
                "company_name": "Example",
                "location": {"name": "Remote"},
                "first_published": today_iso,
                "absolute_url": "https://job-boards.greenhouse.io/example/jobs/103",
                "content": "<p>Remote role. Applicants must reside in the United States only.</p>",
            },
        }

        def read_json(_, url):
            if "/unavailable/" in url:
                raise ValueError("HTTP 503")
            if url.endswith("content=false"):
                return {"jobs": list_rows}
            job_id = url.rsplit("/", 1)[-1]
            return details[job_id]

        board = GreenhouseConnector()
        with patch.object(board, "COMPANIES", ("example", "unavailable")), \
                patch.object(board, "_read_json", side_effect=read_json) as mock_read:
            jobs = board.fetch()

        # Only 2 board list requests + 3 matching detail requests (104/105/106 filtered before detail fetch)
        self.assertEqual(mock_read.call_count, 5)
        self.assertEqual([j.job_url for j in jobs], [
            "https://job-boards.greenhouse.io/xendit/jobs/101",
            "https://job-boards.greenhouse.io/canonical/jobs/102",
        ])
        self.assertEqual(jobs[0].description, "Build & scale APIs in Manila.")
        self.assertEqual(jobs[0].platform, "Greenhouse")
        self.assertEqual(board.last_raw_count, 6)
        self.assertEqual(board.last_error, "")
        self.assertIn("unavailable", board.coverage_warning)

    def test_greenhouse_all_unavailable_sets_error(self):
        board = GreenhouseConnector()
        with patch.object(board, "COMPANIES", ("unavailable",)), \
                patch.object(board, "_read_json", side_effect=ValueError("HTTP 503")):
            self.assertEqual(board.fetch(), [])
        self.assertEqual(board.last_raw_count, 0)
        self.assertIn("HTTP 503", board.last_error)

    def test_ashby_filters_foreign_and_unlisted_and_handles_partial_failure(self):
        today = datetime.now(MANILA).date()
        today_iso = f"{today.isoformat()}T09:00:00+00:00"
        old_iso = f"{(today - timedelta(days=10)).isoformat()}T09:00:00+00:00"

        payload = {
            "jobs": [
                {
                    "id": "1",
                    "title": "Software Engineer - Postgres Tooling",
                    "location": "Remote, Global",
                    "secondaryLocations": [{"location": "Philippines"}],
                    "isRemote": True,
                    "isListed": True,
                    "publishedAt": today_iso,
                    "jobUrl": "https://jobs.ashbyhq.com/supabase/1",
                    "descriptionPlain": "Work from anywhere globally.",
                },
                {
                    "id": "2",
                    "title": "Technical Support Engineer (APAC)",
                    "location": "APAC",
                    "secondaryLocations": [],
                    "isRemote": True,
                    "isListed": True,
                    "publishedAt": today_iso,
                    "jobUrl": "https://jobs.ashbyhq.com/supabase/2",
                    "descriptionPlain": "APAC remote software support with SQL and REST APIs.",
                },
                {
                    "id": "3",
                    "title": "Backend Engineer",
                    "location": "Remote, AMER",
                    "secondaryLocations": [],
                    "isRemote": True,
                    "isListed": True,
                    "publishedAt": today_iso,
                    "jobUrl": "https://jobs.ashbyhq.com/supabase/3",
                    "descriptionPlain": "Americas timezones only.",
                },
                {
                    "id": "4",
                    "title": "Site Reliability Engineer",
                    "location": "Remote (US)",
                    "secondaryLocations": [],
                    "isRemote": True,
                    "isListed": True,
                    "publishedAt": today_iso,
                    "jobUrl": "https://jobs.ashbyhq.com/supabase/4",
                    "descriptionPlain": "US remote.",
                },
                {
                    "id": "5",
                    "title": "Full Stack Engineer",
                    "location": "Remote, Global",
                    "secondaryLocations": [],
                    "isRemote": True,
                    "isListed": False,
                    "publishedAt": today_iso,
                    "jobUrl": "https://jobs.ashbyhq.com/supabase/5",
                    "descriptionPlain": "Unlisted draft.",
                },
                {
                    "id": "6",
                    "title": "Old Software Engineer",
                    "location": "Remote, Global",
                    "secondaryLocations": [],
                    "isRemote": True,
                    "isListed": True,
                    "publishedAt": old_iso,
                    "jobUrl": "https://jobs.ashbyhq.com/supabase/6",
                    "descriptionPlain": "Expired posting.",
                },
            ]
        }

        def read_json(_, url):
            if "/unavailable" in url:
                raise ValueError("HTTP 502")
            return payload

        board = AshbyConnector()
        with patch.object(board, "COMPANIES", ("supabase", "unavailable")), \
                patch.object(board, "_read_json", side_effect=read_json):
            jobs = board.fetch()

        self.assertEqual([j.job_url for j in jobs], [
            "https://jobs.ashbyhq.com/supabase/1",
            "https://jobs.ashbyhq.com/supabase/2",
        ])
        self.assertEqual(jobs[0].company, "Supabase")
        self.assertEqual(jobs[1].location, "APAC (Remote)")
        self.assertEqual(board.last_raw_count, 6)
        self.assertEqual(board.last_error, "")
        self.assertIn("unavailable", board.coverage_warning)

    def test_talent_ph_parses_cards_deduplicates_maps_dates_and_handles_partial_errors(self):
        today = datetime.now(MANILA).date()
        today_iso = f"{today.isoformat()}T05:00:00Z"
        old_iso = f"{(today - timedelta(days=9)).isoformat()}T05:00:00Z"

        html = f"""
        <html><body>
          <article class="JobCard_card__abc">
            <h2 class="JobCard_title__xyz">Junior Web Developer</h2>
            <span class="JobCard_company__111">Manila Tech Co</span>
            <span class="JobCard_location__222">Makati, Metro Manila, Philippines</span>
            <p class="JobCard_snippet__333">Build React and Node.js apps. <a href="/view?id=9001">Show more</a></p>
            <time datetime="{today_iso}">Last updated: 3 hours ago</time>
          </article>
          <article class="JobCard_card__abc">
            <h2 class="JobCard_title__xyz">Software Engineer</h2>
            <span class="JobCard_company__111">Laguna Systems</span>
            <span class="JobCard_location__222">Santa Rosa, Laguna, Philippines</span>
            <p class="JobCard_snippet__333">Full-stack work <a href="/view?id=9002">Show more</a></p>
            <time datetime="{old_iso}">Last updated: 9 days ago</time>
          </article>
          <article class="JobCard_card__abc">
            <h2 class="JobCard_title__xyz">Registered Nurse</h2>
            <span class="JobCard_company__111">Hospital PH</span>
            <span class="JobCard_location__222">Cebu City, Philippines</span>
            <p class="JobCard_snippet__333">Clinic duties <a href="/view?id=9003">Show more</a></p>
            <time datetime="{today_iso}">Last updated: 2 hours ago</time>
          </article>
        </body></html>
        """

        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            if "failquery" in url:
                raise RuntimeError("HTTP 503")
            return MagicMock(status_code=200, text=html)

        board = TalentPHConnector()
        board.window_days = 3
        with patch.object(board, "QUERIES", ("software developer", "web developer", "failquery")), \
                patch.object(board, "get_url", side_effect=fake_get):
            jobs = board.fetch()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].job_url, "https://ph.talent.com/view?id=9001")
        self.assertEqual(jobs[0].company, "Manila Tech Co")
        self.assertEqual(jobs[0].platform, "Talent.com PH")
        self.assertEqual(jobs[0].description, "Build React and Node.js apps.")
        first_params = parse_qs(urlsplit(calls[0]).query)
        self.assertEqual(first_params["date"], ["3"])
        self.assertEqual(first_params["l"], ["Philippines"])
        self.assertEqual(board.last_error, "")
        self.assertIn("failquery", board.coverage_warning)

        board_err = TalentPHConnector()
        with patch.object(board_err, "QUERIES", ("onlyfail",)), \
                patch.object(board_err, "get_url", side_effect=RuntimeError("HTTP 403")):
            self.assertEqual(board_err.fetch(), [])
        self.assertIn("HTTP 403", board_err.last_error)

    def test_smartrecruiters_includes_grab_and_aggregator_registers_new_boards(self):
        self.assertIn("Grab", SR_COMPANIES)

        source = Path(aggregator_mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "get_default_connectors"
        )
        call_names = {
            node.func.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertIn("GreenhouseConnector", call_names)
        self.assertIn("AshbyConnector", call_names)
        self.assertIn("WorkableConnector", call_names)
        self.assertIn("TalentPHConnector", call_names)
        self.assertIn("Web3CareerConnector", call_names)
        self.assertIn("SmartRecruitersConnector", call_names)
        self.assertIn("WellfoundConnector", call_names)
        self.assertNotIn("ContraConnector", call_names)
        self.assertNotIn("FlexJobsConnector", call_names)
        self.assertNotIn("ZipRecruiter", source)

        if not getattr(aggregator_mod.get_default_connectors, "_mock_name", None):
            platforms = {c.platform for c in aggregator_mod.get_default_connectors()}
            self.assertTrue({"Greenhouse", "Ashby", "Workable", "Talent.com PH", "Web3.career", "SmartRecruiters", "Wellfound"}.issubset(platforms))
            self.assertTrue({"ZipRecruiter", "Contra", "FlexJobs"}.isdisjoint(platforms))

    def test_workable_parses_widget_and_handles_partial_failure(self):
        today = datetime.now(MANILA).date()
        today_iso = today.isoformat()
        old_iso = (today - timedelta(days=10)).isoformat()

        payload = {
            "jobs": [
                {
                    "title": "Junior QA Automation Engineer",
                    "published_on": today_iso,
                    "url": "https://apply.workable.com/j/ABC123",
                    "city": "Pasig",
                    "state": "NCR",
                    "country": "Philippines",
                    "telecommuting": True,
                    "department": "Engineering",
                    "employment_type": "Full-time",
                    "description": "Playwright testing in Manila.",
                },
                {
                    "title": "Accounting Associate",
                    "published_on": today_iso,
                    "url": "https://apply.workable.com/j/ACC1",
                    "city": "Pasig",
                    "country": "Philippines",
                    "telecommuting": False,
                },
                {
                    "title": "Old Software Developer",
                    "published_on": old_iso,
                    "url": "https://apply.workable.com/j/OLD1",
                    "city": "Makati",
                    "country": "Philippines",
                    "telecommuting": False,
                },
            ]
        }

        def read_json(_, url):
            if "/unavailable" in url:
                raise ValueError("HTTP 429")
            return payload

        board = WorkableConnector()
        with patch.object(board, "COMPANIES", ("isupport-worldwide", "unavailable")), \
                patch.object(board, "_read_json", side_effect=read_json):
            jobs = board.fetch()

        self.assertEqual([j.job_url for j in jobs], ["https://apply.workable.com/j/ABC123"])
        self.assertEqual(jobs[0].company, "iSupport Worldwide")
        self.assertEqual(jobs[0].platform, "Workable")
        self.assertIn("Remote", jobs[0].location)
        self.assertEqual(board.last_error, "")
        self.assertIn("unavailable", board.coverage_warning)

        err_board = WorkableConnector()
        with patch.object(err_board, "COMPANIES", ("unavailable",)), \
                patch.object(err_board, "_read_json", side_effect=ValueError("HTTP 429")):
            self.assertEqual(err_board.fetch(), [])
        self.assertIn("HTTP 429", err_board.last_error)

    def test_web3_career_pairs_rows_and_jsonld_and_filters_regions(self):
        today = datetime.now(MANILA).date()
        today_dt = f"{today.isoformat()} 12:00:00 +0000"
        old_dt = f"{(today - timedelta(days=10)).isoformat()} 12:00:00 +0000"

        ld_anywhere = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Junior Full Stack Engineer",
            "datePosted": today_dt,
            "description": "Build TypeScript and React Web3 tools.",
            "hiringOrganization": {"@type": "Organization", "name": "Protocol Labs"},
            "jobLocationType": "TELECOMMUTE",
            "applicantLocationRequirements": {"@type": "Country", "name": "Anywhere"},
            "baseSalary": {"@type": "MonetaryAmount", "currency": "USD", "value": {"@type": "QuantitativeValue", "minValue": 60000, "maxValue": 90000, "unitText": "YEAR"}},
        }
        ld_us_only = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Backend Engineer",
            "datePosted": today_dt,
            "description": "US remote only.",
            "hiringOrganization": {"@type": "Organization", "name": "US Startup"},
            "jobLocationType": "TELECOMMUTE",
            "applicantLocationRequirements": {"@type": "Country", "name": "United States"},
        }
        ld_old = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Software Developer",
            "datePosted": old_dt,
            "description": "Old listing.",
            "hiringOrganization": {"@type": "Organization", "name": "Old Co"},
            "jobLocationType": "TELECOMMUTE",
            "applicantLocationRequirements": {"@type": "Country", "name": "Anywhere"},
        }

        html = f"""
        <html><head>
          <script type="application/ld+json">{json.dumps(ld_anywhere)}</script>
          <script type="application/ld+json">{json.dumps(ld_us_only)}</script>
          <script type="application/ld+json">{json.dumps(ld_old)}</script>
        </head><body><table>
          <tr data-jobid="1001"><td><a href="/junior-full-stack-engineer-protocol-labs/1001"><h2>Junior Full Stack Engineer</h2></a></td></tr>
          <tr data-jobid="1002"><td><a href="/backend-engineer-us-startup/1002"><h2>Backend Engineer</h2></a></td></tr>
          <tr data-jobid="1003"><td><a href="/software-developer-old-co/1003"><h2>Software Developer</h2></a></td></tr>
        </table></body></html>
        """

        def fake_get(url, **kwargs):
            if "page=2" in url:
                raise RuntimeError("HTTP 503")
            return MagicMock(status_code=200, text=html)

        board = Web3CareerConnector()
        with patch.object(board, "get_url", side_effect=fake_get):
            jobs = board.fetch()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].job_url, "https://web3.career/junior-full-stack-engineer-protocol-labs/1001")
        self.assertEqual(jobs[0].company, "Protocol Labs")
        self.assertEqual(jobs[0].salary, "USD 60,000 - 90,000/year")
        self.assertEqual(jobs[0].platform, "Web3.career")
        self.assertEqual(board.last_error, "")
        self.assertIn("page 2", board.coverage_warning)

    def test_himalayas_has_polite_query_delay_configured(self):
        delay = HimalayasConnector.query_delay_seconds
        self.assertIsInstance(delay, tuple)
        self.assertEqual(len(delay), 2)
        self.assertGreaterEqual(delay[0], 2.0)

    def test_run_local_auto_recovers_recent_cloud_partial_with_deferred_boards_once(self):
        with tempfile.TemporaryDirectory() as temp:
            db = str(Path(temp) / "recover.db")
            init_db(db)
            cmd = inbox.enqueue(db, ["developer"], automatic=True, now=time.time() - 100)
            claimed_cloud = inbox.claim(db, "cloud", "github")
            self.assertIsNotNone(claimed_cloud)
            inbox.update_owned(
                db,
                claimed_cloud,
                result={
                    "status": "partial",
                    "added": 1,
                    "skipped": 0,
                    "total_fetched": 1,
                    "platforms": {"Indeed": 1},
                    "progress": {
                        "has_more": False,
                        "unfinished": True,
                        "deferred_boards": [{"platform": "Glassdoor", "error": "403", "retry_at": time.time() + 3600}],
                    },
                },
            )

            stop = threading.Event()
            claimed_runs = []

            def fake_run_claimed(db_arg, claimed_arg, agg_arg, key=inbox.KEY):
                claimed_runs.append(claimed_arg)
                inbox.update_owned(
                    db_arg,
                    claimed_arg,
                    result={
                        "status": "ok",
                        "added": 2,
                        "skipped": 0,
                        "total_fetched": 2,
                        "platforms": {"Glassdoor": 2},
                        "progress": {"has_more": False, "unfinished": False, "deferred_boards": []},
                    },
                )
                stop.set()

            with patch("src.inbox_worker.run_claimed", side_effect=fake_run_claimed), \
                    patch("src.inbox_worker.inbox.POLL_SECONDS", 0):
                run_local(db, MagicMock(), stop=stop)

            self.assertEqual(len(claimed_runs), 1)
            self.assertTrue(claimed_runs[0]["resume"])
            self.assertFalse(claimed_runs[0]["restart"])
            self.assertEqual(claimed_runs[0]["executor"], "local")
            self.assertEqual(inbox.read(db)["status"], "complete")

    def test_bossjob_accepts_only_verified_active_recruitment_when_published_older(self):
        today = datetime.now(MANILA).date()
        today_str = today.isoformat()
        old_valid_pub = (today - timedelta(days=45)).isoformat()
        ancient_pub = (today - timedelta(days=240)).isoformat()
        future_exp = (today + timedelta(days=30)).isoformat()
        past_exp = (today - timedelta(days=1)).isoformat()

        base_item = {
            "job_title": "Junior Web Developer",
            "company_name": "Active PH Co",
            "job_country": "Philippines",
            "job_location": "Manila",
            "status_key": "active",
            "recruiter_status_key": "active",
            "company_is_onhold": False,
            "published_at": old_valid_pub,
            "expired_at": future_exp,
            "recruiter_last_active_at": f"{today_str} 14:00:00",
            "recruiter_reply_label": "Reply today 3 times",
            "activity_score": 25,
        }

        items = [
            {**base_item, "id": 1, "job_url": "/job/valid-active-1"},
            {**base_item, "id": 2, "job_url": "/job/zero-reply-2", "recruiter_reply_label": "Reply today 0 times"},
            {**base_item, "id": 3, "job_url": "/job/low-score-3", "activity_score": 10},
            {**base_item, "id": 4, "job_url": "/job/inactive-rec-4", "recruiter_status_key": "inactive"},
            {**base_item, "id": 5, "job_url": "/job/expired-5", "expired_at": past_exp},
            {**base_item, "id": 6, "job_url": "/job/ancient-6", "published_at": ancient_pub},
            {**base_item, "id": 7, "job_url": "/job/stale-rec-7", "recruiter_last_active_at": (today - timedelta(days=10)).isoformat()},
            {**base_item, "id": 8, "job_url": "/job/onhold-fresh-8", "published_at": today_str, "company_is_onhold": True},
        ]

        board = BossjobConnector()
        payload = json.dumps({"code": 0, "data": {"jobs": items, "total_pages": 1}}).encode()
        with patch.object(board, "open_url", return_value=io.BytesIO(payload)):
            jobs = board.fetch("Web Developer")

        self.assertEqual([j.job_url for j in jobs], ["https://bossjob.ph/en/job/valid-active-1"])
        self.assertIn(today_str, jobs[0].date_posted)

    def test_himalayas_stops_at_max_pages_and_clears_cursor(self):
        self.assertEqual(HimalayasConnector.revision, 4)
        self.assertEqual(HimalayasConnector.MAX_PAGES, 30)
        board = HimalayasConnector()
        now = int(datetime.now(MANILA).timestamp())
        start, _ = board.date_window()
        board.feed_state = {
            "window_start": start.date().isoformat(),
            "query": "",
            "pages_saved": HimalayasConnector.MAX_PAGES - 1,
            "cursor": "cursor-29",
            "seen_pages": [],
        }
        data = {
            "jobs": [{"guid": "h-30", "title": "Software Engineer", "applicationLink": "https://example.com/h30", "pubDate": now}],
            "nextCursor": "cursor-30",
            "totalCount": 5000,
        }
        with patch.object(board, "open_url", return_value=io.BytesIO(json.dumps(data).encode())):
            jobs = board.fetch()

        self.assertEqual(len(jobs), 1)
        self.assertFalse(board.has_more)
        self.assertIsNone(board.next_feed_state["cursor"])
        self.assertIn("capped at 30 pages", board.coverage_warning)

    def test_run_local_resumes_local_partial_only_after_cooldown_expires(self):
        with tempfile.TemporaryDirectory() as temp:
            db = str(Path(temp) / "local_resume.db")
            init_db(db)
            inbox.enqueue(db, ["developer"], automatic=True, now=time.time() - 10)
            claimed_future = inbox.claim(db, "local", "pc")
            self.assertIsNotNone(claimed_future)
            inbox.update_owned(
                db,
                claimed_future,
                result={
                    "status": "partial",
                    "added": 1,
                    "skipped": 0,
                    "total_fetched": 1,
                    "platforms": {"LinkedIn": 1},
                    "progress": {
                        "has_more": False,
                        "can_continue": False,
                        "unfinished": True,
                        "deferred_boards": [{"platform": "LinkedIn", "error": "HTTP Error 429", "retry_at": time.time() + 600}],
                    },
                },
            )

            stop_wait = threading.Event()
            stop_wait.is_set = MagicMock(side_effect=[False, True])
            with patch("src.inbox_worker.run_claimed") as mock_run_future, \
                    patch("src.inbox_worker.inbox.POLL_SECONDS", 0):
                run_local(db, MagicMock(), stop=stop_wait)
            mock_run_future.assert_not_called()

            db_ready = str(Path(temp) / "local_resume_ready.db")
            init_db(db_ready)
            inbox.enqueue(db_ready, ["developer"], automatic=True, now=time.time() - 10)
            claimed_ready = inbox.claim(db_ready, "local", "pc")
            self.assertIsNotNone(claimed_ready)
            inbox.update_owned(
                db_ready,
                claimed_ready,
                result={
                    "status": "partial",
                    "added": 1,
                    "skipped": 0,
                    "total_fetched": 1,
                    "platforms": {"LinkedIn": 1},
                    "progress": {
                        "has_more": False,
                        "can_continue": False,
                        "unfinished": True,
                        "deferred_boards": [{"platform": "LinkedIn", "error": "HTTP Error 429", "retry_at": time.time() - 10}],
                    },
                },
            )

            stop_ready = threading.Event()
            claimed_runs = []

            def fake_run_claimed(db_arg, claimed_arg, agg_arg, key=inbox.KEY):
                claimed_runs.append(claimed_arg)
                inbox.update_owned(
                    db_arg,
                    claimed_arg,
                    result={
                        "status": "ok",
                        "added": 4,
                        "skipped": 0,
                        "total_fetched": 4,
                        "platforms": {"LinkedIn": 4},
                        "progress": {"has_more": False, "can_continue": False, "unfinished": False, "deferred_boards": []},
                    },
                )
                stop_ready.set()

            with patch("src.inbox_worker.run_claimed", side_effect=fake_run_claimed), \
                    patch("src.inbox_worker.inbox.POLL_SECONDS", 0):
                run_local(db_ready, MagicMock(), stop=stop_ready)

            self.assertEqual(len(claimed_runs), 1)
            self.assertTrue(claimed_runs[0]["resume"])
            self.assertFalse(claimed_runs[0]["restart"])
            self.assertEqual(inbox.read(db_ready)["status"], "complete")
