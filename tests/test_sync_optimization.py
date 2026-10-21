import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.database import TursoConnection, init_db, insert_jobs, get_jobs, update_job_status
from src.models import Job


class TestSyncIngestionCache(unittest.TestCase):
    def test_cloud_entry_backfill_is_idempotent_and_preserves_tracking(self):
        job = self.job()
        job.title = "Developer II"
        job.description = "Fresh graduates are welcome. Minimum 3 years experience required."
        self.write([job])
        row = get_jobs(self.db)[0]
        update_job_status(self.db, row["id"], "saved", notes="Keep this")
        self.sql.execute("UPDATE jobs SET experience_level = 'Mid-Level'")
        self.sql.commit()
        with patch("src.database.is_turso_active", return_value=True), patch(
            "src.database.get_db_connection", side_effect=lambda *args: TursoConnection(self.client)
        ):
            init_db(self.db)
            writes = self.writes
            init_db(self.db)
            self.assertEqual(self.writes, writes)
        row = get_jobs(self.db)[0]
        self.assertEqual((row["experience_level"], row["status"], row["notes"]),
                         ("Junior / Entry", "saved", "Keep this"))

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = os.path.join(self.folder.name, "optimization_test.db")
        init_db(self.db)
        self.sql = sqlite3.connect(self.db)
        self.addCleanup(self.sql.close)
        self.reads = 0
        self.writes = 0
        self.fail_write = False
        owner = self

        class Client:
            def execute(self, query, params=None):
                if "FROM jobs ORDER BY id DESC" in query:
                    owner.reads += 1
                cur = owner.sql.execute(query, params or [])
                rows = cur.fetchall() if cur.description else []
                owner.sql.commit()
                return SimpleNamespace(columns=[c[0] for c in cur.description] if cur.description else [],
                                       rows=rows, rows_affected=max(0, cur.rowcount), last_insert_rowid=cur.lastrowid)

            def batch(self, statements):
                if owner.fail_write:
                    owner.fail_write = False
                    raise RuntimeError("mock database failure")
                owner.writes += len(statements)
                return [self.execute(query, params) for query, params in statements]

            def close(self):
                pass

        self.client = Client()
        self.cache = {}

    def job(self, board="LinkedIn", ident="1"):
        return Job("Junior Android Developer", "Example", "Remote", board, 1,
                   f"https://{board.lower()}.example/jobs/{ident}", date_posted="today")

    def write(self, jobs):
        with patch("src.database.get_db_connection", return_value=TursoConnection(self.client)):
            return insert_jobs(self.db, jobs, sync_cache=self.cache)

    def test_empty_fetch_does_not_open_a_database_connection(self):
        with patch("src.database.get_db_connection") as connection:
            self.assertEqual(insert_jobs(self.db, [], sync_cache=self.cache), (0, 0))
        connection.assert_not_called()

    def test_twenty_searches_reuse_one_catalog_without_merging_distinct_ids(self):
        for index in range(20):
            self.assertEqual(self.write([self.job(ident=str(index))]), (1, 0))
        self.assertEqual(self.reads, 1)
        self.assertEqual(len(get_jobs(self.db)), 20)
        self.assertEqual(self.write([self.job(ident="0")]), (0, 1))
        self.assertEqual(len(get_jobs(self.db)), 20)

    def test_cached_catalog_preserves_cross_board_sources_and_live_applied_status(self):
        self.write([self.job()])
        row = get_jobs(self.db)[0]
        update_job_status(self.db, row["id"], "applied", notes="Verified application")
        self.assertEqual(self.write([self.job("Indeed")]), (0, 1))
        self.write([self.job()])
        rows = get_jobs(self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "applied")
        self.assertEqual(rows[0]["notes"], "Verified application")
        self.assertEqual(self.reads, 1)

    def test_failed_write_discards_cache_before_retry(self):
        self.write([self.job()])
        self.fail_write = True
        with self.assertRaisesRegex(RuntimeError, "mock database failure"):
            self.write([self.job(ident="2")])
        self.assertEqual(self.cache, {})
        self.assertEqual(self.write([self.job(ident="2")]), (1, 0))
        self.assertEqual(self.reads, 2)
        self.assertEqual(len(get_jobs(self.db)), 2)

    def test_overlapping_keywords_do_not_rewrite_unchanged_jobs(self):
        self.write([self.job()])
        for _ in range(20):
            self.assertEqual(self.write([self.job()]), (0, 1))
        self.assertEqual(self.writes, 1)
        self.assertEqual(self.reads, 1)

    def test_changed_salary_and_new_source_still_write(self):
        self.write([self.job()])
        changed = self.job()
        changed.salary = "35000"
        self.assertEqual(self.write([changed]), (0, 1))
        self.assertEqual(get_jobs(self.db)[0]["salary"], "35000")
        self.assertEqual(self.write([self.job("Indeed")]), (0, 1))
        self.assertEqual(self.writes, 3)

    def test_unchanged_fetch_preserves_job_timestamp_and_live_archive(self):
        self.write([self.job()])
        row = get_jobs(self.db)[0]
        update_job_status(self.db, row["id"], "ignored", notes="Candidate archived")
        self.sql.execute("UPDATE jobs SET updated_at = '2020-01-01 00:00:00'")
        self.sql.commit()
        self.assertEqual(self.write([self.job()]), (0, 1))
        row = self.sql.execute("SELECT status, notes, updated_at FROM jobs").fetchone()
        self.assertEqual(tuple(row),
                         ("ignored", "Candidate archived", "2020-01-01 00:00:00"))

    def test_description_is_saved_and_short_preview_cannot_replace_full_text(self):
        job = self.job()
        job.description = "Full requirements and responsibilities for this developer role."
        self.write([job])
        preview = self.job()
        preview.description = "Short preview"
        self.write([preview])
        self.assertEqual(get_jobs(self.db)[0]["description"], job.description)
        self.assertEqual(self.writes, 1)

    def test_description_enrichment_preserves_saved_status_and_notes(self):
        self.write([self.job()])
        row = get_jobs(self.db)[0]
        update_job_status(self.db, row["id"], "saved", notes="Keep this application")
        job = self.job()
        job.description = "Requirements from employer"
        self.write([job])
        row = get_jobs(self.db)[0]
        self.assertEqual(row["description"], job.description)
        self.assertEqual(row["status"], "saved")
        self.assertEqual(row["notes"], "Keep this application")

    def test_description_html_is_text_and_scripts_are_removed(self):
        job = Job("Developer", "Example", "Remote", "Example", 1, "https://example.com", description="<p>Kotlin</p><script>alert(1)</script><p>Remote</p>")
        self.assertEqual(job.description, "Kotlin\nRemote")

    def test_cloud_description_migration_preserves_existing_jobs_and_is_idempotent(self):
        insert_jobs(self.db, [self.job()])
        self.sql.execute("ALTER TABLE jobs DROP COLUMN description")
        self.sql.commit()
        with patch("src.database.is_turso_active", return_value=True), patch("src.database.get_db_connection", side_effect=lambda path: TursoConnection(self.client)):
            init_db(self.db)
            init_db(self.db)
        self.assertEqual(len(get_jobs(self.db)), 1)
        self.assertEqual(get_jobs(self.db)[0]["description"], "")
