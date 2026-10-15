import io
import csv
import json
import sqlite3
import os
from typing import Any, Dict, List, Optional, Tuple
from src.models import Job, normalize_date

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_hash TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    platform TEXT NOT NULL,
    tier INTEGER NOT NULL,
    job_url TEXT NOT NULL,
    salary TEXT,
    role_category TEXT NOT NULL,
    experience_level TEXT NOT NULL,
    date_posted TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    pipeline_stage TEXT DEFAULT 'applied',
    follow_up_date TEXT,
    notes TEXT,
    sources TEXT DEFAULT '[]',
    applied_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_level ON jobs(experience_level);
CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(role_category);
CREATE INDEX IF NOT EXISTS idx_jobs_tier ON jobs(tier);
"""

try:
    import libsql_client
    HAS_LIBSQL = True
except ImportError:
    libsql_client = None
    HAS_LIBSQL = False

class TursoRow:
    def __init__(self, cols, vals):
        self._dict = dict(zip(cols, vals))
        self._vals = vals

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        return self._dict[k]

    def get(self, k, default=None):
        return self._dict.get(k, default)

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    def items(self):
        return self._dict.items()

    def __iter__(self):
        return iter(self._dict.items())

    def __contains__(self, k):
        return k in self._dict

    def __len__(self):
        return len(self._dict)

    def __repr__(self):
        return f"<TursoRow {self._dict}>"

class TursoCursor:
    def __init__(self, client):
        self._client = client
        self._last_rs = None
        self._row_idx = 0
        self.rowcount = -1
        self.lastrowid = None
        self.description = None

    def execute(self, sql, params=None):
        if params is None:
            self._last_rs = self._client.execute(sql)
        else:
            clean_params = [p if p is not None else None for p in list(params)]
            self._last_rs = self._client.execute(sql, clean_params)
        self._row_idx = 0
        self.rowcount = getattr(self._last_rs, "rows_affected", 0) if self._last_rs is not None else 0
        self.lastrowid = getattr(self._last_rs, "last_insert_rowid", None) if self._last_rs is not None else None
        self.description = (
            [(c, None, None, None, None, None, None) for c in self._last_rs.columns]
            if self._last_rs is not None and hasattr(self._last_rs, "columns") and self._last_rs.columns
            else None
        )
        return self

    def executemany(self, sql, seq_of_params):
        stmts = [(sql, list(p)) for p in seq_of_params]
        if stmts:
            self._client.batch(stmts)
            self.rowcount = len(stmts)
        else:
            self.rowcount = 0
        return self

    def fetchone(self):
        if self._last_rs is None or self._row_idx >= len(self._last_rs.rows):
            return None
        r = self._last_rs.rows[self._row_idx]
        self._row_idx += 1
        return TursoRow(self._last_rs.columns, r)

    def fetchall(self):
        if self._last_rs is None:
            return []
        rows = [TursoRow(self._last_rs.columns, r) for r in self._last_rs.rows[self._row_idx:]]
        self._row_idx = len(self._last_rs.rows)
        return rows

class TursoConnection:
    def __init__(self, client):
        self._client = client
        self.row_factory = None

    def cursor(self):
        return TursoCursor(self._client)

    def execute(self, sql, params=None):
        cur = self.cursor()
        return cur.execute(sql, params)

    def executescript(self, script):
        for stmt in script.strip().split(";"):
            s = stmt.strip()
            if s:
                try:
                    self._client.execute(s)
                except Exception:
                    pass

    def commit(self):
        pass

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass

def get_turso_url() -> str:
    url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    if not url and os.environ.get("VERCEL"):
        url = "https://job-accelerator-rhettrina.aws-ap-northeast-1.turso.io"
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://")
    return url

def get_turso_token() -> str:
    token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if not token and os.environ.get("VERCEL"):
        token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTIwNDIzNjcsImlkIjoiMDFhMTNlMGMtNGQwMS03ZTllLTg4ZTAtMmMxYTNjMDhkZGQ1Iiwia2lkIjoidll0ZTBSNXdnZ2MyZ0VrRTFuREpfMUNHZTBwbGdEbVVna0w1dGJoQ2EzZyIsInJpZCI6IjZjOTcxNDFlLWY1ZGQtNGJmNS04YjQzLTAyNjY4MmNlNTdlYyJ9.veXC15vhglAH04ASngJAwPiWs7pTJYxQ1FvYn6EtzZAvsVUg0cppyFdbah-XcitFmFgwoXJ1YC1z8YUT2KTPDA"
    return token

def is_turso_active(db_path: str = "") -> bool:
    url = get_turso_url()
    token = get_turso_token()
    if not url or not token:
        return False
    norm = (db_path or "").replace("\\", "/").lower()
    # Isolate guest sandboxes to local SQLite
    if "guest" in norm:
        return False
    # Unit tests targeting temp files (e.g. server_test.db) run locally
    if "_test.db" in norm or "test_" in norm:
        return False
    return True

def get_db_connection(db_path: str = "data/jobs.db", timeout: float = 25.0):
    if is_turso_active(db_path) and HAS_LIBSQL:
        url = get_turso_url()
        token = get_turso_token()
        client = libsql_client.create_client_sync(url, auth_token=token)
        return TursoConnection(client)
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute("PRAGMA busy_timeout = 25000;")
    return conn

def init_db(db_path: str = "data/jobs.db") -> None:
    if is_turso_active(db_path):
        return  # Turso cloud schema is managed and persisted
    parent = os.path.dirname(db_path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    conn = get_db_connection(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executescript(SCHEMA)

        # Safe migration for existing DB files
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(jobs);")
        existing_cols = {col[1] for col in cursor.fetchall()}
        if "pipeline_stage" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN pipeline_stage TEXT DEFAULT 'applied';")
        if "follow_up_date" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN follow_up_date TEXT;")
        if "sources" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN sources TEXT DEFAULT '[]';")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_stage ON jobs(pipeline_stage);")

        # Safe backfill for legacy unclassified junior/entry opportunities
        try:
            from src.classifier import classify_experience_level
            cursor.execute("SELECT id, title, experience_level FROM jobs WHERE experience_level != 'Junior / Entry';")
            legacy_rows = cursor.fetchall()
            to_update = []
            for row in legacy_rows:
                jid, title, old_lvl = row[0], row[1], row[2]
                new_lvl = classify_experience_level(title)
                if new_lvl == "Junior / Entry" and old_lvl != "Junior / Entry":
                    to_update.append((new_lvl, jid))
            if to_update:
                cursor.executemany("UPDATE jobs SET experience_level = ? WHERE id = ?;", to_update)
        except Exception:
            pass

        conn.commit()
    finally:
        conn.close()

def insert_jobs(db_path: str, jobs: List[Job]) -> Tuple[int, int]:
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    added = 0
    skipped = 0
    try:
        cursor = conn.cursor()
        for job in jobs:
            norm_date = normalize_date(job.date_posted) if job.date_posted else ""
            canonical_co = job.company.strip().lower()
            canonical_title = job.title.strip().lower()

            cursor.execute(
                """
                SELECT id, platform, job_url, salary, date_posted, sources, status
                FROM jobs
                WHERE lower(trim(company)) = ? AND lower(trim(title)) = ?
                ORDER BY id DESC
                LIMIT 1;
                """,
                (canonical_co, canonical_title),
            )
            existing = cursor.fetchone()
            if existing:
                # Aggregate source platform and link
                try:
                    sources_list = json.loads(existing["sources"]) if existing["sources"] else []
                except Exception:
                    sources_list = []
                if not sources_list:
                    sources_list = [{"platform": existing["platform"], "url": existing["job_url"]}]

                already_present = any(
                    s.get("platform", "").lower() == job.platform.lower() or s.get("url") == job.job_url
                    for s in sources_list
                )
                if not already_present:
                    sources_list.append({"platform": job.platform, "url": job.job_url})

                new_salary = job.salary or existing["salary"] or ""

                # Check if incoming listing has a newer date or fresh date vs empty
                existing_date = existing["date_posted"] or ""
                if norm_date and existing_date:
                    is_newer_date = norm_date > existing_date
                    new_date = norm_date if is_newer_date else existing_date
                else:
                    is_newer_date = bool(norm_date and not existing_date)
                    new_date = norm_date or existing_date

                existing_status = existing["status"]
                is_new_source = not already_present
                is_new_post = is_newer_date or is_new_source

                # Re-post / Archive handling:
                # 1. If previously archived ('ignored') and a new post arrives (newer date or new platform),
                #    bring it out again to Inbox ('new') so the candidate never misses refreshed opportunities!
                # 2. If 'new', keep in Inbox with updated date and sources.
                # 3. If 'applied' or 'saved', preserve applicant's tracking state.
                if existing_status == "ignored" and is_new_post:
                    target_status = "new"
                    added += 1
                else:
                    target_status = existing_status
                    skipped += 1

                cursor.execute(
                    """
                    UPDATE jobs
                    SET sources = ?, salary = ?, date_posted = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (json.dumps(sources_list), new_salary, new_date, target_status, existing["id"]),
                )
            else:
                initial_sources = json.dumps([{"platform": job.platform, "url": job.job_url}])
                cursor.execute(
                    """
                    INSERT INTO jobs (dedup_hash, title, company, location, platform, tier, job_url, salary, role_category, experience_level, date_posted, status, sources)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                    ON CONFLICT(dedup_hash) DO NOTHING;
                    """,
                    (
                        job.dedup_hash,
                        job.title,
                        job.company,
                        job.location,
                        job.platform,
                        job.tier,
                        job.job_url,
                        job.salary,
                        job.role_category,
                        job.experience_level,
                        norm_date,
                        initial_sources,
                    ),
                )
                if cursor.rowcount > 0:
                    added += 1
                else:
                    skipped += 1
        conn.commit()
    finally:
        conn.close()
    return added, skipped

def get_jobs(
    db_path: str,
    status: Optional[str] = None,
    role_category: Optional[str] = None,
    experience_level: Optional[str] = None,
    tier: Optional[int] = None,
    search: Optional[str] = None,
    date_filter: Optional[str] = None,
    has_salary: bool = False,
    remote_only: bool = False,
    hide_senior: bool = False,
    include_va: bool = False,
    platform: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        clauses = []
        params: List[Any] = []

        if status:
            if "," in status:
                statuses = [s.strip() for s in status.split(",") if s.strip()]
                placeholders = ",".join(["?"] * len(statuses))
                clauses.append(f"status IN ({placeholders})")
                params.extend(statuses)
            else:
                clauses.append("status = ?")
                params.append(status)
        if role_category and role_category != "All":
            rc = role_category.strip()
            if rc.upper() in ("VIRTUAL ASSISTANT", "VA", "VA (WITH TRAINING)"):
                va_sub = [
                    "role_category = 'Virtual Assistant'",
                    "lower(title) LIKE '%virtual assistant%'",
                    "lower(title) LIKE '%administrative assistant%'",
                    "lower(title) LIKE '%executive assistant%'",
                    "lower(title) LIKE '%remote assistant%'",
                    "lower(title) LIKE '%cyberbacker%'",
                    "lower(title) LIKE '%athena%'",
                    "lower(title) LIKE '%virtudesk%'",
                    "lower(title) LIKE '%pineapple staffing%'"
                ]
                clauses.append(f"({' OR '.join(va_sub)})")
            elif rc == "Frontend":
                frontend_pats = ["%frontend%", "%front-end%", "%react%", "%vue%", "%angular%", "%ui dev%", "%web designer%", "%svelte%"]
                sub_clauses = ["(role_category = 'Frontend' OR role_category = 'Both')"]
                for pat in frontend_pats:
                    sub_clauses.append("lower(title) LIKE ?")
                    params.append(pat)
                clauses.append(f"({' OR '.join(sub_clauses)})")
            elif rc == "Backend":
                backend_pats = ["%backend%", "%back-end%", "%python%", "%node%", "%django%", "%fastapi%", "%golang%", "%go developer%", "%java%", "%.net%", "%c#%", "%php%", "%laravel%", "%ruby%", "%api developer%"]
                sub_clauses = ["(role_category = 'Backend' OR role_category = 'Both')"]
                for pat in backend_pats:
                    sub_clauses.append("lower(title) LIKE ?")
                    params.append(pat)
                clauses.append(f"({' OR '.join(sub_clauses)})")
            elif rc == "Full Stack":
                fs_pats = ["%full stack%", "%fullstack%", "%full-stack%"]
                sub_clauses = ["(role_category = 'Full Stack' OR role_category = 'Both')"]
                for pat in fs_pats:
                    sub_clauses.append("lower(title) LIKE ?")
                    params.append(pat)
                clauses.append(f"({' OR '.join(sub_clauses)})")
            elif rc == "Mobile":
                mob_pats = ["%mobile%", "%android%", "%ios%", "%flutter%", "%react native%", "%swift%", "%kotlin%"]
                sub_clauses = ["(role_category = 'Mobile' OR role_category = 'Both')"]
                for pat in mob_pats:
                    sub_clauses.append("lower(title) LIKE ?")
                    params.append(pat)
                clauses.append(f"({' OR '.join(sub_clauses)})")
            elif rc in ("DevOps / Cloud", "DevOps", "Cloud"):
                devops_pats = ["%devops%", "%cloud%", "%aws%", "%azure%", "%gcp%", "%sre%", "%site reliability%", "%kubernetes%", "%docker%", "%infrastructure%"]
                sub_clauses = ["(role_category = 'DevOps / Cloud' OR role_category = 'Both')"]
                for pat in devops_pats:
                    sub_clauses.append("lower(title) LIKE ?")
                    params.append(pat)
                clauses.append(f"({' OR '.join(sub_clauses)})")
            elif rc in ("QA / Testing", "QA", "Testing"):
                qa_pats = ["%qa%", "%quality assurance%", "%tester%", "%testing%", "%sdet%", "%automation test%"]
                sub_clauses = ["(role_category = 'QA / Testing' OR role_category = 'Both')"]
                for pat in qa_pats:
                    sub_clauses.append("lower(title) LIKE ?")
                    params.append(pat)
                clauses.append(f"({' OR '.join(sub_clauses)})")
            elif rc in ("Data/AI/ML", "Data & AI"):
                data_pats = ["%data%", "%ai%", "%machine learning%", "%analytics%", "%nlp%", "%deep learning%", "%bi developer%"]
                sub_clauses = ["(role_category = 'Data/AI/ML' OR role_category = 'Both')"]
                for pat in data_pats:
                    sub_clauses.append("lower(title) LIKE ?")
                    params.append(pat)
                clauses.append(f"({' OR '.join(sub_clauses)})")
            elif rc == "Web/Software Dev":
                clauses.append("(role_category = 'Web/Software Dev' OR role_category = 'Both' OR (role_category != 'Data/AI/ML' AND role_category != 'Virtual Assistant'))")
            else:
                clauses.append("(role_category = ? OR role_category = 'Both' OR lower(title) LIKE ?)")
                params.extend([rc, f"%{rc.lower()}%"])

        if not include_va and role_category not in ("Virtual Assistant", "VA", "VA (With Training)"):
            clauses.append("(role_category != 'Virtual Assistant' AND lower(title) NOT LIKE '%virtual assistant%' AND lower(title) NOT LIKE '%administrative assistant%')")
        if experience_level and experience_level != "All":
            raw_levels = [l.strip() for l in experience_level.split(",") if l.strip() and l.strip() != "All"]
            if raw_levels:
                level_clauses = []
                for el in raw_levels:
                    if el in ("Junior / Entry", "Junior", "Entry", "Junior / Entry Level"):
                        senior_guard = "lower(title) NOT LIKE '%senior%' AND lower(title) NOT LIKE '%sr%' AND lower(title) NOT LIKE '%lead%' AND lower(title) NOT LIKE '%director%' AND lower(title) NOT LIKE '%manager%'"
                        roman_guard = "lower(title) NOT LIKE '%engineer ii%' AND lower(title) NOT LIKE '%developer ii%' AND lower(title) NOT LIKE '%programmer ii%'"
                        jr_sub = [
                            "experience_level = 'Junior / Entry'",
                            f"(lower(title) LIKE '%junior%' AND {senior_guard})",
                            f"(lower(title) LIKE '%jr%' AND lower(title) NOT LIKE '%jr-%' AND lower(title) NOT LIKE '%project%' AND {senior_guard})",
                            f"(lower(title) LIKE '%entry level%' OR lower(title) LIKE '%entry-level%')",
                            f"(lower(title) LIKE '%associate%' AND (lower(title) LIKE '%developer%' OR lower(title) LIKE '%engineer%' OR lower(title) LIKE '%software%' OR lower(title) LIKE '%qa%' OR lower(title) LIKE '%web%') AND {senior_guard})",
                            f"(lower(title) LIKE '%intern%' AND lower(title) NOT LIKE '%internal%' AND lower(title) NOT LIKE '%international%' AND {senior_guard})",
                            f"(lower(title) LIKE '%trainee%' AND {senior_guard})",
                            f"(lower(title) LIKE '%apprentice%' AND {senior_guard})",
                            f"(lower(title) LIKE '%fresh grad%' AND {senior_guard})",
                            f"(lower(title) LIKE '%early career%' AND {senior_guard})",
                            f"(lower(title) LIKE '%ojt%' AND {senior_guard})",
                            f"(lower(title) LIKE '%engineer i%' AND {senior_guard} AND {roman_guard})",
                            f"(lower(title) LIKE '%developer i%' AND {senior_guard} AND {roman_guard})",
                            f"(lower(title) LIKE '%programmer i%' AND {senior_guard} AND {roman_guard})",
                            f"(lower(title) LIKE '%0-1 year%' AND {senior_guard})",
                            f"(lower(title) LIKE '%0-2 year%' AND {senior_guard})"
                        ]
                        level_clauses.append(f"({' OR '.join(jr_sub)})")
                    elif el in ("Senior / Lead", "Senior", "Lead"):
                        level_clauses.append("(experience_level = 'Senior / Lead' OR lower(title) LIKE '%senior%' OR lower(title) LIKE '%sr%' OR lower(title) LIKE '%lead%' OR lower(title) LIKE '%principal%')")
                    elif el in ("Mid-Level", "Mid"):
                        level_clauses.append("(experience_level = 'Mid-Level' OR lower(title) LIKE '%engineer ii%' OR lower(title) LIKE '%developer ii%')")
                    else:
                        level_clauses.append("experience_level = ?")
                        params.append(el)
                if level_clauses:
                    clauses.append(f"({' OR '.join(level_clauses)})")

        if hide_senior:
            clauses.append("(experience_level != 'Senior / Lead' AND lower(title) NOT LIKE '%senior%' AND lower(title) NOT LIKE '%sr%' AND lower(title) NOT LIKE '%lead%' AND lower(title) NOT LIKE '%principal%' AND lower(title) NOT LIKE '%staff%' AND lower(title) NOT LIKE '%architect%')")
        if tier:
            clauses.append("tier = ?")
            params.append(tier)
        if platform and platform != "All":
            p_clean = platform.strip()
            clauses.append("(platform = ? OR sources LIKE ?)")
            params.extend([p_clean, f'%"{p_clean}"%'])
        if has_salary:
            clauses.append("(salary IS NOT NULL AND salary != '')")
        if remote_only:
            clauses.append("(location LIKE '%remote%' OR location LIKE '%wfh%' OR location LIKE '%worldwide%')")
        if search:
            words = [w.strip() for w in search.strip().split() if w.strip()]
            for word in words:
                query_param = f"%{word}%"
                clauses.append("(title LIKE ? OR company LIKE ? OR location LIKE ? OR role_category LIKE ? OR experience_level LIKE ?)")
                params.extend([query_param, query_param, query_param, query_param, query_param])

        if date_filter and date_filter != "all":
            # If querying applied jobs, filter by when the user actually applied (COALESCE(applied_at, updated_at, date_posted))
            if status == "applied" or (status and "applied" in status):
                effective_date = "date(COALESCE(applied_at, updated_at, date_posted), 'localtime')"
                clauses.append("COALESCE(applied_at, updated_at, date_posted) IS NOT NULL")
            else:
                effective_date = "date(date_posted, 'localtime')"
                clauses.append("date_posted GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'")

            df_lower = str(date_filter).lower().strip()
            if df_lower in ("today", "1d"):
                clauses.append(f"{effective_date} >= date('now', 'localtime')")
            elif df_lower in ("3days", "3d"):
                clauses.append(f"{effective_date} >= date('now', 'localtime', '-3 days')")
            elif df_lower in ("7days", "7d"):
                clauses.append(f"{effective_date} >= date('now', 'localtime', '-7 days')")
            elif df_lower in ("14days", "14d"):
                clauses.append(f"{effective_date} >= date('now', 'localtime', '-14 days')")

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        order_by = "COALESCE(applied_at, updated_at) DESC, id DESC" if (status == "applied" or (status and "applied" in status)) else "COALESCE(date_posted, '') DESC, updated_at DESC, id DESC"
        query = f"SELECT * FROM jobs {where_sql} ORDER BY {order_by} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            raw_sources = d.get("sources")
            if raw_sources:
                try:
                    d["sources"] = json.loads(raw_sources)
                except Exception:
                    d["sources"] = [{"platform": d["platform"], "url": d["job_url"]}]
            else:
                d["sources"] = [{"platform": d["platform"], "url": d["job_url"]}]
            rows.append(d)
        return rows
    finally:
        conn.close()

def update_job_status(
    db_path: str,
    job_id: int,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    pipeline_stage: Optional[str] = None,
    follow_up_date: Optional[str] = None,
) -> bool:
    conn = get_db_connection(db_path)
    try:
        set_clauses = ["updated_at = CURRENT_TIMESTAMP"]
        params: List[Any] = []

        if status is not None:
            set_clauses.append("status = ?")
            params.append(status)
            if status == "applied":
                set_clauses.append("applied_at = COALESCE(applied_at, CURRENT_TIMESTAMP)")
        if notes is not None:
            set_clauses.append("notes = ?")
            params.append(notes)
        if pipeline_stage is not None:
            set_clauses.append("pipeline_stage = ?")
            params.append(pipeline_stage)
        if follow_up_date is not None:
            set_clauses.append("follow_up_date = ?")
            params.append(follow_up_date)

        query = f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ?"
        params.append(job_id)
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def export_jobs_csv(db_path: str, status: Optional[str] = "applied") -> str:
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM jobs"
        params: List[Any] = []
        if status and status != "all":
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY COALESCE(applied_at, created_at) DESC"
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
        headers = [
            "ID",
            "Title",
            "Company",
            "Location",
            "Platform",
            "Tier",
            "Salary",
            "Role Category",
            "Experience Level",
            "Status",
            "Pipeline Stage",
            "Date Posted",
            "Applied At",
            "Follow Up Date",
            "Notes",
            "Job URL",
        ]
        writer.writerow(headers)
        for r in rows:
            writer.writerow([
                r["id"],
                r["title"],
                r["company"],
                r["location"] or "",
                r["platform"],
                r["tier"],
                r["salary"] or "",
                r["role_category"],
                r["experience_level"],
                r["status"],
                r["pipeline_stage"] or "applied",
                r["date_posted"] or "",
                r["applied_at"] or "",
                r["follow_up_date"] or "",
                r["notes"] or "",
                r["job_url"],
            ])
        return output.getvalue()
    finally:
        conn.close()

def get_stats(db_path: str) -> Dict[str, Any]:
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status")
        status_counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}

        cursor.execute("SELECT experience_level, COUNT(*) as cnt FROM jobs WHERE status = 'new' GROUP BY experience_level")
        level_counts = {row["experience_level"]: row["cnt"] for row in cursor.fetchall()}

        cursor.execute("SELECT pipeline_stage, COUNT(*) as cnt FROM jobs WHERE status = 'applied' GROUP BY pipeline_stage")
        stage_counts = {row["pipeline_stage"] or "applied": row["cnt"] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) as total FROM jobs")
        total = cursor.fetchone()["total"]
        return {
            "total": total,
            "new": status_counts.get("new", 0),
            "saved": status_counts.get("saved", 0),
            "applied": status_counts.get("applied", 0),
            "ignored": status_counts.get("ignored", 0),
            "by_level": level_counts,
            "by_stage": stage_counts,
        }
    finally:
        conn.close()

def get_user_setting(db_path: str, key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM user_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row and row[0] is not None:
            return row[0]
        return default
    finally:
        conn.close()

def set_user_setting(db_path: str, key: str, value: str) -> bool:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
            """,
            (key, value),
        )
        conn.commit()
        return True
    finally:
        conn.close()

def get_all_user_settings(db_path: str) -> Dict[str, str]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM user_settings")
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    finally:
        conn.close()


