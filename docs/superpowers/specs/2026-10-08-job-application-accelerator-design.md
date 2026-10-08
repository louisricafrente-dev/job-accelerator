# Job Application Accelerator - Design Specification

**Date:** 2026-10-08  
**Status:** Validated Design  
**Target Directory:** `C:\Users\PC\.gemini\antigravity\scratch\job-accelerator`

---

## 1. Executive Summary & Goals

The **Job Application Accelerator** is a local-first system designed to aggregate job listings across 12 specific platforms into a single unified workspace. It eliminates repetitive manual searching across disparate job boards, deduplicates postings, classifies experience levels (Entry/Junior, Mid, Senior), and provides a high-velocity web dashboard equipped with 1-click direct apply links, keyboard shortcuts, and application status tracking.

### Success Criteria
- **High-Velocity Applying:** Reduces time spent discovering, filtering, and opening relevant jobs across 12 platforms by at least 80%.
- **Zero Duplicate Applications:** Tracks application history in a local database so applied or ignored listings are never duplicated or reset.
- **Precision Filtering:** Instant filtering by Target Role (Web/Software Dev vs Data/AI/ML), Experience Level (Junior/Entry, Mid, Senior), Tier, and Work Setup (Remote/Hybrid PH/Worldwide).
- **Resilient Aggregation:** Connector isolation ensures that failure or rate-limiting on one platform never halts the synchronization of the other 11 platforms.

---

## 2. Target Platforms & Priority Tiers

The system aggregates from 12 platforms partitioned into four operational tiers:

| Tier | Priority Focus | Platforms | Extraction Strategy |
| :--- | :--- | :--- | :--- |
| **Tier 1** | Apply Heavily (PH & Core Global) | **LinkedIn, JobStreet, Indeed, Kalibrr** | `jobspy` (LinkedIn, Indeed) + REST endpoints (Kalibrr, JobStreet) |
| **Tier 2** | High Value PH & Startup | **Wellfound, Bossjob, Foundit** | Public REST / GraphQL search endpoints & light web fetchers |
| **Tier 3** | Remote / Global Tech | **Remote OK, We Work Remotely, Arc** | Public JSON APIs (`remoteok.com/api`) & official RSS feeds |
| **Tier 4** | Backup / Freelance & Reviews | **Upwork, Glassdoor** | RSS search feeds (Upwork) + `jobspy` (Glassdoor) |

---

## 3. System Architecture & Components

```
┌────────────────────────────────────────────────────────────────────────┐
│                          User Interface                                │
│       Local Web Dashboard (http://localhost:8000)                      │
│   • Instant Filter (Role, Level, Tier, Setup)                          │
│   • Power Keyboard Shortcuts (J, K, A, S, X)                           │
│   • 1-Click "Apply Now" (Opens browser tab & tracks status)            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST
┌───────────────────────────────────▼────────────────────────────────────┐
│                    Application Server (FastAPI / Starlette)             │
│   • GET  /api/jobs (Filterable job feed with pagination/search)        │
│   • POST /api/jobs/{id}/status (Update status: applied, saved, ignored) │
│   • POST /api/sync (Triggers concurrent multi-platform sync)           │
│   • GET  /api/stats (Live counts: new, saved, applied, by level)       │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │                                 │
┌──────────────────▼───────────────┐ ┌───────────────▼───────────────────┐
│       SQLite Database (`jobs.db`)│ │     Sync & Aggregation Engine     │
│   • WAL Mode for high concurrency│ │   • ThreadPool concurrent workers │
│   • Unique deduplication index   │ │   • Clean URL & SHA-256 Hasher    │
│   • Preserves user application   │ │   • Auto-tagger & Level Classifier│
│     statuses across sync cycles  │ │   • Connector Isolation & Fallback│
└──────────────────────────────────┘ └─────────────────┬─────────────────┘
                                                       │
                 ┌─────────────────────────────────────▼────────┐
                 │          Modular Connector Suite             │
                 │ ├─ JobSpy Connector (LinkedIn, Indeed, GD)   │
                 │ ├─ Remote APIs (RemoteOK, WWR, Arc)          │
                 │ ├─ Local PH Endpoints (Kalibrr, Bossjob, etc)│
                 │ └─ Niche & Freelance (Wellfound, Upwork)     │
                 └──────────────────────────────────────────────┘
```

---

## 4. Data Model & SQLite Schema

Stored locally in `data/jobs.db` with `PRAGMA journal_mode=WAL` enabled for non-blocking concurrent reads and writes.

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_hash TEXT UNIQUE NOT NULL,      -- SHA-256(platform + normalized_company + normalized_title + clean_url)
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    platform TEXT NOT NULL,               -- e.g. 'LinkedIn', 'JobStreet', 'Remote OK'
    tier INTEGER NOT NULL,                -- 1, 2, 3, or 4
    job_url TEXT NOT NULL,
    salary TEXT,                          -- Raw or parsed compensation string
    role_category TEXT NOT NULL,          -- 'Web/Software Dev' | 'Data/AI/ML' | 'Both'
    experience_level TEXT NOT NULL,       -- 'Junior / Entry' | 'Mid-Level' | 'Senior / Lead' | 'Unspecified'
    date_posted TEXT,                     -- Standardized ISO-8601 or relative date
    status TEXT NOT NULL DEFAULT 'new',   -- 'new', 'saved', 'applied', 'ignored'
    notes TEXT,                           -- Optional user notes (e.g., date applied, interview notes)
    applied_at DATETIME,                  -- Timestamp when user marked as applied
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_level ON jobs(experience_level);
CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(role_category);
CREATE INDEX IF NOT EXISTS idx_jobs_tier ON jobs(tier);
```

### Preservation Guarantees
All sync operations execute:
```sql
INSERT INTO jobs (dedup_hash, title, company, location, platform, tier, job_url, salary, role_category, experience_level, date_posted, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
ON CONFLICT(dedup_hash) DO NOTHING;
```
If a job was previously marked `applied` or `ignored`, its status is untouched.

---

## 5. Classification Engine (Role & Experience Level)

### 5.1 Experience Level Classifier
Runs automatically during the normalization step before database insertion:
- **`Junior / Entry` Keywords:** `junior`, `jr.`, `jr `, `entry level`, `entry-level`, `graduate`, `fresh grad`, `associate`, `intern`, `internship`, `0-1 year`, `0-2 years`, `trainee`.
- **`Senior / Lead` Keywords:** `senior`, `sr.`, `sr `, `lead`, `principal`, `architect`, `staff`, `head of`, `director`, `vp`, `5+ years`, `7+ years`, `manager`.
- **`Mid-Level` Keywords:** `mid-level`, `mid level`, `intermediate`, `2-4 years`, `3-5 years`, or postings having no Junior/Senior qualifiers.
- **Fallback:** `Unspecified` if no clear match is found.

### 5.2 Role Category Classifier
- **`Web/Software Dev` Keywords:** `frontend`, `front-end`, `backend`, `back-end`, `full stack`, `fullstack`, `software engineer`, `web developer`, `python developer`, `react`, `node`, `javascript`, `typescript`, `golang`, `java`, `c#`, `.net`.
- **`Data/AI/ML` Keywords:** `data analyst`, `data analytics`, `data engineer`, `machine learning`, `ml engineer`, `ai engineer`, `data scientist`, `nlp`, `deep learning`, `computer vision`, `bi developer`, `business intelligence`, `analytics engineer`.
- If a post matches both sets (e.g. "Full Stack Engineer - AI Applications"), it is classified as `'Both'`.

---

## 6. Dashboard User Interface & Interaction Workflow

### 6.1 Layout
1. **Top Bar:**
   - Stats summary: Total New, Total Saved, Total Applied, Jobs Discovered Today.
   - Sync Trigger: "⚡ Sync Jobs" button with active progress feedback.
2. **Filter & Control Bar:**
   - **Search Input:** Real-time client-side filter by keyword, company, or tech stack.
   - **Role Tabs:** `[All Roles]` | `[Web & Software Dev]` | `[Data & AI/ML]`.
   - **Experience Level Selector:** `[All Levels]` | `[🟢 Junior / Entry-Level]` | `[🔵 Mid-Level]` | `[🟣 Senior / Lead]`.
   - **Senior Suppression Toggle:** Quick checkbox to *"Exclude Senior Postings"* when focusing on Entry/Mid positions.
   - **Tier Filter:** Dropdown to isolate specific tiers (`Tier 1 Only`, `Tier 3 Remote Only`, etc.).
   - **Status Views:** `[Inbox (New)]` (default) | `[⭐ Saved]` | `[✅ Applied]` | `[✕ Archive/Ignored]`.
3. **Job Cards:**
   - Header with Title, Company, and Location badge.
   - Badges for Platform, Tier, and Experience Level with distinct visual color coding.
   - Salary display (if detected) and Date Posted.
   - Action buttons:
     - `🚀 Apply Now`: Opens target URL in a new tab.
     - `✅ Applied`: Moves card to Applied status with current date.
     - `⭐ Save`: Saves for customized application later.
     - `✕ Ignore`: Hides from Inbox immediately.

### 6.2 High-Speed Keyboard Navigation ("Power Mode")
- `J` / `K` (or Down/Up arrow): Select next / previous job card.
- `A` or `Enter`: Open the apply link in new browser tab and trigger quick prompt to mark applied.
- `S`: Save job card.
- `X` / `Delete`: Ignore / dismiss job card.

---

## 7. Connector Specifications & Resilience

### 7.1 Connectors Matrix
1. **LinkedIn / Indeed / Glassdoor (`jobspy_connector`):**
   - Implemented via `python-jobspy`.
   - Fetches target queries for location `Philippines` and `Remote`.
2. **Remote OK (`remoteok_connector`):**
   - Direct HTTP call to `https://remoteok.com/api` with custom User-Agent.
3. **We Work Remotely (`wwr_connector`):**
   - Parses RSS feeds: `https://weworkremotely.com/categories/remote-programming-jobs.rss` and `.../data-science-jobs.rss`.
4. **Arc (`arc_connector`):**
   - Fetches developer job search listings from public endpoints.
5. **Kalibrr (`kalibrr_connector`):**
   - Consumes public search endpoint `https://www.kalibrr.com/api/job_board/search`.
6. **Bossjob (`bossjob_connector`):**
   - Consumes public mobile/web search API `https://bossjob.ph/api`.
7. **JobStreet & Foundit (`ph_connectors`):**
   - Direct query parsers for public job listings.
8. **Upwork & Wellfound (`backup_connectors`):**
   - Upwork public search RSS query for software/data jobs.

### 7.2 Fault Isolation
- Every connector runs inside an isolated execution thread with dedicated timeout (15s).
- Catch-all exception handling prevents any connector failure from affecting peer connectors.
- Results from healthy connectors are committed to SQLite immediately upon completion.

---

## 8. Verification & Testing Strategy

1. **Unit & Smoke Tests (`tests/test_connectors.py`):**
   - Test each connector's health and schema compliance independently.
2. **Classification Logic Tests (`tests/test_classifier.py`):**
   - Test keywords accurately categorize experience levels (e.g. "Junior Software Engineer", "Senior Lead Architect") and role domains.
3. **Data Seeder (`seed_sample_data.py`):**
   - Generates realistic test data across all 12 platforms and all 3 experience tiers for instant visual verification of the dashboard without waiting for network scrapes.
4. **End-to-End Test (`tests/test_e2e_flow.py`):**
   - Verify: Sync -> DB Insertion -> Status Update via API -> Filter verification on Web Dashboard.
