"""
Cloud Cron Scraper Runner (GitHub Actions)
Executes scheduled multi-board job scrapes in the cloud with strict Local-First priority.
Safely yields if candidate PC local worker is actively running or acknowledging commands.
Records full telemetry, sync_status, and daily_scrape_day in Turso Database.
"""
import os
import sys
import time
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is available in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Load local .env variables if present
env_file = os.path.join(root_dir, ".env")
if os.path.exists(env_file):
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

from src.database import (
    init_db,
    get_stats,
    get_user_setting,
    set_user_setting,
    is_turso_active
)
from src.daily_schedule import day as get_manila_day
from src import execution_inbox as inbox
from src.aggregator import Aggregator

def run():
    force = "--force" in sys.argv or os.environ.get("FORCE_SYNC") == "1"
    db_path = "data/jobs.db"

    print("=" * 60)
    print("      ☁️ Job Accelerator - Scheduled Cloud Cron Runner")
    print("=" * 60)

    if not is_turso_active(db_path):
        print("[!] ERROR: Turso Cloud Database is not active or credentials missing.")
        sys.exit(1)

    print("[*] Connecting to Turso Cloud Database...")
    init_db(db_path)

    # 1. Check auto_sync_enabled setting
    auto_enabled = get_user_setting(db_path, "auto_sync_enabled", "1").strip().lower()
    if auto_enabled in ("0", "false") and not force:
        print("[*] Notice: Automatic sync is paused in user settings (auto_sync_enabled=0). Skipping scheduled run.")
        return

    # 2. Local-First & Active Worker Concurrency Check
    now = time.time()
    claimed_command = None
    try:
        current_command = inbox.read(db_path)
        
        # 2a. Check if ANY worker (local or cloud) is actively running
        if current_command.get("status") == "running" and current_command.get("lease_until", 0) > now and not force:
            executor_type = current_command.get("executor", "unknown")
            lease_left = int(current_command.get("lease_until", 0) - now)
            if executor_type == "local":
                print(f"[✓] Local-First Rule: Local worker is actively running sync on candidate PC (lease valid for {lease_left}s).")
            else:
                print(f"[✓] Concurrency Guard: Another {executor_type} worker is currently running sync (lease valid for {lease_left}s).")
            print("[*] Cloud runner gracefully yields.")
            return

        presence_raw = get_user_setting(db_path, inbox.KEY + ":local", "{}")
        presence = json.loads(presence_raw or "{}")
        local_last_seen = presence.get("last_seen_at", 0)
        
        # 2b. If local worker was seen in the last 90s and a command is freshly queued for local
        if (
            current_command.get("status") == "queued"
            and now < current_command.get("local_deadline", 0)
            and (now - local_last_seen) < 90
            and not force
        ):
            print("[✓] Local-First Rule: Recent local worker detected within acknowledgment window. Yielding to local.")
            return

        # 2c. If a command is queued but local deadline expired (or force=True), claim it
        if current_command.get("status") == "queued":
            claimed_command = inbox.claim(db_path, "cloud", "github-cron-runner")
            if claimed_command:
                print(f"[+] Claimed queued inbox command: {claimed_command.get('id')}")

    except Exception as e:
        print(f"[*] Warning during local-first check (proceeding with cloud run): {e}")

    # 3. Cloud Execution
    print("[+] Local worker is offline or idle. Cloud GitHub Actions runner taking execution authority.")
    before_stats = get_stats(db_path)
    print(f"[*] Pre-sync stats: {before_stats['total']} total jobs ({before_stats['new']} new, {before_stats['applied']} applied)")

    aggregator = Aggregator(db_path=db_path)
    aggregator.daily_run = True
    print(f"[*] Starting multi-board scrape across {len(aggregator.connectors)} platforms...")
    start_time = time.time()

    sync_stats = aggregator.run_sync()
    duration = time.time() - start_time

    # 4. Post-sync hygiene
    print("[*] Running hygiene purges (non-tech filtering & exact timeline deduplication)...")
    try:
        from scripts.purge_non_tech import purge_irrelevant_jobs
        purge_irrelevant_jobs(db_path)
    except Exception as e:
        print(f"[*] Non-tech purge notice: {e}")

    try:
        from scripts.purge_same_timeline_dups import purge_same_timeline_duplicates
        purge_same_timeline_duplicates(db_path)
    except Exception as e:
        print(f"[*] Deduplication purge notice: {e}")

    after_stats = get_stats(db_path)

    # 5. Record telemetry, sync_status, and daily_scrape_day in Turso
    result_summary = {
        "status": "complete",
        "added": sync_stats.get("added", 0),
        "skipped": sync_stats.get("skipped", 0),
        "total_fetched": sync_stats.get("total_fetched", 0),
        "platforms": sync_stats.get("platforms", {})
    }

    telemetry = {
        "cycle_id": f"cloud-cron-{int(now)}",
        "is_syncing": False,
        "executor": "cloud",
        "runner": "github-actions",
        "completed_at": time.time(),
        "duration_seconds": round(duration, 2),
        "last_result": result_summary
    }

    try:
        set_user_setting(db_path, "sync_status", json.dumps(telemetry))
        today_manila = get_manila_day()
        set_user_setting(db_path, "daily_scrape_day", today_manila)
        print(f"[✓] Recorded daily_scrape_day={today_manila} in Turso database.")
        
        # Complete claimed inbox command if any
        if claimed_command:
            inbox.update_owned(db_path, claimed_command, result=result_summary)
            print(f"[✓] Completed inbox command {claimed_command.get('id')}.")
    except Exception as e:
        print(f"[*] Warning updating sync_status / inbox setting: {e}")

    print("=" * 60)
    print(f"[✓] Cloud Cron Sync completed successfully in {duration:.2f}s!")
    print(f"[+] Newly Discovered Jobs: +{sync_stats.get('added', 0)}")
    print(f"[~] Existing / Duplicates Skipped: {sync_stats.get('skipped', 0)}")
    print(f"[*] Post-sync stats: {after_stats['total']} total jobs ({after_stats['new']} new)")
    print("=" * 60)

if __name__ == "__main__":
    run()
