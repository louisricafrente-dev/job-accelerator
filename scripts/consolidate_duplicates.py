import sys
import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta

# Ensure project root in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.models import normalize_date, is_within_15_days, clean_url
from src.database import normalize_company, normalize_title, is_compatible_location

def consolidate_database(db_path: str = "data/jobs.db"):
    if not os.path.exists(db_path):
        print(f"[!] Database file not found: {db_path}")
        return

    print(f"[*] Opening database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Step 1: Normalize dates across all rows
    print("[*] Step 1: Normalizing date_posted across all records...")
    c.execute("SELECT id, date_posted FROM jobs")
    all_date_rows = c.fetchall()
    updated_dates = 0
    for r in all_date_rows:
        raw_dt = r["date_posted"]
        if raw_dt:
            norm = normalize_date(raw_dt)
            if norm and norm != raw_dt:
                c.execute("UPDATE jobs SET date_posted = ? WHERE id = ?", (norm, r["id"]))
                updated_dates += 1
    conn.commit()
    print(f"[OK] Normalized date_posted on {updated_dates} records.")

    # Step 2: Remove stale (>15d) listings in 'new' status to eliminate clutter
    today_utc = datetime.now(timezone.utc)
    cutoff_15d = (today_utc - timedelta(days=15)).strftime("%Y-%m-%d")
    print(f"[*] Step 2: Checking stale (>15d, before {cutoff_15d}) listings in 'new' status...")
    c.execute("SELECT count(*) FROM jobs WHERE status = 'new' AND date_posted != '' AND date_posted < ?", (cutoff_15d,))
    stale_count = c.fetchone()[0]
    if stale_count > 0:
        c.execute("DELETE FROM jobs WHERE status = 'new' AND date_posted != '' AND date_posted < ?", (cutoff_15d,))
        conn.commit()
        print(f"[OK] Purged {stale_count} stale (>15d) 'new' listings. (Applied/Saved jobs were safely preserved).")
    else:
        print("[OK] No stale 'new' listings to purge.")

    # Step 3: Find and merge cross-platform and duplicate jobs (Indeed, Glassdoor, etc.)
    print("[*] Step 3: Detecting and consolidating duplicate / cross-board listings...")
    c.execute("SELECT id, company, title, platform, location, salary, date_posted, sources, status, notes, pipeline_stage, job_url, dedup_hash FROM jobs ORDER BY id ASC")
    all_jobs = [dict(r) for r in c.fetchall()]
    print(f"[*] Processing {len(all_jobs)} total listings for clustering...")

    # Group by normalized company & normalized title
    clusters = {}
    for j in all_jobs:
        norm_co = normalize_company(j["company"]) or j["company"].strip().lower()
        norm_ti = normalize_title(j["title"]) or j["title"].strip().lower()
        key = (norm_co, norm_ti)
        clusters.setdefault(key, []).append(j)

    status_priority = {"applied": 4, "saved": 3, "new": 2, "ignored": 1}
    consolidated_groups = 0
    removed_rows = 0

    for key, group in clusters.items():
        if len(group) <= 1:
            continue

        # Sub-cluster by compatible locations
        sub_clusters = []
        for job in group:
            placed = False
            for sub in sub_clusters:
                # Check if compatible with the primary of this sub-cluster
                if is_compatible_location(sub[0]["location"], job["location"]):
                    sub.append(job)
                    placed = True
                    break
            if not placed:
                sub_clusters.append([job])

        for sub in sub_clusters:
            if len(sub) <= 1:
                continue

            # Sort sub: prefer higher status (applied > saved > new > ignored), then newest date_posted, then smallest id
            sub.sort(key=lambda r: (
                status_priority.get(r["status"], 0),
                r["date_posted"] or "",
                -r["id"]
            ), reverse=True)

            canonical = sub[0]
            duplicates = sub[1:]

            # Merge sources
            merged_sources = []
            try:
                merged_sources = json.loads(canonical["sources"]) if canonical["sources"] else []
            except Exception:
                merged_sources = []
            if not merged_sources:
                merged_sources = [{"platform": canonical["platform"], "url": canonical["job_url"]}]

            seen_urls = {clean_url(s.get("url", "")) for s in merged_sources if s.get("url")}
            seen_platforms = {s.get("platform", "").lower() for s in merged_sources if s.get("platform")}

            for d in duplicates:
                d_sources = []
                try:
                    d_sources = json.loads(d["sources"]) if d["sources"] else []
                except Exception:
                    d_sources = []
                if not d_sources:
                    d_sources = [{"platform": d["platform"], "url": d["job_url"]}]

                for s in d_sources:
                    u_clean = clean_url(s.get("url", ""))
                    p_clean = s.get("platform", "").lower()
                    if u_clean and u_clean not in seen_urls:
                        seen_urls.add(u_clean)
                        seen_platforms.add(p_clean)
                        merged_sources.append(s)
                    elif p_clean not in seen_platforms:
                        seen_platforms.add(p_clean)
                        merged_sources.append(s)

            # Best attributes
            merged_salary = canonical["salary"] or next((d["salary"] for d in duplicates if d["salary"]), "")
            merged_notes = canonical["notes"] or next((d["notes"] for d in duplicates if d["notes"]), "")
            
            # Newest date
            all_dates = [r["date_posted"] for r in sub if r.get("date_posted")]
            merged_date = max(all_dates) if all_dates else canonical["date_posted"]

            # Update canonical row
            c.execute("""
                UPDATE jobs
                SET sources = ?, salary = ?, date_posted = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (json.dumps(merged_sources), merged_salary, merged_date, merged_notes, canonical["id"]))

            # Delete redundant duplicate records
            dup_ids = [d["id"] for d in duplicates]
            c.execute(f"DELETE FROM jobs WHERE id IN ({','.join('?' * len(dup_ids))})", dup_ids)

            consolidated_groups += 1
            removed_rows += len(dup_ids)
            print(f"  [Merged] ID {canonical['id']} ({canonical['platform']}): {canonical['company']} - {canonical['title']} -> Platforms: {[s['platform'] for s in merged_sources]} (deleted IDs: {dup_ids})")

    conn.commit()
    print(f"\n[OK] Consolidation Complete: Merged {consolidated_groups} duplicate groups and removed {removed_rows} redundant rows.")

    c.execute("SELECT count(*) FROM jobs")
    final_count = c.fetchone()[0]
    print(f"[*] Final remaining jobs in database: {final_count}")
    conn.close()

if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "data/jobs.db"
    consolidate_database(db)
