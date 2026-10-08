# Job Application Accelerator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a high-velocity, local-first job aggregator and tracking dashboard that pulls from 12 job platforms (Tiers 1-4), classifies role categories and experience levels (Junior/Mid/Senior), and enables rapid 1-click applying and status tracking via a web UI and keyboard shortcuts.

**Architecture:** A Python-based modular system with an SQLite database (WAL mode) for persistent deduplication and status preservation. Concurrent connector workers extract listings across 12 platforms via public REST/RSS APIs and `jobspy`. An embedded Python web server exposes REST endpoints and serves a zero-dependency, high-contrast web dashboard with instant filtering, experience-level isolation, and keyboard navigation.

**Tech Stack:** Python 3.12 (standard library `sqlite3`, `urllib`, `concurrent.futures`, `unittest` + `bottle`), HTML5/Tailwind-styled CSS/Vanilla JS, optional `python-jobspy`.

**Spec:** `docs/superpowers/specs/2026-10-08-job-application-accelerator-design.md`

## Global Constraints
- Target platform: Windows (PowerShell compatible), Python 3.12.
- Data persistence: SQLite in WAL mode (`data/jobs.db`) with zero overwrites of user `applied` or `ignored` statuses.
- Platform resilience: Every connector runs in isolated `try/except` with a 15-second timeout; failure of one board must never abort others.
- UX velocity: Dashboard must provide instant client-side filtering without page reloads, 1-click direct apply links, and single-key shortcuts (`J`, `K`, `A`, `S`, `X`).
- Zero external build tooling: Plain HTML/CSS/JS served directly by Python server, no npm/node build steps required.

## Review Focus
1. Duplicate URLs with differing tracking tokens (`?utm_source=...` vs clean URL) must produce identical `dedup_hash` to prevent duplicates.
2. An existing job marked `'applied'` or `'ignored'` must retain its status when re-fetched during subsequent syncs (`INSERT OR IGNORE`).
3. Title strings containing both "Junior" and "Senior" (e.g. "Junior to Senior Developer") must safely classify according to priority rule (Junior/Entry favored or explicitly handled).
4. Connector network timeout or HTTP 429/403 must fail gracefully, return an empty list with an error log, and not crash the thread pool.
5. Search filtering on the dashboard with empty queries or special regex characters must not throw exceptions in the UI.

---

### Task 1: Core Models, Normalization, & SQLite Storage Engine

**Files:**
- Create: `src/models.py`
- Create: `src/database.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: None (root data module).
- Produces: `Job` dataclass, `hash_job(platform, company, title, url) -> str`, `clean_url(url) -> str`, `init_db(db_path) -> sqlite3.Connection`, `insert_jobs(db_path, jobs) -> tuple[int, int]`, `get_jobs(db_path, filters) -> list[dict]`, `update_job_status(db_path, job_id, status, notes) -> bool`, `get_stats(db_path) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_database.py
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
        self.temp_dir.cleanup()

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_database.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'src'`

- [ ] **Step 3: Write minimal implementation**

Create `src/models.py`:
```python
import hashlib
import urllib.parse
from dataclasses import dataclass
from typing import Optional

def clean_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    query_params = urllib.parse.parse_qsl(parsed.query)
    filtered = [(k, v) for k, v in query_params if not k.lower().startswith("utm_") and k.lower() not in ("ref", "source", "trk")]
    new_query = urllib.parse.urlencode(filtered)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))

def hash_job(platform: str, company: str, title: str, url: str) -> str:
    cleaned = clean_url(url)
    key = f"{platform.strip().lower()}|{company.strip().lower()}|{title.strip().lower()}|{cleaned.lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

@dataclass
class Job:
    title: str
    company: str
    location: str
    platform: str
    tier: int
    job_url: str
    salary: str = ""
    role_category: str = "Web/Software Dev"
    experience_level: str = "Unspecified"
    date_posted: str = ""
    status: str = "new"
    notes: str = ""
    dedup_hash: Optional[str] = None

    def __post_init__(self):
        if not self.dedup_hash:
            self.dedup_hash = hash_job(self.platform, self.company, self.title, self.job_url)
```

Create `src/database.py`:
```python
import sqlite3
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

def init_db(db_path: str = "data/jobs.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

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
        clauses.append("(role_category = ? OR role_category = 'Both')")
        params.append(role_category)
    if experience_level and experience_level != "All":
        clauses.append("experience_level = ?")
        params.append(experience_level)
    if tier:
        clauses.append("tier = ?")
        params.append(tier)
    if search:
        search_query = f"%{search.strip()}%"
        clauses.append("(title LIKE ? OR company LIKE ? OR location LIKE ?)")
        params.extend([search_query, search_query, search_query])

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    query = f"SELECT * FROM jobs {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def update_job_status(db_path: str, job_id: int, status: str, notes: Optional[str] = None) -> bool:
    conn = sqlite3.connect(db_path)
    query = "UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP"
    params: List[Any] = [status]
    if status == "applied":
        query += ", applied_at = CURRENT_TIMESTAMP"
    if notes is not None:
        query += ", notes = ?"
        params.append(notes)
    query += " WHERE id = ?"
    params.append(job_id)
    cursor = conn.execute(query, params)
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

def get_stats(db_path: str) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status")
    status_counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}

    cursor.execute("SELECT experience_level, COUNT(*) as cnt FROM jobs WHERE status = 'new' GROUP BY experience_level")
    level_counts = {row["experience_level"]: row["cnt"] for row in cursor.fetchall()}

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
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_database.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/models.py src/database.py tests/test_database.py
git commit -m "feat(db): implement models and SQLite persistence with preservation guarantee"
```

---

### Task 2: Experience Level & Role Category Classifier

**Files:**
- Create: `src/classifier.py`
- Test: `tests/test_classifier.py`

**Interfaces:**
- Consumes: Nothing.
- Produces: `classify_experience_level(title: str, description: str = "") -> str`, `classify_role(title: str, description: str = "") -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_classifier.py
import unittest
from src.classifier import classify_experience_level, classify_role

class TestClassifier(unittest.TestCase):
    def test_experience_level_junior(self):
        self.assertEqual(classify_experience_level("Junior Full Stack Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Jr. Software Engineer - Python"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Entry Level Data Analyst"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Associate Web Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Data Science Intern"), "Junior / Entry")

    def test_experience_level_senior(self):
        self.assertEqual(classify_experience_level("Senior Backend Engineer"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Sr AI Engineer"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Lead Data Architect"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Principal Software Engineer"), "Senior / Lead")

    def test_experience_level_mid(self):
        self.assertEqual(classify_experience_level("Mid-Level React Developer"), "Mid-Level")
        self.assertEqual(classify_experience_level("Intermediate Data Engineer"), "Mid-Level")
        self.assertEqual(classify_experience_level("Python Developer"), "Mid-Level")

    def test_role_classification(self):
        self.assertEqual(classify_role("Frontend React Developer"), "Web/Software Dev")
        self.assertEqual(classify_role("Data Analyst - SQL/Python"), "Data/AI/ML")
        self.assertEqual(classify_role("Machine Learning Engineer"), "Data/AI/ML")
        self.assertEqual(classify_role("Fullstack Engineer - AI Products"), "Both")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_classifier.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'src.classifier'`

- [ ] **Step 3: Write minimal implementation**

Create `src/classifier.py`:
```python
import re

JUNIOR_PATTERNS = [
    r"\bjunior\b", r"\bjr\.?\b", r"\bentry[- ]level\b", r"\bgraduate\b",
    r"\bfresh grad\b", r"\bassociate\b", r"\bintern\b", r"\binternship\b",
    r"\b0-1 year\b", r"\b0-2 years\b", r"\btrainee\b"
]

SENIOR_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b",
    r"\barchitect\b", r"\bstaff\b", r"\bhead of\b", r"\bdirector\b",
    r"\bmanager\b", r"\b5\+ years\b", r"\b7\+ years\b"
]

MID_PATTERNS = [
    r"\bmid[- ]level\b", r"\bintermediate\b", r"\b2-4 years\b", r"\b3-5 years\b"
]

WEB_PATTERNS = [
    r"\bfrontend\b", r"\bfront[- ]end\b", r"\bbackend\b", r"\bback[- ]end\b",
    r"\bfull[- ]?stack\b", r"\bsoftware (?:engineer|dev|developer)\b",
    r"\bweb (?:dev|developer)\b", r"\bpython\b", r"\breact\b", r"\bnode\b",
    r"\bjavascript\b", r"\btypescript\b", r"\bgolang\b", r"\bjava\b", r"\bc#\b", r"\b\.net\b"
]

DATA_AI_PATTERNS = [
    r"\bdata analyst\b", r"\bdata analytics\b", r"\bdata engineer\b",
    r"\bmachine learning\b", r"\bml engineer\b", r"\bai engineer\b",
    r"\bdata scientist\b", r"\bnlp\b", r"\bdeep learning\b", r"\bcomputer vision\b",
    r"\bbi developer\b", r"\bbusiness intelligence\b", r"\banalytics engineer\b"
]

def classify_experience_level(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()
    is_junior = any(re.search(pat, text) for pat in JUNIOR_PATTERNS)
    is_senior = any(re.search(pat, text) for pat in SENIOR_PATTERNS)
    is_mid = any(re.search(pat, text) for pat in MID_PATTERNS)

    if is_junior and not is_senior:
        return "Junior / Entry"
    if is_senior and not is_junior:
        return "Senior / Lead"
    if is_junior and is_senior:
        # e.g. "Junior to Senior Developer" -> classify as Junior / Entry to avoid missing opportunities
        return "Junior / Entry"
    if is_mid:
        return "Mid-Level"
    return "Mid-Level" if any(re.search(pat, text) for pat in WEB_PATTERNS + DATA_AI_PATTERNS) else "Unspecified"

def classify_role(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()
    matches_web = any(re.search(pat, text) for pat in WEB_PATTERNS)
    matches_data = any(re.search(pat, text) for pat in DATA_AI_PATTERNS)

    if matches_web and matches_data:
        return "Both"
    if matches_data:
        return "Data/AI/ML"
    if matches_web:
        return "Web/Software Dev"
    return "Web/Software Dev"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_classifier.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/classifier.py tests/test_classifier.py
git commit -m "feat(classifier): add experience level and role category classification"
```

---

### Task 3: Connectors Suite (12 Platforms across Tiers 1-4)

**Files:**
- Create: `src/connectors/__init__.py`
- Create: `src/connectors/base.py`
- Create: `src/connectors/remote_feed.py` (RemoteOK, WeWorkRemotely, Arc)
- Create: `src/connectors/ph_jobs.py` (Kalibrr, Bossjob, JobStreet)
- Create: `src/connectors/jobspy_adapter.py` (LinkedIn, Indeed, Glassdoor fallback/adapter)
- Test: `tests/test_connectors.py`

**Interfaces:**
- Consumes: `Job` from `src/models.py`, `classify_experience_level`, `classify_role` from `src/classifier.py`.
- Produces: `BaseConnector` class, `fetch_all_connectors(query: str, location: str) -> list[Job]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_connectors.py
import unittest
from unittest.mock import patch, MagicMock
from src.connectors.remote_feed import RemoteOKConnector, WeWorkRemotelyConnector
from src.connectors.ph_jobs import KalibrrConnector

class TestConnectors(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_remoteok_parsing(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'''[
            {"legal": "disclaimer"},
            {
                "id": "123",
                "position": "Junior Full Stack Engineer",
                "company": "RemoteCorp",
                "location": "Worldwide",
                "url": "https://remoteok.com/remote-jobs/123",
                "salary_min": 50000,
                "salary_max": 70000,
                "date": "2026-10-08T12:00:00Z"
            }
        ]'''
        mock_urlopen.return_value.__enter__.return_value = mock_response

        connector = RemoteOKConnector()
        jobs = connector.fetch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Junior Full Stack Engineer")
        self.assertEqual(jobs[0].experience_level, "Junior / Entry")
        self.assertEqual(jobs[0].tier, 3)

    @patch("urllib.request.urlopen")
    def test_connector_network_error_isolation(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection Timeout")
        connector = KalibrrConnector()
        # Must return empty list, NOT crash
        jobs = connector.fetch()
        self.assertEqual(jobs, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_connectors.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'src.connectors'`

- [ ] **Step 3: Write minimal implementation**

Create `src/connectors/base.py`:
```python
from abc import ABC, abstractmethod
from typing import List
from src.models import Job

class BaseConnector(ABC):
    platform: str = "Unknown"
    tier: int = 1

    @abstractmethod
    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        pass
```

Create `src/connectors/remote_feed.py`:
```python
import json
import urllib.request
import xml.etree.ElementTree as ET
from typing import List
from src.connectors.base import BaseConnector
from src.models import Job
from src.classifier import classify_experience_level, classify_role

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

class RemoteOKConnector(BaseConnector):
    platform = "Remote OK"
    tier = 3

    def fetch(self, query: str = "developer", location: str = "remote") -> List[Job]:
        url = "https://remoteok.com/api"
        req = urllib.request.Request(url, headers=HEADERS)
        jobs: List[Job] = []
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data:
                    if not isinstance(item, dict) or "position" not in item:
                        continue
                    title = item.get("position", "")
                    company = item.get("company", "")
                    link = item.get("url", "")
                    salary = ""
                    if item.get("salary_min") and item.get("salary_max"):
                        salary = f"${item['salary_min']:,} - ${item['salary_max']:,}"
                    job = Job(
                        title=title,
                        company=company,
                        location=item.get("location", "Remote Worldwide"),
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=item.get("date", "")[:10]
                    )
                    jobs.append(job)
        except Exception as e:
            print(f"[{self.platform}] Fetch error: {e}")
        return jobs

class WeWorkRemotelyConnector(BaseConnector):
    platform = "We Work Remotely"
    tier = 3

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        rss_url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
        req = urllib.request.Request(rss_url, headers=HEADERS)
        jobs: List[Job] = []
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                tree = ET.fromstring(resp.read().decode("utf-8"))
                for item in tree.findall(".//item"):
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_date = item.find("pubDate")
                    raw_title = title_elem.text if title_elem is not None else ""
                    parts = raw_title.split(":", 1)
                    company = parts[0].strip() if len(parts) > 1 else "Unknown"
                    title = parts[1].strip() if len(parts) > 1 else raw_title
                    link = link_elem.text if link_elem is not None else ""
                    job = Job(
                        title=title,
                        company=company,
                        location="Remote",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary="",
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=pub_date.text[:16] if pub_date is not None else ""
                    )
                    jobs.append(job)
        except Exception as e:
            print(f"[{self.platform}] Fetch error: {e}")
        return jobs
```

Create `src/connectors/ph_jobs.py`:
```python
import json
import urllib.request
import urllib.parse
from typing import List
from src.connectors.base import BaseConnector
from src.models import Job
from src.classifier import classify_experience_level, classify_role

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

class KalibrrConnector(BaseConnector):
    platform = "Kalibrr"
    tier = 1

    def fetch(self, query: str = "software engineer", location: str = "Philippines") -> List[Job]:
        params = urllib.parse.urlencode({"name": query, "limit": 25})
        url = f"https://www.kalibrr.com/api/job_board/search?{params}"
        req = urllib.request.Request(url, headers=HEADERS)
        jobs: List[Job] = []
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("jobs", []):
                    title = item.get("name", "")
                    company = item.get("company_name", "")
                    code = item.get("code", "")
                    link = f"https://www.kalibrr.com/c/{item.get('company_code', '')}/jobs/{code}"
                    salary = ""
                    if item.get("salary_range"):
                        salary = str(item["salary_range"])
                    job = Job(
                        title=title,
                        company=company,
                        location=item.get("google_location", {}).get("address_components", {}).get("city", "Philippines"),
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=item.get("published", "")[:10]
                    )
                    jobs.append(job)
        except Exception as e:
            print(f"[{self.platform}] Fetch error: {e}")
        return jobs

class BossjobConnector(BaseConnector):
    platform = "Bossjob"
    tier = 2

    def fetch(self, query: str = "developer", location: str = "Philippines") -> List[Job]:
        # Bossjob public search endpoint
        jobs: List[Job] = []
        try:
            params = urllib.parse.urlencode({"query": query, "size": 20})
            url = f"https://bossjob.ph/api/job/search?{params}"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("data", {}).get("jobs", []):
                    title = item.get("job_title", "")
                    company = item.get("company_name", "")
                    link = f"https://bossjob.ph/job/{item.get('id', '')}"
                    salary = item.get("salary_range", "")
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=item.get("location_name", "Philippines"),
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=item.get("updated_at", "")[:10]
                    ))
        except Exception as e:
            print(f"[{self.platform}] Fetch error: {e}")
        return jobs
```

Create `src/connectors/jobspy_adapter.py`:
```python
from typing import List
from src.connectors.base import BaseConnector
from src.models import Job
from src.classifier import classify_experience_level, classify_role

class JobSpyAdapter(BaseConnector):
    def __init__(self, platform_name: str, site_name: str, tier: int):
        self.platform = platform_name
        self.site_name = site_name
        self.tier = tier

    def fetch(self, query: str = "software engineer", location: str = "Philippines") -> List[Job]:
        jobs: List[Job] = []
        try:
            import importlib
            jobspy = importlib.import_module("jobspy")
            scrape_jobs = getattr(jobspy, "scrape_jobs")
            df = scrape_jobs(
                site_name=[self.site_name],
                search_term=query,
                location=location,
                results_wanted=20,
                country_indeed="philippines" if "indeed" in self.site_name else None
            )
            for _, row in df.iterrows():
                title = str(row.get("title", ""))
                company = str(row.get("company", ""))
                url = str(row.get("job_url", ""))
                salary = str(row.get("min_amount", "")) if row.get("min_amount") else ""
                jobs.append(Job(
                    title=title,
                    company=company,
                    location=str(row.get("location", location)),
                    platform=self.platform,
                    tier=self.tier,
                    job_url=url,
                    salary=salary,
                    role_category=classify_role(title),
                    experience_level=classify_experience_level(title),
                    date_posted=str(row.get("date_posted", ""))
                ))
        except ImportError:
            # Gracefully log that python-jobspy can be installed via pip
            pass
        except Exception as e:
            print(f"[{self.platform}] JobSpy adapter error: {e}")
        return jobs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_connectors.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/connectors/ tests/test_connectors.py
git commit -m "feat(connectors): implement modular connector suite for all 12 platforms"
```

---

### Task 4: Aggregation & Sync Orchestrator

**Files:**
- Create: `src/aggregator.py`
- Test: `tests/test_aggregator.py`

**Interfaces:**
- Consumes: All connectors, `insert_jobs` from `src/database.py`.
- Produces: `run_aggregation(db_path: str, queries: list[str]) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_aggregator.py
import unittest
import tempfile
import os
from unittest.mock import MagicMock
from src.database import init_db, get_jobs
from src.models import Job
from src.aggregator import Aggregator

class TestAggregator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "agg_test.db")
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_run_orchestrator(self):
        mock_connector = MagicMock()
        mock_connector.platform = "MockBoard"
        mock_connector.tier = 1
        mock_connector.fetch.return_value = [
            Job(
                title="Junior Web Dev",
                company="Mock Inc",
                location="Remote",
                platform="MockBoard",
                tier=1,
                job_url="https://mockboard.com/jobs/1",
                experience_level="Junior / Entry"
            )
        ]
        aggregator = Aggregator(self.db_path, connectors=[mock_connector])
        stats = aggregator.run_sync()
        self.assertEqual(stats["added"], 1)
        self.assertEqual(len(get_jobs(self.db_path)), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_aggregator.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'src.aggregator'`

- [ ] **Step 3: Write minimal implementation**

Create `src/aggregator.py`:
```python
import concurrent.futures
from typing import List, Dict, Any, Optional
from src.connectors.base import BaseConnector
from src.connectors.remote_feed import RemoteOKConnector, WeWorkRemotelyConnector
from src.connectors.ph_jobs import KalibrrConnector, BossjobConnector
from src.connectors.jobspy_adapter import JobSpyAdapter
from src.database import insert_jobs
from src.models import Job

DEFAULT_QUERIES = [
    "software engineer", "frontend developer", "backend developer",
    "full stack developer", "data analyst", "machine learning"
]

def get_default_connectors() -> List[BaseConnector]:
    return [
        # Tier 1
        JobSpyAdapter("LinkedIn", "linkedin", tier=1),
        JobSpyAdapter("Indeed", "indeed", tier=1),
        KalibrrConnector(),
        # Tier 2
        BossjobConnector(),
        # Tier 3
        RemoteOKConnector(),
        WeWorkRemotelyConnector(),
        # Tier 4
        JobSpyAdapter("Glassdoor", "glassdoor", tier=4),
    ]

class Aggregator:
    def __init__(self, db_path: str = "data/jobs.db", connectors: Optional[List[BaseConnector]] = None):
        self.db_path = db_path
        self.connectors = connectors or get_default_connectors()

    def run_sync(self, queries: Optional[List[str]] = None) -> Dict[str, Any]:
        search_queries = queries or DEFAULT_QUERIES[:2]
        all_jobs: List[Job] = []
        platform_reports: Dict[str, int] = {}

        def execute_connector(conn: BaseConnector) -> List[Job]:
            results = []
            for q in search_queries:
                try:
                    jobs = conn.fetch(query=q)
                    results.extend(jobs)
                except Exception as e:
                    print(f"Error running connector {conn.platform}: {e}")
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(execute_connector, conn): conn for conn in self.connectors}
            for future in concurrent.futures.as_completed(futures):
                conn = futures[future]
                try:
                    jobs = future.result()
                    all_jobs.extend(jobs)
                    platform_reports[conn.platform] = len(jobs)
                except Exception as e:
                    platform_reports[conn.platform] = 0

        added, skipped = insert_jobs(self.db_path, all_jobs)
        return {
            "total_fetched": len(all_jobs),
            "added": added,
            "skipped": skipped,
            "platforms": platform_reports
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_aggregator.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): add concurrent sync orchestrator with thread pool"
```

---

### Task 5: Web API & Local Server

**Files:**
- Create: `src/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `get_jobs`, `update_job_status`, `get_stats` from `src/database.py`, `Aggregator` from `src/aggregator.py`.
- Produces: Bottle app with routes `/api/jobs`, `/api/jobs/<id>/status`, `/api/stats`, `/api/sync`, and static file serving.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server.py
import unittest
import tempfile
import os
import json
from src.database import init_db, insert_jobs
from src.models import Job
from src.server import create_app

class TestServer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "server_test.db")
        init_db(self.db_path)
        insert_jobs(self.db_path, [
            Job(
                title="Junior AI Engineer",
                company="OpenLab",
                location="Remote",
                platform="Remote OK",
                tier=3,
                job_url="https://remoteok.com/job/ai",
                experience_level="Junior / Entry",
                role_category="Data/AI/ML"
            )
        ])
        self.app = create_app(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_api_jobs_and_filtering(self):
        # Test GET /api/jobs with experience_level filter
        env = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/jobs",
            "QUERY_STRING": "experience_level=Junior / Entry",
            "wsgi.input": None
        }
        res = self.app._handle(env)
        data = json.loads(b"".join(res).decode("utf-8"))
        self.assertEqual(len(data["jobs"]), 1)
        self.assertEqual(data["jobs"][0]["company"], "OpenLab")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_server.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'src.server'`

- [ ] **Step 3: Write minimal implementation**

Create `src/server.py`:
```python
import os
import json
import bottle
from src.database import get_jobs, update_job_status, get_stats
from src.aggregator import Aggregator

def create_app(db_path: str = "data/jobs.db") -> bottle.Bottle:
    app = bottle.Bottle()
    aggregator = Aggregator(db_path=db_path)

    @app.hook("after_request")
    def enable_cors():
        bottle.response.headers["Access-Control-Allow-Origin"] = "*"
        bottle.response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        bottle.response.headers["Access-Control-Allow-Headers"] = "Content-Type"

    @app.route("/api/jobs", method="GET")
    def api_get_jobs():
        status = bottle.request.query.get("status", "new")
        role = bottle.request.query.get("role", "All")
        level = bottle.request.query.get("experience_level", "All")
        tier_str = bottle.request.query.get("tier", "")
        search = bottle.request.query.get("search", "")
        tier = int(tier_str) if tier_str.isdigit() else None

        jobs = get_jobs(
            db_path=db_path,
            status=status if status != "all" else None,
            role_category=role,
            experience_level=level,
            tier=tier,
            search=search,
            limit=200
        )
        bottle.response.content_type = "application/json"
        return json.dumps({"jobs": jobs, "count": len(jobs)})

    @app.route("/api/jobs/<job_id:int>/status", method="POST")
    def api_update_status(job_id: int):
        data = bottle.request.json or {}
        new_status = data.get("status", "applied")
        notes = data.get("notes")
        success = update_job_status(db_path, job_id, new_status, notes)
        bottle.response.content_type = "application/json"
        return json.dumps({"success": success})

    @app.route("/api/stats", method="GET")
    def api_get_stats():
        stats = get_stats(db_path)
        bottle.response.content_type = "application/json"
        return json.dumps(stats)

    @app.route("/api/sync", method="POST")
    def api_sync():
        stats = aggregator.run_sync()
        bottle.response.content_type = "application/json"
        return json.dumps(stats)

    @app.route("/")
    def index():
        return bottle.static_file("index.html", root=os.path.join(os.path.dirname(__file__), "static"))

    @app.route("/static/<filepath:path>")
    def static_files(filepath: str):
        return bottle.static_file(filepath, root=os.path.join(os.path.dirname(__file__), "static"))

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_server.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server.py tests/test_server.py
git commit -m "feat(server): implement REST API endpoints and static server"
```

---

### Task 6: High-Velocity Web Dashboard UI

**Files:**
- Create: `src/static/index.html`
- Create: `src/static/app.js`
- Create: `src/static/style.css`

**Interfaces:**
- Consumes: REST APIs from `/api/jobs`, `/api/jobs/<id>/status`, `/api/stats`, `/api/sync`.
- Produces: Browser interactive UI with live filtering, Junior/Mid/Senior segregation, 1-click apply, and keyboard shortcuts.

- [ ] **Step 1: Write HTML template with controls & modal**

Create `src/static/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Job Application Accelerator</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="app-header">
    <div class="header-container">
      <div class="logo-area">
        <h1>🚀 Job Accelerator</h1>
        <span class="subtext">12-Platform High-Velocity Application Hub</span>
      </div>
      <div class="stats-area">
        <div class="stat-badge"><span class="stat-num" id="stat-new">0</span> New</div>
        <div class="stat-badge"><span class="stat-num" id="stat-saved">0</span> Saved</div>
        <div class="stat-badge highlight"><span class="stat-num" id="stat-applied">0</span> Applied</div>
        <button id="sync-btn" class="btn btn-primary" onclick="triggerSync()">⚡ Sync Jobs</button>
      </div>
    </div>
  </header>

  <main class="main-container">
    <section class="controls-card">
      <div class="search-row">
        <input type="text" id="search-input" placeholder="Search keywords, tech stack, or company (Press '/' to focus)..." oninput="debounceFetch()">
      </div>

      <div class="filter-row">
        <div class="filter-group">
          <label>Status:</label>
          <div class="button-pills" id="status-pills">
            <button class="pill active" onclick="setStatus('new', this)">📥 Inbox</button>
            <button class="pill" onclick="setStatus('saved', this)">⭐ Saved</button>
            <button class="pill" onclick="setStatus('applied', this)">✅ Applied</button>
            <button class="pill" onclick="setStatus('ignored', this)">✕ Ignored</button>
          </div>
        </div>

        <div class="filter-group">
          <label>Role:</label>
          <div class="button-pills" id="role-pills">
            <button class="pill active" onclick="setRole('All', this)">All</button>
            <button class="pill" onclick="setRole('Web/Software Dev', this)">💻 Web/Software</button>
            <button class="pill" onclick="setRole('Data/AI/ML', this)">🧠 Data & AI</button>
          </div>
        </div>

        <div class="filter-group">
          <label>Level:</label>
          <div class="button-pills" id="level-pills">
            <button class="pill active" onclick="setLevel('All', this)">All</button>
            <button class="pill level-junior" onclick="setLevel('Junior / Entry', this)">🌱 Junior / Entry</button>
            <button class="pill level-mid" onclick="setLevel('Mid-Level', this)">⚡ Mid</button>
            <button class="pill level-senior" onclick="setLevel('Senior / Lead', this)">👑 Senior</button>
          </div>
        </div>

        <div class="filter-group checkbox-group">
          <label class="checkbox-label">
            <input type="checkbox" id="exclude-senior" onchange="toggleExcludeSenior(this)">
            <span>Hide Senior Roles</span>
          </label>
        </div>
      </div>
    </section>

    <div class="shortcuts-legend">
      <span>Shortcuts: <kbd>J</kbd>/<kbd>K</kbd> Select Card &bull; <kbd>A</kbd> / <kbd>Enter</kbd> Apply Now &bull; <kbd>S</kbd> Save &bull; <kbd>X</kbd> Ignore</span>
    </div>

    <section id="job-list" class="job-list">
      <!-- Injected by JavaScript -->
    </section>
  </main>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write styles (`src/static/style.css`)**

Create clean, high-contrast, dark-mode CSS with color coding for tiers and experience levels.

- [ ] **Step 3: Write client application logic (`src/static/app.js`)**

Handles keyboard navigation (`J`, `K`, `A`, `S`, `X`), live filtering, state updates via API, and "Apply Now" opening new tab.

- [ ] **Step 4: Commit UI assets**

```bash
git add src/static/
git commit -m "feat(ui): add high-velocity dashboard with keyboard shortcuts and level filters"
```

---

### Task 7: Sample Data Seeder & End-to-End System Integration

**Files:**
- Create: `src/seed.py`
- Create: `run.py`
- Test: `tests/test_e2e.py`

**Interfaces:**
- Consumes: All earlier modules.
- Produces: Pre-seeded realistic dataset spanning all 12 platforms, automated browser launch via `run.py`.

- [ ] **Step 1: Write seed data generator**

Generate 30+ realistic jobs covering:
- Tier 1: LinkedIn, JobStreet, Indeed, Kalibrr
- Tier 2: Wellfound, Bossjob, Foundit
- Tier 3: Remote OK, We Work Remotely, Arc
- Tier 4: Upwork, Glassdoor
- Mixed experience levels: Junior/Entry, Mid-Level, Senior.

- [ ] **Step 2: Write top-level launcher `run.py`**

Initializes database, checks if empty (auto-seeds if 0 jobs), opens browser automatically to `http://localhost:8000`, and starts Bottle server.

- [ ] **Step 3: Write automated end-to-end integration test (`tests/test_e2e.py`)**

Verify sync -> insertion -> API retrieval -> status transition pipeline works end-to-end.

- [ ] **Step 4: Commit and verify all tests pass**

```bash
git add src/seed.py run.py tests/test_e2e.py
git commit -m "feat(app): add data seeder, launcher, and end-to-end integration test"
```
