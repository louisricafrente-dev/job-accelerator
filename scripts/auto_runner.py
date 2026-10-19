"""Local scheduled scraping and Gmail notifications for the Job Accelerator."""
import os
import sys
import time
import datetime
import threading

# Ensure project root in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from src.aggregator import Aggregator
from src.database import get_user_setting
from scripts.daily_notifier import send_daily_email

DB_PATH = os.path.join(root_dir, "data", "jobs.db")
SYNC_INTERVAL_HOURS = max(1, min(24, int(os.environ.get("AUTO_SYNC_INTERVAL_HOURS", "6"))))
_runner_lock = threading.Lock()
_runner_thread = None

def _enabled(db_path: str) -> bool:
    return get_user_setting(db_path, "auto_sync_enabled", "1") not in ("0", "false", "False")

def run_cycle(db_path: str = DB_PATH) -> dict:
    """Run a local database sync and notify only when new jobs were added."""
    result = Aggregator(db_path=db_path).run_sync(force=True)
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] Sync {result.get('status')}: +{result.get('added', 0)} jobs")
    if result.get("added", 0) > 0:
        email_result = send_daily_email(db_path=db_path, dashboard_url="http://localhost:8000", new_jobs_count=result.get("added", 0))
        print(f"Email: {email_result.get('message', email_result.get('error', 'completed'))}")
    return result

def run_loop(db_path: str = DB_PATH):
    print("=" * 60)
    print("Job Application Accelerator - Local Background Runner")
    print(f"Cycle Interval: Every {SYNC_INTERVAL_HOURS} hours")
    print("New job notifications: michael18ricafrente@gmail.com")
    print("=" * 60)

    while True:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{now_str}] Starting autonomous sync & scraping cycle...")
        if _enabled(db_path):
            try:
                run_cycle(db_path)
            except Exception as e:
                print(f"[!] Sync error: {e}")
        else:
            print(f"[{now_str}] Automatic sync is turned off in dashboard settings.")

        next_run = datetime.datetime.now() + datetime.timedelta(hours=SYNC_INTERVAL_HOURS)
        print(f"\n[💤] Sleeping until next cycle at {next_run.strftime('%Y-%m-%d %H:%M:%S')} ({SYNC_INTERVAL_HOURS}h)...")
        deadline = time.monotonic() + SYNC_INTERVAL_HOURS * 3600
        while time.monotonic() < deadline:
            time.sleep(min(60, max(1, deadline - time.monotonic())))

def start_background_runner(db_path: str = DB_PATH) -> bool:
    """Start one local daemon runner when the local web app launches."""
    global _runner_thread
    with _runner_lock:
        if _runner_thread and _runner_thread.is_alive():
            return False
        _runner_thread = threading.Thread(target=run_loop, args=(db_path,), name="job-accelerator-auto-sync", daemon=True)
        _runner_thread.start()
        return True

if __name__ == "__main__":
    if "--once" in sys.argv:
        run_cycle(DB_PATH)
    else:
        run_loop(DB_PATH)
