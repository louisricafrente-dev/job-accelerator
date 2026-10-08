import io
import csv
import sqlite3
import os
from typing import Any, Dict, List, Optional, Tuple
from src.models import Job

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
    applied_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_level ON jobs(experience_level);
CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(role_category);
CREATE INDEX IF NOT EXISTS idx_jobs_tier ON jobs(tier);
"""

def init_db(db_path: str = "data/jobs.db") -> None:
    parent = os.path.dirname(db_path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
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

    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_stage ON jobs(pipeline_stage);")
    conn.commit()
    conn.close()

def insert_jobs(db_path: str, jobs: List[Job]) -> Tuple[int, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    added = 0
    skipped = 0
    cursor = conn.cursor()
    for job in jobs:
        cursor.execute(
            """
            INSERT INTO jobs (dedup_hash, title, company, location, platform, tier, job_url, salary, role_category, experience_level, date_posted, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
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
                job.date_posted,
            ),
        )
        if cursor.rowcount > 0:
            added += 1
        else:
            skipped += 1
    conn.commit()
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
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    clauses = []
    params: List[Any] = []

    if status:
        clauses.append("status = ?")
        params.append(status)
    if role_category and role_category != "All":
        rc = role_category.strip()
        if rc == "Frontend":
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
            clauses.append("(role_category = 'Web/Software Dev' OR role_category = 'Both' OR role_category != 'Data/AI/ML')")
        else:
            clauses.append("(role_category = ? OR role_category = 'Both' OR lower(title) LIKE ?)")
            params.extend([rc, f"%{rc.lower()}%"])
    if experience_level and experience_level != "All":
        clauses.append("experience_level = ?")
        params.append(experience_level)
    if tier:
        clauses.append("tier = ?")
        params.append(tier)
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
        effective_date = "COALESCE(NULLIF(substr(date_posted, 1, 10), ''), date(created_at))"
        if date_filter == "today":
            clauses.append(f"{effective_date} >= date('now', 'localtime')")
        elif date_filter == "3days":
            clauses.append(f"{effective_date} >= date('now', '-3 days')")
        elif date_filter == "7days":
            clauses.append(f"{effective_date} >= date('now', '-7 days')")
        elif date_filter == "14days":
            clauses.append(f"{effective_date} >= date('now', '-14 days')")

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    query = f"SELECT * FROM jobs {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def update_job_status(
    db_path: str,
    job_id: int,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    pipeline_stage: Optional[str] = None,
    follow_up_date: Optional[str] = None,
) -> bool:
    conn = sqlite3.connect(db_path)
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
    success = cursor.rowcount > 0
    conn.close()
    return success

def export_jobs_csv(db_path: str, status: Optional[str] = "applied") -> str:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM jobs"
    params: List[Any] = []
    if status and status != "all":
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY COALESCE(applied_at, created_at) DESC"
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

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

def get_stats(db_path: str) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status")
    status_counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}

    cursor.execute("SELECT experience_level, COUNT(*) as cnt FROM jobs WHERE status = 'new' GROUP BY experience_level")
    level_counts = {row["experience_level"]: row["cnt"] for row in cursor.fetchall()}

    cursor.execute("SELECT pipeline_stage, COUNT(*) as cnt FROM jobs WHERE status = 'applied' GROUP BY pipeline_stage")
    stage_counts = {row["pipeline_stage"] or "applied": row["cnt"] for row in cursor.fetchall()}

    cursor.execute("SELECT COUNT(*) as total FROM jobs")
    total = cursor.fetchone()["total"]
    conn.close()
    return {
        "total": total,
        "new": status_counts.get("new", 0),
        "saved": status_counts.get("saved", 0),
        "applied": status_counts.get("applied", 0),
        "ignored": status_counts.get("ignored", 0),
        "by_level": level_counts,
        "by_stage": stage_counts,
    }

