"""
Job Application Accelerator - Autonomous Local Background Runner
Runs 15-board scraping and email digest on a continuous timer (every 6 hours).
"""
import os
import sys
import time
import datetime

# Ensure project root in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from scripts.cloud_sync import run_cloud_sync
from scripts.daily_notifier import send_daily_email

SYNC_INTERVAL_HOURS = 6

def run_loop():
    print("=" * 60)
    print("🚀 Job Application Accelerator - Autonomous Background Runner")
    print(f"Cycle Interval: Every {SYNC_INTERVAL_HOURS} hours")
    print("Target Email: michael18ricafrente@gmail.com")
    print("=" * 60)

    while True:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{now_str}] Starting autonomous sync & scraping cycle...")
        try:
            run_cloud_sync()
        except Exception as e:
            print(f"[!] Sync error: {e}")

        print(f"[{now_str}] Compiling & dispatching daily digest...")
        try:
            result = send_daily_email()
            print(f"[✓] Daily email status: {result.get('message', 'Completed')}")
        except Exception as e:
            print(f"[!] Email error: {e}")

        next_run = datetime.datetime.now() + datetime.timedelta(hours=SYNC_INTERVAL_HOURS)
        print(f"\n[💤] Sleeping until next cycle at {next_run.strftime('%Y-%m-%d %H:%M:%S')} ({SYNC_INTERVAL_HOURS}h)...")
        time.sleep(SYNC_INTERVAL_HOURS * 3600)

if __name__ == "__main__":
    run_loop()
