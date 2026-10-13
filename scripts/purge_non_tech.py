import sqlite3
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.classifier import is_relevant_opportunity, is_non_tech, is_virtual_assistant, is_entry_training_va

def purge_irrelevant_jobs(db_path: str = "data/jobs.db"):
    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, company, platform, role_category FROM jobs")
    rows = cursor.fetchall()

    to_delete = []
    platform_breakdown = {}
    non_tech_count = 0
    va_non_training_count = 0
    other_unrelated_count = 0

    for r in rows:
        jid, title, company, platform, role_cat = r[0], r[1], r[2], r[3], r[4]
        
        # Check relevance: Must be verified tech OR entry/junior VA with training
        if not is_relevant_opportunity(title, "", allow_va_training=True):
            to_delete.append(jid)
            platform_breakdown[platform] = platform_breakdown.get(platform, 0) + 1
            if is_non_tech(title):
                non_tech_count += 1
            elif is_virtual_assistant(title) and not is_entry_training_va(title):
                va_non_training_count += 1
            else:
                other_unrelated_count += 1

    print(f"Total jobs evaluated: {len(rows)}")
    print(f"Identified for purging: {len(to_delete)}")
    print(f"  - Explicit non-tech blacklisted (Accountants, Medical, etc.): {non_tech_count}")
    print(f"  - Virtual Assistant without training: {va_non_training_count}")
    print(f"  - Other unrelated (Trades, Auto, Cider, Non-tech Admin): {other_unrelated_count}")
    print(f"Platform breakdown of purged records: {platform_breakdown}")

    if to_delete:
        cursor.executemany("DELETE FROM jobs WHERE id = ?", [(jid,) for jid in to_delete])
        conn.commit()
        # Vacuum database to reclaim space and optimize indexes
        cursor.execute("VACUUM")
        conn.commit()
        print(f"Successfully purged {len(to_delete)} irrelevant records from {db_path}.")

    cursor.execute("SELECT COUNT(*) FROM jobs")
    remaining = cursor.fetchone()[0]
    print(f"Remaining high-quality, verified opportunities in {db_path}: {remaining}")

    conn.close()

if __name__ == "__main__":
    purge_irrelevant_jobs()
