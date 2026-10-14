"""
Automated 6-Hour Sync and Email Dispatcher
1. Triggers multi-board scraping across all 15 platforms in MAX MODE.
2. Updates SQLite database with newly harvested opportunities.
3. Compiles the latest matches and dispatches the HTML email digest to michael18ricafrente@gmail.com.
"""
import os
import sys

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from src.aggregator import Aggregator
from scripts.daily_notifier import send_daily_email

def main():
    db_path = os.path.join(root_dir, "data", "jobs.db")
    print(f"[*] Starting MAX MODE 15-Board Sync on database: {db_path}...")
    aggregator = Aggregator(db_path=db_path)
    sync_result = aggregator.run_sync(force=True)
    
    print(f"[✓] Sync complete: +{sync_result.get('added', 0)} new jobs, {sync_result.get('skipped', 0)} existing updated.")
    print(f"[*] Platforms scraped: {sync_result.get('platforms', {})}")

    print(f"[*] Compiling digest and sending email to michael18ricafrente@gmail.com...")
    email_result = send_daily_email(db_path=db_path)
    print(f"[✓] Email result: {email_result}")

if __name__ == "__main__":
    main()
