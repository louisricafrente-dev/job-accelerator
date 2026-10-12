import sqlite3
import json
import os
import re
from src.models import normalize_date

def run_migration(db_path: str = "data/jobs.db") -> None:
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Ensure sources column exists
    cur.execute("PRAGMA table_info(jobs);")
    cols = {col[1] for col in cur.fetchall()}
    if "sources" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN sources TEXT DEFAULT '[]';")
        conn.commit()

    # 2. Normalize date_posted for all rows
    cur.execute("SELECT id, date_posted FROM jobs;")
    rows = cur.fetchall()
    updated_dates = 0
    for r in rows:
        raw_date = r["date_posted"]
        norm = normalize_date(raw_date) if raw_date else ""
        if norm != raw_date:
            cur.execute("UPDATE jobs SET date_posted = ? WHERE id = ?", (norm, r["id"]))
            updated_dates += 1
    conn.commit()
    print(f"Normalized date_posted on {updated_dates} rows.")

    # 3. Initialize sources for rows where sources is empty/invalid
    cur.execute("SELECT id, platform, job_url, sources FROM jobs;")
    rows = cur.fetchall()
    initialized_sources = 0
    for r in rows:
        raw_src = r["sources"]
        needs_init = False
        if not raw_src or raw_src.strip() in ("", "[]"):
            needs_init = True
        else:
            try:
                parsed = json.loads(raw_src)
                if not isinstance(parsed, list) or len(parsed) == 0:
                    needs_init = True
            except Exception:
                needs_init = True
        if needs_init:
            initial = json.dumps([{"platform": r["platform"], "url": r["job_url"]}])
            cur.execute("UPDATE jobs SET sources = ? WHERE id = ?", (initial, r["id"]))
            initialized_sources += 1
    conn.commit()
    print(f"Initialized sources on {initialized_sources} rows.")

    # 4. Find all duplicate groups where lower(trim(company)) and lower(trim(title)) have > 1 row
    cur.execute("""
        SELECT lower(trim(company)) as comp, lower(trim(title)) as titl, count(*) as cnt
        FROM jobs
        GROUP BY lower(trim(company)), lower(trim(title))
        HAVING cnt > 1;
    """)
    dup_groups = cur.fetchall()
    merged_sets = 0
    deleted_rows = 0

    for grp in dup_groups:
        comp, titl = grp["comp"], grp["titl"]
        cur.execute("""
            SELECT * FROM jobs
            WHERE lower(trim(company)) = ? AND lower(trim(title)) = ?
            ORDER BY 
              CASE WHEN status IN ('applied', 'saved') THEN 1 ELSE 2 END,
              id ASC;
        """, (comp, titl))
        group_rows = [dict(row) for row in cur.fetchall()]
        if len(group_rows) <= 1:
            continue

        canonical = group_rows[0]
        duplicate_rows = group_rows[1:]

        # Merge sources
        all_sources = []
        try:
            all_sources = json.loads(canonical.get("sources") or "[]")
        except Exception:
            all_sources = []
        if not all_sources:
            all_sources = [{"platform": canonical["platform"], "url": canonical["job_url"]}]

        merged_salary = canonical.get("salary") or ""
        merged_date = canonical.get("date_posted") or ""
        merged_notes = canonical.get("notes") or ""
        merged_status = canonical.get("status") or "new"
        merged_stage = canonical.get("pipeline_stage") or "applied"

        for dup in duplicate_rows:
            dup_sources = []
            try:
                dup_sources = json.loads(dup.get("sources") or "[]")
            except Exception:
                dup_sources = []
            if not dup_sources:
                dup_sources = [{"platform": dup["platform"], "url": dup["job_url"]}]

            for s in dup_sources:
                if not any(
                    existing.get("platform", "").lower() == s.get("platform", "").lower()
                    or existing.get("url") == s.get("url")
                    for existing in all_sources
                ):
                    all_sources.append(s)

            if not merged_salary and dup.get("salary"):
                merged_salary = dup["salary"]
            if not merged_date and dup.get("date_posted"):
                merged_date = dup["date_posted"]
            if not merged_notes and dup.get("notes"):
                merged_notes = dup["notes"]
            if merged_status not in ("applied", "saved") and dup.get("status") in ("applied", "saved"):
                merged_status = dup["status"]
                merged_stage = dup.get("pipeline_stage") or "applied"

        # Update canonical row
        cur.execute("""
            UPDATE jobs
            SET sources = ?, salary = ?, date_posted = ?, notes = ?, status = ?, pipeline_stage = ?
            WHERE id = ?;
        """, (json.dumps(all_sources), merged_salary, merged_date, merged_notes, merged_status, merged_stage, canonical["id"]))

        # Delete duplicate rows
        dup_ids = [dup["id"] for dup in duplicate_rows]
        cur.execute(f"DELETE FROM jobs WHERE id IN ({','.join('?' * len(dup_ids))})", dup_ids)
        merged_sets += 1
        deleted_rows += len(dup_ids)

    conn.commit()
    conn.close()
    print(f"Consolidated {merged_sets} duplicate sets. Removed {deleted_rows} redundant duplicate rows.")

if __name__ == "__main__":
    run_migration()
