import io
import csv
import json
import sqlite3
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from src.models import Job, normalize_date, clean_url

VALID_STATUSES = {"new", "saved", "applied", "ignored"}
VALID_STAGES = {"applied", "hr_screening", "tech_exam", "final_interview", "offer", "rejected", "screening", "interview", "technical", "withdrawn"}

def normalize_company(name: str) -> str:
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r"\b(inc|incorporated|corp|corporation|llc|ltd|limited|pvt|co|gmbh|solutions|technologies|technology|philippines|ph)\b\.?", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def normalize_title(title: str) -> str:
    if not title:
        return ""
    s = title.lower().strip()
    s = re.sub(r"[\(\[\{]\s*(remote|hybrid|wfh|full[\s\-]*time|part[\s\-]*time|philippines|day\s*shift|night\s*shift)\s*[\)\]\}]", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def normalize_location(loc: str) -> str:
    if not loc:
        return ""
    s = loc.lower().strip()
    s = re.sub(r"\bp\d+\b", "", s)
    s = re.sub(r"\b\d{4,5}\b", "", s)
    s = re.sub(r"[,\-\/\|]", " ", s)
    s = re.sub(r"\b(city|province|region|ncr|national capital region)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def is_compatible_location(loc1: str, loc2: str) -> bool:
    if not loc1 or not loc2:
        return True
    l1 = (loc1 or "").strip().lower()
    l2 = (loc2 or "").strip().lower()
    if l1 == l2:
        return True

    remote_keywords = ("remote", "wfh", "work from home", "anywhere", "worldwide")
    if any(k in l1 for k in remote_keywords) and any(k in l2 for k in remote_keywords):
        return True

    n1 = normalize_location(l1)
    n2 = normalize_location(l2)
    if n1 == n2 or n1 in n2 or n2 in n1:
        return True

    ph_cities = {
        "taguig", "makati", "manila", "pasig", "quezon", "mandaluyong",
        "alabang", "muntinlupa", "paranaque", "pasay", "cebu", "davao",
        "clark", "angeles", "pampanga", "cavite", "laguna", "baguio",
        "iloilo", "bacolod", "cagayan"
    }
    tokens1 = set(n1.split())
    tokens2 = set(n2.split())
    matched1 = tokens1.intersection(ph_cities)
    matched2 = tokens2.intersection(ph_cities)
    if matched1 and matched2:
        return bool(matched1.intersection(matched2))

    ph_general = {"philippines", "ph", "metro manila", "remote", "wfh"}
    if any(k in l1 for k in ph_general) and any(k in l2 for k in ph_general):
        return True

    return False

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
    description TEXT DEFAULT '',
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
CREATE TABLE IF NOT EXISTS admin_login_attempts (
    client_key TEXT PRIMARY KEY,
    window_started INTEGER NOT NULL,
    attempts INTEGER NOT NULL
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
    elif url and not url.startswith("https://") and not url.startswith("http://"):
        url = f"https://{url}"
    return url

def get_turso_token() -> str:
    token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if not token and os.environ.get("VERCEL"):
        raise RuntimeError("TURSO_AUTH_TOKEN must be configured for Vercel")
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
    if is_turso_active(db_path) and not HAS_LIBSQL:
        raise RuntimeError("libsql-client is required for the configured cloud database")
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
        conn = get_db_connection(db_path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "description" not in columns:
                try:
                    conn.execute("ALTER TABLE jobs ADD COLUMN description TEXT DEFAULT ''")
                except Exception:
                    # Another cold start may have completed the same additive migration.
                    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
                    if "description" not in columns:
                        raise
        finally:
            conn.close()
        return
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
        if "description" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN description TEXT DEFAULT ''")
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

def insert_jobs(db_path: str, jobs: List[Job], *, sync_cache: Optional[dict] = None) -> Tuple[int, int]:
    if not jobs:
        return 0, 0
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    added = 0
    skipped = 0
    try:
        cursor = conn.cursor()
        cloud = isinstance(conn, TursoConnection)
        pending = []
        catalog = {}
        known_hashes = set()
        if cloud and sync_cache is not None and sync_cache.get("db_path") == db_path and "catalog" in sync_cache:
            catalog = sync_cache["catalog"]
            known_hashes = sync_cache["known_hashes"]
        elif cloud:
            for row in cursor.execute("SELECT dedup_hash, company, title, location, platform, job_url, salary, description, date_posted, sources, status FROM jobs ORDER BY id DESC").fetchall():
                item = dict(row)
                norm_co = normalize_company(item["company"]) or item["company"].strip().lower()
                norm_ti = normalize_title(item["title"]) or item["title"].strip().lower()
                catalog.setdefault((norm_co, norm_ti), []).append(item)
                known_hashes.add(item["dedup_hash"])

        def write(sql, params):
            if cloud:
                pending.append((sql, list(params)))
            else:
                cursor.execute(sql, params)

        for job in jobs:
            norm_date = normalize_date(job.date_posted) if job.date_posted else ""
            canonical_co = normalize_company(job.company) or job.company.strip().lower()
            canonical_title = normalize_title(job.title) or job.title.strip().lower()

            if cloud:
                candidates = catalog.get((canonical_co, canonical_title), [])
            else:
                cursor.execute(
                    """
                    SELECT id, dedup_hash, platform, job_url, salary, description, date_posted, sources, status, location, company, title
                    FROM jobs
                    WHERE lower(trim(company)) = ? AND lower(trim(title)) = ?
                    ORDER BY id DESC;
                    """,
                    (job.company.strip().lower(), job.title.strip().lower()),
                )
                candidates = [dict(r) for r in cursor.fetchall()]
                if not candidates:
                    cursor.execute(
                        """
                        SELECT id, dedup_hash, platform, job_url, salary, description, date_posted, sources, status, location, company, title
                        FROM jobs
                        WHERE lower(trim(company)) LIKE ?
                        ORDER BY id DESC;
                        """,
                        (f"%{canonical_co[:8]}%",),
                    )
                    all_c = [dict(r) for r in cursor.fetchall()]
                    candidates = [
                        r for r in all_c
                        if (normalize_company(r["company"]) or r["company"].strip().lower()) == canonical_co
                        and (normalize_title(r["title"]) or r["title"].strip().lower()) == canonical_title
                    ]
            def sources_for(row):
                try:
                    sources = json.loads(row["sources"] or "[]")
                    if not isinstance(sources, list):
                        sources = []
                except (ValueError, TypeError):
                    sources = []
                return [{"platform": row["platform"], "url": row["job_url"]}] + [source for source in sources if isinstance(source, dict)]

            existing = next((row for row in candidates
                             if any(clean_url(source.get("url", "")) == clean_url(job.job_url)
                                    for source in sources_for(row))), None)
            if existing is None:
                existing = next((row for row in candidates
                                 if is_compatible_location(row["location"], job.location)
                                 and not any(source.get("platform", "").lower() == job.platform.lower()
                                             for source in sources_for(row))), None)
            if existing:
                # Aggregate source platform and link
                try:
                    sources_list = json.loads(existing["sources"]) if existing["sources"] else []
                except Exception:
                    sources_list = []
                if not sources_list:
                    sources_list = [{"platform": existing["platform"], "url": existing["job_url"]}]

                already_present = any(
                    clean_url(s.get("url", "")) == clean_url(job.job_url)
                    for s in sources_list
                )
                if not already_present:
                    sources_list.append({"platform": job.platform, "url": job.job_url})

                new_salary = job.salary or existing["salary"] or ""
                old_description = existing.get("description") or ""
                new_description = job.description if len(job.description or "") > len(old_description) else old_description

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

                encoded_sources = json.dumps(sources_list)
                if (encoded_sources == existing["sources"]
                        and new_salary == (existing["salary"] or "")
                        and new_date == existing_date
                        and new_description == old_description):
                    continue

                write(
                    """
                    UPDATE jobs
                    SET sources = ?, salary = ?, date_posted = ?, description = ?,
                        status = CASE WHEN status = 'ignored' AND ? THEN 'new' ELSE status END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE dedup_hash = ?
                    """,
                    (encoded_sources, new_salary, new_date, new_description, int(is_new_post), existing["dedup_hash"]),
                )
                if cloud:
                    existing.update(sources=encoded_sources, salary=new_salary, description=new_description, date_posted=new_date, status=target_status)
            else:
                initial_sources = json.dumps([{"platform": job.platform, "url": job.job_url}])
                write(
                    """
                    INSERT INTO jobs (dedup_hash, title, company, location, platform, tier, job_url, salary, role_category, experience_level, date_posted, status, sources, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
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
                        job.description or "",
                    ),
                )
                inserted = job.dedup_hash not in known_hashes if cloud else cursor.rowcount > 0
                if inserted:
                    added += 1
                    known_hashes.add(job.dedup_hash)
                    if cloud:
                        catalog.setdefault((canonical_co, canonical_title), []).append({**vars(job), "date_posted": norm_date, "sources": initial_sources, "status": "new"})
                else:
                    skipped += 1
        if cloud:
            for start in range(0, len(pending), 50):
                conn._client.batch(pending[start:start + 50])
        conn.commit()
        if cloud and sync_cache is not None:
            sync_cache.update(db_path=db_path, catalog=catalog, known_hashes=known_hashes)
    except Exception:
        if sync_cache is not None:
            sync_cache.clear()
        raise
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
    with_total: bool = False,
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

        is_explicit_unspecified = experience_level and any(u in experience_level for u in ("Unspecified", "Other", "Others", "Unspecified / Other"))
        if not include_va and not is_explicit_unspecified and (not role_category or role_category.strip().upper() not in ("VIRTUAL ASSISTANT", "VA", "VA (WITH TRAINING)")):
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
                    elif el in ("Unspecified", "Other", "Others", "Unspecified / Other"):
                        level_clauses.append("(experience_level = 'Unspecified' OR experience_level IS NULL OR experience_level = '' OR experience_level = 'Other')")
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
            elif df_lower in ("15days", "15d"):
                clauses.append(f"{effective_date} >= date('now', 'localtime', '-15 days')")

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        order_by = "COALESCE(applied_at, updated_at) DESC, id DESC" if (status == "applied" or (status and "applied" in status)) else "COALESCE(date_posted, '') DESC, updated_at DESC, id DESC"
        projection = "*, COUNT(*) OVER () AS matching_total" if with_total else "*"
        query = f"SELECT {projection} FROM jobs {where_sql} ORDER BY {order_by} LIMIT ? OFFSET ?"
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
    if status is not None and status not in VALID_STATUSES:
        raise ValueError("Unsupported job status")
    if pipeline_stage is not None and pipeline_stage not in VALID_STAGES:
        raise ValueError("Unsupported pipeline stage")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 10000):
        raise ValueError("Notes must be text of at most 10000 characters")
    if follow_up_date:
        from datetime import date
        if not isinstance(follow_up_date, str):
            raise ValueError("Follow-up date must use YYYY-MM-DD")
        try:
            date.fromisoformat(follow_up_date)
        except ValueError:
            raise ValueError("Follow-up date must use YYYY-MM-DD") from None
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

        cursor.execute("SELECT COUNT(*) as cnt FROM jobs WHERE role_category = 'Virtual Assistant' OR lower(title) LIKE '%virtual assistant%'")
        va_count = cursor.fetchone()["cnt"]

        return {
            "total": total,
            "new": status_counts.get("new", 0),
            "saved": status_counts.get("saved", 0),
            "applied": status_counts.get("applied", 0),
            "ignored": status_counts.get("ignored", 0),
            "va": va_count,
            "by_level": level_counts,
            "by_stage": stage_counts,
        }
    finally:
        conn.close()

def decode_setting_value(raw):
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and "__preference_revision" in value and "value" in value:
            return value["value"]
    except (ValueError, TypeError):
        pass
    return raw


def get_user_setting(db_path: str, key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM user_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row and row[0] is not None:
            return decode_setting_value(row[0])
        return default
    finally:
        conn.close()

def set_user_setting(db_path: str, key: str, value: str, revision: Optional[int] = None) -> bool:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        stored = value if revision is None else json.dumps({"__preference_revision": revision, "value": value})
        condition = "" if revision is None else "WHERE CASE WHEN json_valid(user_settings.value) THEN COALESCE(json_extract(user_settings.value, '$.__preference_revision'), 0) ELSE 0 END <= ?"
        params = (key, stored) if revision is None else (key, stored, revision)
        cursor.execute(
            "INSERT INTO user_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP " + condition,
            params,
        )
        conn.commit()
        return True
    finally:
        conn.close()


def set_sync_checkpoint(db_path: str, checkpoint: str, status: str) -> None:
    conn = get_db_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO user_settings (key, value, updated_at) VALUES "
            "('sync_batch_progress', ?, CURRENT_TIMESTAMP), ('sync_status', ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (checkpoint, status),
        )
        conn.commit()
    finally:
        conn.close()


def acquire_sync_lease(db_path: str, lease: str, now: int, key: str = "sync_lease") -> bool:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("""
            INSERT INTO user_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            WHERE CAST(substr(user_settings.value, 1, instr(user_settings.value, '|') - 1) AS INTEGER) <= ?
        """, (key, lease, now))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def release_sync_lease(db_path: str, lease: str, key: str = "sync_lease") -> None:
    conn = get_db_connection(db_path)
    try:
        conn.execute("DELETE FROM user_settings WHERE key=? AND value=?", (key, lease))
        conn.commit()
    finally:
        conn.close()


def renew_sync_lease(db_path: str, owner: str, expires_at: int, now: int, key: str = "sync_lease") -> bool:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "UPDATE user_settings SET value=? WHERE key=? "
            "AND substr(value, instr(value, '|') + 1)=? "
            "AND CAST(substr(value, 1, instr(value, '|') - 1) AS INTEGER)>?",
            (f"{expires_at}|{owner}", key, owner, now),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def get_all_user_settings(db_path: str) -> Dict[str, str]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM user_settings")
        rows = cursor.fetchall()
        return {row[0]: decode_setting_value(row[1]) for row in rows}
    finally:
        conn.close()


