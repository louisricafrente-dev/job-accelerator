import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from src.aggregator import Aggregator
from src.connectors.base import BaseConnector
from src.connectors.ph_jobs import OnlineJobsConnector, BossjobConnector, JobStreetConnector
from src.connectors.remote_feed import JobicyConnector, HimalayasConnector, FreelancerConnector
from src.database import init_db, get_jobs, get_user_setting
from src.models import Job, MANILA, scrape_date_window
from src.sync_batches import PROGRESS_KEY
from tests.test_sync_batches import Clock


def response(data):
    return io.BytesIO(json.dumps(data).encode())


class PagedQuery(BaseConnector):
    platform = "Paged query test"
    tier = 1
    checkpointed_query = True
    query_group_size = 5

    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.fail_once = False

    def fetch(self, query="", location=""):
        state = self.page_state(query)
        page = state.get("page", 0)
        self.calls.append((query, page))
        self.clock.value += 2
        if self.fail_once and query == "a" and page == 1:
            self.fail_once = False
            raise RuntimeError("temporary outage")
        self.finish_page(state, [f"{query}-{page}"], ["today"], page < 2)
        state["page"] = page + 1
        return [Job("Software Developer", f"Example {query}-{page}", "Philippines", self.platform, 1,
                    f"https://example.com/{query}-{page}", date_posted="today")]


class TestDurableQueryPages(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = os.path.join(temp.name, "coverage.db")
        init_db(self.db)
        self.clock = Clock()
        self.board = PagedQuery(self.clock)
        for name, value in [("time.monotonic", self.clock.monotonic), ("time.time", self.clock.time), ("QUERY_DELAY_SECONDS", 0)]:
            p = patch("src.sync_batches." + name, value)
            p.start()
            self.addCleanup(p.stop)

    def run_batch(self, budget=1, resume=False):
        return Aggregator(self.db, [self.board]).run_sync(["a", "b"], budget_seconds=budget, cycle_id="coverage", resume=resume)

    def test_cursor_survives_instances_and_keyword_is_not_complete_at_first_page(self):
        first = self.run_batch()
        self.assertEqual(first["progress"]["completed_searches"], 0)
        saved = json.loads(get_user_setting(self.db, PROGRESS_KEY))["boards"][self.board.platform]
        self.assertEqual(saved["query_states"]["a"]["page"], 1)
        self.assertNotIn("a", saved.get("completed_queries", {}))
        for _ in range(5):
            result = self.run_batch()
        self.assertEqual(self.board.calls, [("a", 0), ("a", 1), ("a", 2), ("b", 0), ("b", 1), ("b", 2)])
        self.assertFalse(result["progress"]["has_more"])
        self.assertEqual(len(get_jobs(self.db)), 6)

    def test_error_on_later_page_keeps_its_cursor_while_other_keyword_finishes(self):
        self.run_batch()
        self.board.fail_once = True
        result = self.run_batch()
        self.assertEqual(result["status"], "partial")
        self.clock.value += 901
        result = self.run_batch(budget=100, resume=True)
        self.assertEqual(self.board.calls, [("a", 0), ("a", 1), ("b", 0), ("b", 1), ("b", 2), ("a", 1), ("a", 2)])
        self.assertFalse(result["progress"]["unfinished"])

    def test_ingestion_failure_cannot_commit_next_page(self):
        self.run_batch()
        with patch("src.sync_batches.insert_jobs", side_effect=RuntimeError("database unavailable")):
            result = self.run_batch()
        self.assertEqual(result["status"], "error")
        saved = json.loads(get_user_setting(self.db, PROGRESS_KEY))["boards"][self.board.platform]
        self.assertEqual(saved["query_states"]["a"]["page"], 1)
        self.clock.value += 901
        self.run_batch(resume=True)
        self.assertEqual(self.board.calls[-2:], [("a", 1), ("a", 1)])

    def test_limited_source_finishes_partial_without_an_automatic_retry_loop(self):
        self.board.coverage_limit = "Coverage limited: no verified public continuation"
        original = self.board.fetch
        def limited(query="", location=""):
            jobs = original(query, location)
            self.board.coverage_warning = self.board.coverage_limit
            return jobs
        with patch.object(self.board, "fetch", side_effect=limited):
            result = self.run_batch(budget=100)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["progress"]["has_more"])
        self.assertFalse(result["progress"]["unfinished"])
        self.assertTrue(result["progress"]["coverage_issues"])
        before = len(self.board.calls)
        result = self.run_batch()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(self.board.calls), before)


class TestSourcePageBoundaries(unittest.TestCase):
    def test_jobstreet_keeps_yesterday_midnight_when_source_timestamp_is_utc(self):
        from datetime import timezone
        start, _ = scrape_date_window()
        jobs = JobStreetConnector()._parse_items([{"id": "one", "title": "Software Developer",
                                                   "listingDate": start.astimezone(timezone.utc).isoformat()}])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].date_posted, start.date().isoformat())

    def test_unknown_or_invalid_dates_do_not_trigger_a_successful_old_page_cutoff(self):
        c = JobicyConnector()
        state = c.page_state()
        c.finish_page(state, ["unknown"], ["2026-00-00"], True, ordered=True)
        self.assertFalse(c.has_more)
        self.assertIn("unverified", c.coverage_warning)

    def test_ziprecruiter_feed_pages_use_feed_state_in_the_real_scheduler(self):
        import pandas as pd
        from types import SimpleNamespace
        from src.connectors.jobspy_adapter import JobSpyAdapter
        c = JobSpyAdapter("ZipRecruiter", "zip_recruiter", 2)
        offsets = []
        def scrape(**kwargs):
            offsets.append(kwargs["offset"])
            count = 35 if kwargs["offset"] == 0 else 1
            return pd.DataFrame([{"job_url": f"https://example.com/{kwargs['offset']+i}", "title": "Software Developer",
                                  "date_posted": "today", "location": "Philippines"} for i in range(count)])
        with tempfile.TemporaryDirectory() as temp:
            db = os.path.join(temp, "zip.db")
            init_db(db)
            with patch.dict("sys.modules", {"jobspy": SimpleNamespace(scrape_jobs=scrape)}), patch("src.sync_batches.QUERY_DELAY_SECONDS", 0):
                result = Aggregator(db, [c]).run_sync(["developer"], budget_seconds=5)
        self.assertEqual(offsets, [0, 35])
        self.assertFalse(result["progress"]["has_more"])

    def test_jobicy_continues_beyond_fifty_and_stops_at_verified_old_page(self):
        c = JobicyConnector()
        start, _ = scrape_date_window()
        calls = []
        def fetch(request, **kwargs):
            params = parse_qs(urlsplit(request.full_url).query)
            calls.append(params)
            page = len(calls)
            date = "today" if page < 3 else (start-timedelta(days=1)).date().isoformat()
            rows = [{"id": f"{page}-{i}", "jobTitle": "Software Developer", "url": f"https://example.com/{page}-{i}", "pubDate": date} for i in range(50)]
            return response({"success": True, "jobs": rows, "nextCursor": f"cursor-{page}", "hasMore": True})
        with patch.object(c, "open_url", side_effect=fetch):
            total = 0
            for _ in range(3):
                total += len(c.fetch())
                self.assertEqual(c.last_error, "")
                c.feed_state = dict(c.next_feed_state)
        self.assertEqual(total, 100)
        self.assertEqual(calls[1]["cursor"], ["cursor-1"])
        self.assertNotIn("tag", calls[0], "Do not silently exclude configured roles using a fixed dev tag")
        self.assertFalse(c.has_more)

    def test_himalayas_uses_browse_cursor_not_curated_search_page(self):
        c = HimalayasConnector()
        now = int(datetime.now(MANILA).timestamp())
        data = {"jobs": [{"guid": "one", "title": "Software Developer", "applicationLink": "https://example.com/one", "pubDate": now}],
                "nextCursor": "opaque1", "totalCount": 50}
        with patch.object(c, "open_url", return_value=response(data)) as fetch:
            c.fetch()
        self.assertTrue(c.has_more)
        self.assertEqual(urlsplit(fetch.call_args.args[0].full_url).path, "/jobs/api")
        c.feed_state = dict(c.next_feed_state)
        data["jobs"][0]["guid"] = "two"
        data["nextCursor"] = "opaque2"
        with patch.object(c, "open_url", return_value=response(data)) as fetch:
            c.fetch()
        self.assertEqual(parse_qs(urlsplit(fetch.call_args.args[0].full_url).query)["cursor"], ["opaque1"])

    def test_onlinejobs_uses_real_offsets_and_does_not_stop_at_fifty_or_sixty(self):
        c = OnlineJobsConnector()
        start, _ = scrape_date_window()
        calls = []
        def fetch(request, **kwargs):
            offset = len(calls) * 30
            calls.append(request.full_url)
            date = "today" if offset < 60 else (start-timedelta(days=1)).date().isoformat()
            cards = ''.join(f'<div class="jobpost-cat-box"><h4>Software Developer</h4><p class="fs-13" data-temp="{date}"></p><a href="/jobseekers/job/{offset+i}">Job</a></div>' for i in range(30))
            html = cards + f'<a href="/jobseekers/jobsearch/{offset+30}?jobkeyword=developer">Next</a>'
            return io.BytesIO(html.encode())
        with patch.object(c, "open_url", side_effect=fetch):
            total = 0
            for _ in range(3):
                total += len(c.fetch())
                self.assertEqual(c.last_error, "")
                c.query_state = dict(c.next_query_state)
        self.assertEqual(total, 60)
        self.assertIn("/jobsearch/30?", calls[1])
        self.assertIn("/jobsearch/60?", calls[2])
        self.assertFalse(c.has_more)

    def test_source_cannot_silently_repeat_or_reverse_publication_pages(self):
        c = JobicyConnector()
        for rows, message in [([{ "id": "same", "pubDate": "today"}], "repeated"),
                              ([{ "id": "new", "pubDate": "today"}], "order changed")]:
            state = c.page_state()
            c.finish_page(state, ["same"], ["yesterday" if message == "order changed" else "today"], True, ordered=True)
            c.feed_state = dict(c.next_feed_state)
            with patch.object(c, "open_url", return_value=response({"success": True, "jobs": rows, "nextCursor": "next", "hasMore": True})):
                c.fetch()
            self.assertIn(message, c.last_error)
            c.feed_state = {}

    def test_freelancer_retains_date_bounds_on_later_offset(self):
        c = FreelancerConnector()
        start, end = scrape_date_window()
        c.query_state = {"window_start": start.date().isoformat(), "query": "react", "offset": 25}
        with patch.object(c, "open_url", return_value=response({"result": {"projects": [], "total_count": 25}})) as fetch:
            c.fetch("react")
        params = parse_qs(urlsplit(fetch.call_args.args[0].full_url).query)
        self.assertEqual(params["offset"], ["25"])
        self.assertEqual(params["from_time"], [str(int(start.timestamp()))])
        self.assertEqual(params["to_time"], [str(int(end.timestamp())-1)])

    def test_bossjob_old_first_page_does_not_hide_recent_second_page_or_claim_full_coverage(self):
        c = BossjobConnector()
        for page, date in [(1, "2020-01-01"), (2, "today")]:
            item = {"id": page, "job_title": "Software Developer", "published_at": date, "job_url": f"/job/{page}", "job_country": "Philippines"}
            with patch.object(c, "open_url", return_value=response({"code": 0, "data": {"jobs": [item], "total_pages": 500}})):
                jobs = c.fetch("developer")
            self.assertEqual(len(jobs), page-1)
            c.query_state = dict(c.next_query_state)
        self.assertFalse(c.has_more)
        self.assertIn("Coverage limited", c.coverage_warning)

    def test_jobspy_continues_when_first_raw_page_has_no_relevant_jobs(self):
        import pandas as pd
        from types import SimpleNamespace
        from src.connectors.jobspy_adapter import JobSpyAdapter
        c = JobSpyAdapter("Indeed", "indeed", 1)
        first = pd.DataFrame([{"job_url": f"https://example.com/{i}", "title": "Accountant", "date_posted": "today"} for i in range(35)])
        second = pd.DataFrame([{"job_url": "https://example.com/last", "title": "Software Developer", "date_posted": "today", "location": "Philippines"}])
        with patch.dict("sys.modules", {"jobspy": SimpleNamespace(scrape_jobs=lambda **kwargs: first)}):
            self.assertEqual(c.fetch("developer"), [])
        self.assertTrue(c.has_more)
        c.query_state = dict(c.next_query_state)
        with patch.dict("sys.modules", {"jobspy": SimpleNamespace(scrape_jobs=lambda **kwargs: second)}):
            self.assertEqual(len(c.fetch("developer")), 1)
        self.assertFalse(c.has_more)
