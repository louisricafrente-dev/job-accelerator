import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from email.message import EmailMessage
from src import gmail_hub as hub
from src.database import init_db, get_db_connection, set_user_setting, get_user_setting
from scripts.gmail_sync import parse_message, window_start, scan, run_request


class GmailHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'gmail_test.db')
        init_db(self.db)
        hub.init_hub(self.db)
        self.conn = get_db_connection(self.db)
        self.addCleanup(self.conn.close)
        self.conn.execute("""INSERT INTO jobs (id,dedup_hash,title,company,platform,tier,job_url,role_category,
            experience_level,status,pipeline_stage,notes,updated_at,applied_at) VALUES
            (1,'one','Android Developer','Acme','Indeed',1,'https://acme.com/jobs/1','Mobile','Junior / Entry',
            'applied','applied','Manual note','2026-10-01 00:00:00','2026-10-01 00:00:00'),
            (2,'two','Web Developer','Acme','Indeed',1,'https://acme.com/jobs/2','Web','Junior / Entry',
            'applied','applied','Other note','2026-10-01 00:00:00','2026-10-01 00:00:00')""")
        self.conn.commit()
        self.jobs = [dict(zip([c[0] for c in self.conn.execute('SELECT * FROM jobs').description], row))
                     for row in self.conn.execute('SELECT * FROM jobs')]
        self.now = time.time() - 20

    def message(self, mid='abc', subject='Acme Web Developer initial interview', **kw):
        return dict(id=mid, thread_id='aaa', subject=subject, sender='Recruiter <hr@acme.com>',
                    body_text=kw.pop('body_text', 'Please schedule an interview for Acme Web Developer.'),
                    received_at=kw.pop('received_at', self.now), trusted=kw.pop('trusted', True), **kw)

    def test_exact_role_not_first_company_and_ambiguous_company_skipped(self):
        job, _ = hub.match_job(self.message(), self.jobs)
        self.assertEqual(job['id'], 2)
        self.assertIsNone(hub.match_job(self.message(subject='Acme interview', body_text='Hello'), self.jobs)[0])
        self.assertIsNone(hub.match_job(self.message(body_text='Acme Android Developer and Acme Web Developer'), self.jobs)[0])

    def test_empty_sender_and_shared_ats_domain_do_not_match_first_job(self):
        self.assertIsNone(hub.match_job(self.message(subject='Other update', body_text='Hello'), self.jobs)[0])

    def test_body_and_rejection_precedence_and_conflict(self):
        self.assertEqual(hub.classify('Acme update', 'We are not moving forward after your final interview.')[1], 'rejected')
        self.assertEqual(hub.classify('Update', 'Please complete your coding assessment.')[1], 'tech_exam')
        self.assertIsNone(hub.classify('Not a job offer', 'Interview cancelled')[1])
        self.assertFalse(hub.classify('Job Alert: 15 new developer jobs', 'Recommended jobs for you')[2])
        self.assertIsNone(hub.classify('Update', 'Your final interview and technical assessment are next.')[1])
        self.assertEqual(hub.classify('Thanks', 'Thank you for applying\nOn Monday wrote:\nFinal interview')[1], 'applied')
        self.assertEqual(hub.classify('Thanks for your application', 'If you are among qualified candidates, we will schedule an interview.')[0], 'RECEIVED')

    def test_ingest_once_preserves_read_and_updates_only_exact_applied_job(self):
        self.assertTrue(hub.ingest(self.db, self.message(), self.jobs))
        self.assertEqual(hub.apply_pending(self.db), 1)
        self.assertEqual(self.conn.execute('SELECT pipeline_stage FROM jobs WHERE id=2').fetchone()[0], 'hr_screening')
        self.assertEqual(self.conn.execute('SELECT pipeline_stage FROM jobs WHERE id=1').fetchone()[0], 'applied')
        self.assertIn('Other note', self.conn.execute('SELECT notes FROM jobs WHERE id=2').fetchone()[0])
        hub.mark_read(self.db, 'abc', True)
        self.assertFalse(hub.ingest(self.db, self.message(), self.jobs))
        self.assertEqual(hub.detail(self.db, 'abc')['is_read'], 1)
        self.assertEqual(hub.apply_pending(self.db), 0)

    def test_action_items_in_hub_and_non_actionable_update_pipeline_silently(self):
        self.jobs[1]['status'] = 'saved'
        hub.ingest(self.db, self.message('a'), self.jobs)
        hub.ingest(self.db, self.message('b', trusted=False), self.jobs)
        hub.ingest(self.db, self.message('c', subject='Hello', body_text='Unknown employer'), self.jobs)
        hub.ingest(self.db, self.message('d', subject='Acme Android Developer update',
                                         body_text='We regret to inform you we are not moving forward with your Acme Android Developer application.'), self.jobs)
        self.assertEqual(hub.apply_pending(self.db), 1)
        self.assertEqual(self.conn.execute('SELECT pipeline_stage FROM jobs WHERE id=1').fetchone()[0], 'rejected')
        res = hub.messages(self.db)
        self.assertEqual(res['stats']['total'], 2)
        self.assertEqual(res['stats']['updated'], 1)
        self.assertEqual([m['id'] for m in res['messages']], ['b', 'a'])

    def test_regression_old_event_and_manual_changes_preserved(self):
        self.conn.execute("UPDATE jobs SET pipeline_stage='offer' WHERE id=2")
        self.conn.commit()
        hub.ingest(self.db, self.message(subject='Acme Web Developer application received', body_text='Thank you for applying'), self.jobs)
        self.assertEqual(hub.apply_pending(self.db), 0)
        self.assertEqual(self.conn.execute('SELECT pipeline_stage FROM jobs WHERE id=2').fetchone()[0], 'offer')
        self.conn.execute("UPDATE jobs SET pipeline_stage='applied',updated_at=CURRENT_TIMESTAMP WHERE id=2")
        self.conn.commit()
        hub.ingest(self.db, self.message('def'), self.jobs)
        self.assertEqual(hub.apply_pending(self.db), 0)

    def test_newest_event_wins_and_no_notes_overwrite(self):
        hub.ingest(self.db, self.message('a', subject='Acme Web Developer initial interview', received_at=self.now-100), self.jobs)
        hub.ingest(self.db, self.message('b', subject='Acme Web Developer final interview', body_text='Final interview invitation', received_at=self.now), self.jobs)
        self.assertEqual(hub.apply_pending(self.db), 1)
        self.assertEqual(self.conn.execute('SELECT pipeline_stage FROM jobs WHERE id=2').fetchone()[0], 'final_interview')

    def test_server_side_pagination_filters_and_detail(self):
        for i in range(5):
            hub.ingest(self.db, self.message(format(i+1, 'x')), self.jobs)
        hub.mark_read(self.db, '1', True)
        first = hub.messages(self.db, limit=2, read='unread', search='Acme')
        self.assertEqual(first['total'], 4)
        self.assertTrue(first['has_more'])
        self.assertNotIn('body_text', first['messages'][0])
        self.assertEqual(hub.messages(self.db, category='REJECTED')['total'], 0)
        self.assertEqual(hub.messages(self.db, search="%' OR 1=1 --")['total'], 0)

    def test_manual_daily_overlap_separate_requests_24h_and_cooldown(self):
        with patch('src.execution_dispatch.dispatch') as dispatch:
            manual = hub.request_scan(self.db, '7d')
            daily = hub.request_scan(self.db, '30d', digest=True)
            self.assertNotEqual(manual['scan']['id'], daily['scan']['id'])
            self.assertEqual(daily['scan']['window'], '24h')
            self.assertEqual(hub.request_scan(self.db, 'today')['status'], 'already_queued')
            self.assertEqual(dispatch.call_count, 2)
            record = manual['scan']
            record.update(status='complete', completed_at=time.time())
            set_user_setting(self.db, hub.SCAN_KEY, json.dumps(record))
            self.assertEqual(hub.request_scan(self.db)['status'], 'cooldown')
        with self.assertRaises(ValueError):
            hub.request_scan(self.db, '365d')

    def test_dispatch_failure_is_not_reported_as_success(self):
        with patch('src.execution_dispatch.dispatch', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                hub.request_scan(self.db)
        self.assertEqual(json.loads(get_user_setting(self.db, hub.SCAN_KEY))['status'], 'error')

    def test_scan_then_digest_once_and_failure_banner(self):
        request = dict(id='test', status='queued', window='24h', digest=True, requested_at=time.time())
        set_user_setting(self.db, hub.DAILY_KEY, json.dumps(request))
        order = []
        with patch('scripts.gmail_sync.scan', side_effect=lambda *a: order.append('scan') or {'imported': 1}), patch(
                'scripts.daily_notifier.send_daily_email', side_effect=lambda *a: order.append('digest') or {'success': True}):
            run_request(self.db, 'test')
            self.assertEqual(run_request(self.db, 'test')['status'], 'stale_request')
        self.assertEqual(order, ['scan', 'digest'])

    def test_failed_scan_sends_honest_digest_and_marks_failure(self):
        set_user_setting(self.db, hub.DAILY_KEY, json.dumps(dict(id='failure', status='queued', window='24h', digest=True)))
        with patch('scripts.gmail_sync.scan', side_effect=OSError('nope')), patch('scripts.daily_notifier.send_daily_email', return_value={'success': True}) as send:
            with self.assertRaises(RuntimeError):
                run_request(self.db, 'failure')
            send.assert_called_once()
        self.assertEqual(json.loads(get_user_setting(self.db, hub.DAILY_KEY))['status'], 'error')

    def test_window_is_rolling_24h_and_today_is_manila_midnight(self):
        now = datetime(2026, 10, 29, 2, tzinfo=timezone.utc).timestamp()
        self.assertEqual(window_start('24h', now), now - 86400)
        self.assertEqual(window_start('today', now), datetime(2026,10,28,16,tzinfo=timezone.utc).timestamp())

    def test_digest_includes_gmail_summary_and_never_claims_failed_scan_succeeded(self):
        from scripts.daily_notifier import generate_digest_data, build_html_content
        set_user_setting(self.db, hub.DAILY_KEY, json.dumps({'status': 'error'}))
        data = generate_digest_data(self.db)
        content = build_html_content(data, 'https://job-accelerator.vercel.app')
        self.assertIn('Mailbox scan did not complete', content)
        self.assertIn('?view=gmail', content)
        self.assertNotIn('Mailbox scan completed', content)

    def test_parse_full_mime_html_gmail_id_auth_and_unread(self):
        raw = EmailMessage()
        raw['From'] = 'Recruiter <hr@acme.com>'
        raw['Subject'] = 'Acme Web Developer'
        raw['Authentication-Results'] = 'mx.google.com; dmarc=pass header.from=acme.com'
        raw.set_content('<p>Initial interview <a href="https://acme.com/jobs/2">Details</a></p><script>alert(1)</script>', subtype='html')
        meta = b'1 (UID 7 X-GM-MSGID 255 X-GM-THRID 254 INTERNALDATE "29-Oct-2026 10:00:00 +0800" FLAGS () RFC822.SIZE 500)'
        message = parse_message(raw.as_bytes(), meta)
        self.assertEqual(message['id'], 'ff')
        self.assertIn('https://acme.com/jobs/2', message['body_text'])
        self.assertNotIn('alert(1)', message['body_text'])
        self.assertTrue(message['trusted'])
        self.assertFalse(message['is_read'])

    def test_scan_all_mail_more_than_50_and_second_pass_no_body_fetch(self):
        now = datetime(2026,10,29,3,tzinfo=timezone.utc).timestamp()
        raw = b'From: Recruiter <hr@acme.com>\r\nSubject: General correspondence\r\n\r\nHello'
        metadata = [f'{i} (UID {i} X-GM-MSGID {i} X-GM-THRID {i} INTERNALDATE "29-Oct-2026 10:00:00 +0800" FLAGS () RFC822.SIZE 100)'.encode() for i in range(1,66)]
        client = Mock()
        client.list.return_value = ('OK', [b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"'])
        client.select.return_value = ('OK', [b'65'])
        def uid(command, *args):
            if command == 'search':
                return 'OK', [b' '.join(str(i).encode() for i in range(1,66))]
            if 'BODY.PEEK' in args[-1]:
                return 'OK', [(b'data', raw), b')']
            return 'OK', metadata
        client.uid.side_effect = uid
        with patch.dict(os.environ, {'GMAIL_APP_PASSWORD': 'test'}):
            first = scan(self.db, now=now, client_factory=lambda *a,**kw: client)
            calls = client.uid.call_count
            second = scan(self.db, now=now, client_factory=lambda *a,**kw: client)
        self.assertEqual(first['imported'], 65)
        self.assertEqual(second['imported'], 0)
        self.assertEqual(client.uid.call_count-calls, 2)
        self.assertEqual(client.select.call_args.kwargs['readonly'], True)


class GmailApiTests(unittest.TestCase):
    from tests.test_local_worker import TestLocalWorker as _Fixture
    setUp = _Fixture.setUp
    call = _Fixture.call

    def test_admin_only_even_for_guest(self):
        self.assertEqual(self.call('/api/gmail/messages')[0], 403)
        from src.auth import create_session_token
        self.admin = create_session_token('guest', 'guest_test')
        self.assertEqual(self.call('/api/gmail/messages', admin=True)[0], 403)
        self.assertEqual(self.call('/api/gmail/scan', 'POST', {'window': '24h'}, admin=True)[0], 403)

    def test_queue_and_read_validation(self):
        with patch('src.execution_dispatch.dispatch'):
            code, value = self.call('/api/gmail/scan', 'POST', {'window': '7d'}, admin=True)
            self.assertEqual(code, 202)
            self.assertEqual(value['scan']['window'], '7d')
        self.assertEqual(self.call('/api/gmail/messages/abc/read', 'POST', {'is_read': 'yes'}, admin=True)[0], 400)
        self.assertEqual(self.call('/api/gmail/messages/abcdef', admin=True)[0], 404)

    def test_digest_cron_queues_24h_instead_of_scanning_on_vercel(self):
        with patch('src.execution_dispatch.dispatch') as dispatch, patch('scripts.gmail_sync.scan') as scanner:
            code, result = self.call('/api/notify/daily', admin=True)
        self.assertEqual(code, 200)
        self.assertEqual(result['scan']['window'], '24h')
        self.assertTrue(result['scan']['digest'])
        dispatch.assert_called_once()
        scanner.assert_not_called()
