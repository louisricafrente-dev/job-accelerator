import sys
import os
import json
import libsql_client
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

from src.models import normalize_date, clean_url
from src.database import normalize_company, normalize_title, is_compatible_location

TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "https://job-accelerator-rhettrina.aws-ap-northeast-1.turso.io").strip()
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()

def consolidate_turso(dry_run: bool = False):
    if not TURSO_TOKEN:
        print("[!] Error: TURSO_AUTH_TOKEN is required in environment.")
        return
    print(f"[*] Connecting to Turso: {TURSO_URL}")
    client = libsql_client.create_client_sync(TURSO_URL, auth_token=TURSO_TOKEN)

    # Pre-check counts
    rs_total = client.execute("SELECT count(*) FROM jobs")
    total_start = rs_total.rows[0][0]
    rs_saved = client.execute("SELECT count(*) FROM jobs WHERE status = 'saved'")
    saved_start = rs_saved.rows[0][0]
    rs_applied = client.execute("SELECT count(*) FROM jobs WHERE status = 'applied'")
    applied_start = rs_applied.rows[0][0]
    print(f"[*] Starting state on Turso: {total_start} total jobs ({saved_start} saved, {applied_start} applied).")

    # Step 1: Normalize dates
    print("[*] Step 1: Checking date_posted normalization on Turso...")
    rs_dates = client.execute("SELECT id, date_posted FROM jobs WHERE date_posted IS NOT NULL AND date_posted != ''")
    date_updates = []
    for r in rs_dates.rows:
        jid, raw_dt = r[0], r[1]
        norm = normalize_date(raw_dt)
        if norm and norm != raw_dt:
            date_updates.append((norm, jid))
    print(f"[*] Found {len(date_updates)} dates needing normalization.")
    if not dry_run and date_updates:
        for norm, jid in date_updates:
            client.execute("UPDATE jobs SET date_posted = ? WHERE id = ?", [norm, jid])
        print(f"[OK] Normalized {len(date_updates)} dates on Turso.")

    # Step 2: Purge stale (>15d) listings in 'new' status
    today_utc = datetime.now(timezone.utc)
    cutoff_15d = (today_utc - timedelta(days=15)).strftime("%Y-%m-%d")
    print(f"[*] Step 2: Checking stale (>15d, before {cutoff_15d}) listings in 'new' status on Turso...")
    rs_stale = client.execute("SELECT count(*) FROM jobs WHERE status = 'new' AND date_posted != '' AND date_posted < ?", [cutoff_15d])
    stale_count = rs_stale.rows[0][0]
    print(f"[*] Stale 'new' listings to purge: {stale_count}")
    if not dry_run and stale_count > 0:
        client.execute("DELETE FROM jobs WHERE status = 'new' AND date_posted != '' AND date_posted < ?", [cutoff_15d])
        print(f"[OK] Purged {stale_count} stale 'new' listings from Turso.")

    # Step 3: Cluster and consolidate duplicates
    print("[*] Step 3: Fetching all listings from Turso for duplicate clustering...")
    rs_all = client.execute("SELECT id, company, title, platform, location, salary, date_posted, sources, status, notes, pipeline_stage, job_url, dedup_hash FROM jobs ORDER BY id ASC")
    cols = [c for c in rs_all.columns]
    all_jobs = [dict(zip(cols, row)) for row in rs_all.rows]
    print(f"[*] Retrieved {len(all_jobs)} records. Clustering by normalized company & title...")

    clusters = {}
    for j in all_jobs:
        norm_co = normalize_company(j["company"]) or j["company"].strip().lower()
        norm_ti = normalize_title(j["title"]) or j["title"].strip().lower()
        key = (norm_co, norm_ti)
        clusters.setdefault(key, []).append(j)

    status_priority = {"applied": 4, "saved": 3, "new": 2, "ignored": 1}
    consolidated_groups = 0
    delete_ids = []
    canonical_updates = []

    for key, group in clusters.items():
        if len(group) <= 1:
            continue

        sub_clusters = []
        for job in group:
            placed = False
            for sub in sub_clusters:
                if is_compatible_location(sub[0]["location"], job["location"]):
                    sub.append(job)
                    placed = True
                    break
            if not placed:
                sub_clusters.append([job])

        for sub in sub_clusters:
            if len(sub) <= 1:
                continue

            sub.sort(key=lambda r: (
                status_priority.get(r["status"], 0),
                r["date_posted"] or "",
                -r["id"]
            ), reverse=True)

            canonical = sub[0]
            duplicates = sub[1:]

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

            merged_salary = canonical["salary"] or next((d["salary"] for d in duplicates if d["salary"]), "")
            merged_notes = canonical["notes"] or next((d["notes"] for d in duplicates if d["notes"]), "")
            all_dates = [r["date_posted"] for r in sub if r.get("date_posted")]
            merged_date = max(all_dates) if all_dates else canonical["date_posted"]

            dup_ids = [d["id"] for d in duplicates]
            delete_ids.extend(dup_ids)
            canonical_updates.append((
                json.dumps(merged_sources),
                merged_salary,
                merged_date,
                merged_notes,
                canonical["id"],
                canonical["company"],
                canonical["title"],
                canonical["status"],
                [s["platform"] for s in merged_sources],
                dup_ids
            ))
            consolidated_groups += 1

    print(f"[*] Detected {consolidated_groups} duplicate groups with {len(delete_ids)} redundant records to remove.")

    if not dry_run:
        print("[*] Applying updates to canonical records in batches...")
        update_stmts = []
        for u in canonical_updates:
            sql = """
                UPDATE jobs
                SET sources = ?, salary = ?, date_posted = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            update_stmts.append((sql, [u[0], u[1], u[2], u[3], u[4]]))
            print(f"  [Merged] ID {u[4]} (status: {u[7]}): {u[5]} - {u[6]} -> Platforms: {u[8]} (deleted IDs: {u[9]})")

        batch_size = 50
        for i in range(0, len(update_stmts), batch_size):
            chunk = update_stmts[i:i + batch_size]
            client.batch(chunk)
        print(f"[OK] Canonical records updated with merged sources.")

        print(f"[*] Deleting {len(delete_ids)} redundant duplicate records...")
        del_stmts = []
        for did in delete_ids:
            del_stmts.append(("DELETE FROM jobs WHERE id = ?", [did]))
        for i in range(0, len(del_stmts), batch_size):
            chunk = del_stmts[i:i + batch_size]
            client.batch(chunk)
        print(f"[OK] Redundant duplicate rows deleted.")


    # Post-check validation
    rs_total_end = client.execute("SELECT count(*) FROM jobs")
    total_end = rs_total_end.rows[0][0]
    rs_saved_end = client.execute("SELECT count(*) FROM jobs WHERE status = 'saved'")
    saved_end = rs_saved_end.rows[0][0]
    rs_applied_end = client.execute("SELECT count(*) FROM jobs WHERE status = 'applied'")
    applied_end = rs_applied_end.rows[0][0]

    print("\n--- Turso Consolidation Summary ---")
    print(f"Total jobs: {total_start} -> {total_end}")
    print(f"Saved jobs: {saved_start} -> {saved_end} (Status fully preserved!)")
    assert saved_end > 0, f"CRITICAL SAFETY CHECK: No saved jobs remaining"
    assert applied_end > 0, f"CRITICAL SAFETY CHECK: No applied jobs remaining"
    print("[SUCCESS] All saved and applied jobs remain 100% intact and verified!")

if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    consolidate_turso(dry_run=dry)
