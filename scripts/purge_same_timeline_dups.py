import sqlite3
import json
import os
import sys

def purge_same_timeline_duplicates(db_path: str = "data/jobs.db") -> int:
    if not os.path.exists(db_path):
        print(f"[!] Database file not found: {db_path}")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT lower(trim(company)) as co, lower(trim(title)) as ti, lower(trim(platform)) as pl,
               coalesce(date_posted, '') as dt, coalesce(location, '') as loc,
               count(*) as cnt, group_concat(id) as ids
        FROM jobs
        GROUP BY lower(trim(company)), lower(trim(title)), lower(trim(platform)), coalesce(date_posted, ''), coalesce(location, '')
        HAVING count(*) > 1
    """)
    groups = c.fetchall()

    if not groups:
        print("[✓] No same-timeline duplicate groups found in database.")
        conn.close()
        return 0

    status_priority = {"applied": 4, "saved": 3, "ignored": 2, "new": 1}
    deleted_count = 0

    print(f"[*] Found {len(groups)} same-timeline duplicate groups. Processing cleanup...")

    for g in groups:
        id_list = [int(x) for x in g["ids"].split(",")]
        placeholders = ",".join("?" for _ in id_list)
        c.execute(f"SELECT * FROM jobs WHERE id IN ({placeholders})", id_list)
        rows = [dict(r) for r in c.fetchall()]

        # Primary = highest priority status, then oldest (smallest) id
        rows.sort(key=lambda r: (status_priority.get(r["status"], 0), -r["id"]), reverse=True)
        primary = rows[0]
        duplicates = rows[1:]

        # Merge sources from duplicates into primary
        try:
            primary_sources = json.loads(primary["sources"]) if primary["sources"] else []
        except Exception:
            primary_sources = []
        if not primary_sources:
            primary_sources = [{"platform": primary["platform"], "url": primary["job_url"]}]

        seen_urls = {s.get("url", "").strip().lower() for s in primary_sources if s.get("url")}

        for d in duplicates:
            try:
                d_sources = json.loads(d["sources"]) if d["sources"] else []
            except Exception:
                d_sources = []
            if not d_sources:
                d_sources = [{"platform": d["platform"], "url": d["job_url"]}]
            for s in d_sources:
                u = s.get("url", "").strip().lower()
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    primary_sources.append(s)

        # Update primary with merged sources & any missing attributes
        merged_salary = primary["salary"] or next((d["salary"] for d in duplicates if d["salary"]), "")
        merged_notes = primary["notes"] or next((d["notes"] for d in duplicates if d["notes"]), "")

        c.execute("""
            UPDATE jobs
            SET sources = ?, salary = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (json.dumps(primary_sources), merged_salary, merged_notes, primary["id"]))

        # Delete duplicate rows
        dup_ids = [d["id"] for d in duplicates]
        delete_placeholders = ",".join("?" for _ in dup_ids)
        c.execute(f"DELETE FROM jobs WHERE id IN ({delete_placeholders})", dup_ids)
        deleted_count += len(dup_ids)

        print(f"  [Merged & Cleaned] Kept ID {primary['id']} ({primary['status']}), deleted duplicate IDs {dup_ids}: {primary['company']} - {primary['title']}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    db_file = sys.argv[1] if len(sys.argv) > 1 else "data/jobs.db"
    purge_same_timeline_duplicates(db_file)
