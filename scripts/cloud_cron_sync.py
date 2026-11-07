"""
Cloud Cron Scraper Runner (GitHub Actions)
Executes scheduled multi-board job scrapes in the cloud with strict Local-First priority.
Safely yields if candidate PC local worker is actively running or acknowledging commands.
Uses the same fenced worker and checkpoint reporting as website commands.
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

from src.database import (
    init_db,
    get_user_setting,
    is_turso_active
)
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

    # Scheduled and website requests share atomic claims and renewable leases.
    from src.daily_schedule import has_unfinished
    resume = not force and has_unfinished(db_path)
    command = inbox.enqueue(db_path, automatic=not force, **({"resume": True} if resume else {}))
    now = time.time()
    if command.get("status") == "running" and command.get("lease_until", 0) > now:
        print(f"[*] Active {command.get('executor', 'unknown')} worker owns this cycle; scheduled runner yields.")
        return

    from src.inbox_worker import run_cloud
    print(f"[*] Supervising shared command {command['id']}; local worker has first priority.")
    result = run_cloud(db_path, command["id"], Aggregator(db_path=db_path))
    current = inbox.public(inbox.read(db_path))
    if current.get("id") != command["id"]:
        print("[*] A newer website command replaced this cycle; scheduled runner stopped.")
        return
    status = current.get("status", "unknown")
    result = result or current.get("result") or {}
    print(json.dumps({"status": status, "added": result.get("added", 0),
                      "total_fetched": result.get("total_fetched", 0),
                      "unfinished": result.get("progress", {}).get("unfinished", 0)}))
    if status == "error":
        raise SystemExit("Scheduled scrape failed; inspect shared source telemetry/checkpoint")
    if status == "partial":
        print("::warning::Scrape finished partially; blocked sources/coverage limits remain in dashboard telemetry.")


if __name__ == "__main__":
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
    run()
