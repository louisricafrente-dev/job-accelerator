import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from src.aggregator import Aggregator
from src.connectors.base import BaseConnector
from src.connectors.ph_jobs import OnlineJobsConnector, JobStreetCatalogConnector
from src.connectors.remote_feed import FreelancerConnector
from src.connectors.video_editor import VideoEditorConnector, video_connectors
from src.database import init_db, get_jobs, insert_jobs, update_job_status
from src.models import Job, MANILA, scrape_date_window
from src.video_editor import video_fit, collectable_job, attention_check

DESCRIPTION = ('Edit simple short-form TikTok gaming tutorials using CapCut. We provide footage, scripts and templates. '
               'Trim clips, add basic captions, music and transitions. Send a portfolio and agree the workload and deadline before starting.')


def job(days=0, platform="OnlineJobs.ph", category="Video Editor", title="CapCut Video Editor"):
    date = (datetime.now(MANILA).date() - timedelta(days=days)).isoformat()
    return Job(title, "Example", "Philippines (Remote)", platform, 1, f"https://example.org/{days}/{category}",
               description=DESCRIPTION, date_posted=date, role_category=category)


class TestVideoRules(unittest.TestCase):
    def test_exact_seven_dates_and_four_sources_only(self):
        for days in range(7):
            self.assertTrue(collectable_job(job(days)), days)
        for days in (-1, 7, 30):
            self.assertFalse(collectable_job(job(days)), days)
        self.assertFalse(collectable_job(job(platform="Upwork")))
        self.assertFalse(collectable_job(job(category="Web/Software Dev")))
        self.assertFalse(collectable_job(job(4, category="Web/Software Dev", title="Software Developer")))
        for date in ("", "recently", "garbage"):
            candidate = job(); candidate.date_posted = date
            self.assertFalse(collectable_job(candidate))

    def test_basic_matches_optional_tools_and_advanced_required_duties(self):
        self.assertEqual(video_fit("Gaming Video Editor", DESCRIPTION), "")
        self.assertEqual(video_fit("Video Editor", DESCRIPTION + '\nAfter Effects is optional.'), "")
        self.assertEqual(video_fit("Video Editor", DESCRIPTION + '\nUse CapCut or Premiere Pro.'), "")
        self.assertEqual(video_fit("Video Editor", DESCRIPTION + '\nNo heavy VFX or motion graphics.'), "")
        for extra in ('Advanced video editing required.', 'Must know After Effects.', 'CapCut and Premiere Pro required.',
                      'Create motion graphics.', 'Spanish subtitles required.', 'Canva required.', 'Minimum 3 years experience.',
                      "2+ years' experience editing videos.", 'Write captions and publish posts.', 'Reply to comments and DMs.',
                      'Plan and manage a regular content calendar.', 'Send first-touch outreach messages.'):
            self.assertTrue(video_fit("Video Editor", DESCRIPTION + '\n' + extra), extra)
        self.assertTrue(video_fit("Senior Video Editor", DESCRIPTION))
        self.assertTrue(video_fit("Virtual Assistant", DESCRIPTION))
        self.assertTrue(video_fit("Video Editor", "Use CapCut... See More"))
        self.assertTrue(attention_check('Begin your proposal with CHECKED'))
        self.assertTrue(attention_check('Start your message with AESTHETIC'))

    def test_factory_does_not_mutate_standard_sources(self):
        boards = video_connectors()
        self.assertEqual({b.source.platform for b in boards}, {"OnlineJobs.ph", "Freelancer", "Indeed", "JobStreet"})
        self.assertTrue(all(b.source.window_days == 7 for b in boards))
        self.assertEqual(OnlineJobsConnector().window_days, 2)
        self.assertFalse(OnlineJobsConnector().video_editor_mode)

    def test_dates_and_categories_both_sync_paths_preserve_history(self):
        class Board(BaseConnector):
            platform = "Video test"
            def fetch(self, **kwargs):
                return [job(6), job(7), job(-1), job(4, category="Web/Software Dev", title="Software Developer")]
        for budget in (None, 5):
            with tempfile.TemporaryDirectory() as directory:
                db = os.path.join(directory, "jobs.db"); init_db(db)
                history = job(30, category="Web/Software Dev", title="Software Developer"); history.status = "saved"
                insert_jobs(db, [history])
                update_job_status(db, get_jobs(db)[0]['id'], 'saved')
                result = Aggregator(db, [Board()]).run_sync(["developer"], budget_seconds=budget)
                self.assertEqual(result['added'], 1)
                rows = get_jobs(db, role_category="Video Editor")
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['platform'], 'OnlineJobs.ph')
                self.assertEqual(len(get_jobs(db, status="saved")), 1)
                self.assertEqual(len(get_jobs(db, role_category="Data/AI/ML")), 0)

    def test_video_category_does_not_leak_to_ai_or_software(self):
        with tempfile.TemporaryDirectory() as directory:
            db = os.path.join(directory, 'jobs.db'); init_db(db)
            candidate = job(title='AI Video Editor')
            insert_jobs(db, [candidate])
            self.assertEqual(len(get_jobs(db, role_category='Video Editor')), 1)
            for family in ('Data/AI/ML', 'Web/Software Dev', 'Virtual Assistant', 'QA / Testing'):
                self.assertEqual(get_jobs(db, role_category=family), [], family)


class TestVideoSources(unittest.TestCase):
    def test_resume_and_failed_ingestion_keep_video_term_and_page(self):
        from tests.test_sync_batches import Clock
        from src.database import get_user_setting
        from src.sync_batches import PROGRESS_KEY
        clock = Clock()
        source = OnlineJobsConnector(); board = VideoEditorConnector(source)
        calls = []
        def fetch(query='', location=''):
            state = source.page_state(query); page = state.get('offset', 0)
            calls.append((query, page)); clock.value += 2
            source.last_error = ''
            source.finish_page(state, [query+str(page)], ['today'], page == 0)
            state['offset'] = page + 1
            return [job()]
        with tempfile.TemporaryDirectory() as directory, patch.object(source, 'fetch', side_effect=fetch), patch.object(board, '_description', return_value=DESCRIPTION), patch('src.sync_batches.time.monotonic', clock.monotonic), patch('src.sync_batches.time.time', clock.time), patch('src.sync_batches.QUERY_DELAY_SECONDS', 0):
            db = os.path.join(directory, 'jobs.db'); init_db(db)
            aggregator = Aggregator(db, [board])
            aggregator.run_sync(['developer'], budget_seconds=1, cycle_id='video')
            saved = json.loads(get_user_setting(db, PROGRESS_KEY))['boards'][board.platform]['feed_state']
            self.assertEqual(saved['source_state']['offset'], 1)
            with patch('src.sync_batches.insert_jobs', side_effect=RuntimeError('write failed')):
                aggregator.run_sync(['developer'], budget_seconds=1, cycle_id='video')
            self.assertEqual(json.loads(get_user_setting(db, PROGRESS_KEY))['boards'][board.platform]['feed_state'], saved)
            clock.value += 901
            result = aggregator.run_sync(['developer'], budget_seconds=100, cycle_id='video', resume=True)
            self.assertEqual(calls[:3], [('CapCut', 0), ('CapCut', 1), ('CapCut', 1)])
            self.assertFalse(result['progress']['unfinished'])

    def test_olj_full_details_and_continuation_are_separate_from_legacy(self):
        source = OnlineJobsConnector(); board = VideoEditorConnector(source)
        day = (datetime.now(MANILA).date() - timedelta(days=6)).isoformat()
        search = f'<div class="jobpost-cat-box"><h4>Video Editor</h4><p class="fs-13" data-temp="{day}"></p><a href="/jobseekers/job/123">Job</a><div class="desc">CapCut</div></div><a href="/jobseekers/jobsearch/1">Next</a>'
        detail = f'<p id="job-description">{DESCRIPTION}</p>'
        def fetch(request, **kwargs):
            return io.BytesIO((detail if '/job/123' in request.full_url else search).encode())
        with patch.object(source, "open_url", side_effect=fetch):
            rows = board.fetch()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].description, DESCRIPTION)
        self.assertTrue(board.has_more)
        self.assertEqual(board.next_feed_state['query_index'], 0)
        self.assertEqual(board.next_feed_state['source_state']['offset'], 1)

    def test_missing_full_description_is_skipped_with_warning(self):
        source = OnlineJobsConnector(); board = VideoEditorConnector(source)
        with patch.object(source, "fetch", return_value=[job()]), patch.object(board, "_description", return_value=""):
            source.last_error = ""; source.has_more = False
            self.assertEqual(board.fetch(), [])
        self.assertIn('full descriptions', board.coverage_warning)
        self.assertEqual(board.next_feed_state['query_index'], 1)

    def test_request_bounds_freelancer_and_jobstreet(self):
        source = FreelancerConnector(); VideoEditorConnector(source)
        response = io.BytesIO(json.dumps({'result': {'projects': [], 'total_count': 0}}).encode())
        with patch.object(source, 'open_url', return_value=response) as fetch:
            source.fetch('CapCut')
        params = parse_qs(urlsplit(fetch.call_args.args[0].full_url).query)
        self.assertEqual(params['full_description'], ['true'])
        start, end = scrape_date_window(days=7)
        self.assertEqual(int(params['from_time'][0]), int(start.timestamp()))
        self.assertEqual(int(params['to_time'][0]), int(end.timestamp())-1)
        source = JobStreetCatalogConnector(); board = VideoEditorConnector(source)
        with patch.object(source, 'get_url', return_value=MagicMock(status_code=200, text='{"data":[],"totalCount":0}')) as fetch:
            board.fetch()
        params = parse_qs(urlsplit(fetch.call_args.args[0]).query)
        self.assertEqual(params['daterange'], ['7'])
        self.assertEqual(params['keywords'], ['CapCut'])

    def test_indeed_uses_seven_day_request_and_full_description(self):
        import pandas as pd
        from types import SimpleNamespace
        from src.connectors.jobspy_adapter import JobSpyAdapter
        source = JobSpyAdapter("Indeed", "indeed", 1); board = VideoEditorConnector(source)
        candidate = job(6, platform='Indeed')
        scrape = MagicMock(return_value=pd.DataFrame([dict(title=candidate.title, company='Example', location='Philippines',
                    job_url=candidate.job_url, date_posted=candidate.date_posted, description=DESCRIPTION)]))
        with patch.dict('sys.modules', {'jobspy': SimpleNamespace(scrape_jobs=scrape)}):
            rows = board.fetch()
        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(scrape.call_args.kwargs['hours_old'], 144)
        self.assertLessEqual(scrape.call_args.kwargs['hours_old'], 168)
