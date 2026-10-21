import sqlite3
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.classifier import is_relevant_opportunity, is_non_tech, is_virtual_assistant, is_entry_training_va

def purge_irrelevant_jobs(db_path: str = "data/jobs.db", commit: bool = True):
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path)

    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, company, platform, role_category, status, description FROM jobs")
    rows = cursor.fetchall()

    to_delete = []
    platform_breakdown = {}
    non_tech_count = 0
    va_non_entry_count = 0
    purged_samples = []

    for r in rows:
        jid, title, company, platform, role_cat, status, desc = r[0], r[1], r[2], r[3], r[4], r[5], r[6]

        # NEVER purge applied jobs (historical tracking record)
        if status == "applied":
            continue

        desc_str = desc or ""

        # 1. Non-tech check (Civil, Mechanical, Electrical, Trades, Medical, Sales, etc.)
        if is_non_tech(title, desc_str):
            to_delete.append(jid)
            platform_breakdown[platform] = platform_breakdown.get(platform, 0) + 1
            non_tech_count += 1
            if len(purged_samples) < 25:
                purged_samples.append((platform, title, company, "Non-Tech Engineering / Trades / Sales / Admin"))
            continue

        # 2. Virtual assistant check: must strictly be entry-level or training
        if is_virtual_assistant(title, desc_str):
            if not is_entry_training_va(title, desc_str):
                to_delete.append(jid)
                platform_breakdown[platform] = platform_breakdown.get(platform, 0) + 1
                va_non_entry_count += 1
                if len(purged_samples) < 25:
                    purged_samples.append((platform, title, company, "Non-Entry / Senior / Executive VA"))
            continue

    print(f"Total jobs evaluated: {len(rows)}")
    print(f"Identified for purging: {len(to_delete)}")
    print(f"  - Non-Tech Engineering / Sales / Medical / Trades: {non_tech_count}")
    print(f"  - Non-Entry / Senior / Executive VA: {va_non_entry_count}")
    print(f"Platform breakdown: {platform_breakdown}")

    print("\nSample records purged:")
    for p, t, c, reason in purged_samples:
        print(f"  [{p}] {t} @ {c} -> {reason}")

    if commit and to_delete:
        cursor.executemany("DELETE FROM jobs WHERE id = ?", [(jid,) for jid in to_delete])
        conn.commit()
        # Vacuum database to reclaim space and optimize indexes
        cursor.execute("VACUUM")
        conn.commit()
        print(f"\n[COMMITTED] Successfully purged {len(to_delete)} records from {db_path}.")
        cursor.execute("SELECT COUNT(*) FROM jobs")
        remaining = cursor.fetchone()[0]
        print(f"Remaining active, verified opportunities in {db_path}: {remaining}")
    elif not commit:
        print("\n[DRY RUN ONLY] No records deleted yet. Pass commit=True to delete.")

    conn.close()

if __name__ == "__main__":
    purge_irrelevant_jobs(commit=True)
