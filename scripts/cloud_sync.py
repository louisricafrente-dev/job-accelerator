"""
Cloud Sync CLI Runner for GitHub Actions / Scheduled Cron Jobs
Scrapes all 15 monitored job boards and updates the database automatically.
"""
import sys
import os
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from src.database import init_db, get_stats
from src.aggregator import Aggregator

def run_cloud_sync():
    db_path = os.environ.get("DB_PATH", os.path.join(root_dir, "data", "jobs.db"))
    print(f"[*] Initializing Cloud Sync targeting database: {db_path}")
    init_db(db_path)

    before_stats = get_stats(db_path)
    print(f"[*] Pre-sync database stats: {before_stats['total']} total jobs ({before_stats['new']} new)")

    aggregator = Aggregator(db_path=db_path)
    print(f"[*] Starting multi-board sync across {len(aggregator.connectors)} platforms...")
    start_time = time.time()

    stats = aggregator.run_sync()
    duration = time.time() - start_time

    # Run safety purge to maintain 100% clean tech & training-VA database
    try:
        from scripts.purge_non_tech import purge_irrelevant_jobs
        purge_irrelevant_jobs(db_path)
        from scripts.purge_same_timeline_dups import purge_same_timeline_duplicates
        purge_same_timeline_duplicates(db_path)
    except Exception as e:
        print(f"[*] Hygiene post-check notice: {e}")

    after_stats = get_stats(db_path)
    print("=" * 60)
    print(f"[✓] Sync finished in {duration:.2f} seconds!")
    print(f"[+] Newly Discovered Jobs: +{stats.get('added', 0)}")
    print(f"[~] Existing / Duplicates Skipped: {stats.get('skipped', 0)}")
    print(f"[*] Post-sync database stats: {after_stats['total']} total jobs ({after_stats['new']} new)")
    print("=" * 60)

    # Print breakdown by platform
    print("\nPlatform Breakdown:")
    for platform, count in stats.get("platforms", {}).items():
        print(f"  - {platform}: {count} jobs")

if __name__ == "__main__":
    run_cloud_sync()
