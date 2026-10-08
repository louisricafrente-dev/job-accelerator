import os
import sys
import webbrowser
import threading
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.database import init_db, get_stats
from src.seed import seed_sample_data
from src.server import create_app

DB_PATH = "data/jobs.db"
PORT = 8000

def open_browser():
    time.sleep(1.2)
    url = f"http://localhost:{PORT}"
    print(f"\n[+] Opening Job Accelerator Dashboard at {url} ...\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

def main():
    print("=" * 60)
    print("       🚀 Job Application Accelerator - Starting Up")
    print("=" * 60)

    # 1. Ensure DB initialized
    init_db(DB_PATH)

    # 2. Check if initial seed is needed
    stats = get_stats(DB_PATH)
    if stats["total"] == 0:
        print("[*] Empty database detected. Seeding sample listings across 12 platforms...")
        seeded = seed_sample_data(DB_PATH)
        print(f"[✓] Seeded {seeded} initial jobs.")
    else:
        print(f"[✓] Database ready with {stats['total']} total jobs ({stats['new']} new, {stats['applied']} applied).")

    # 3. Schedule browser opening
    threading.Thread(target=open_browser, daemon=True).start()

    # 4. Run server
    app = create_app(DB_PATH)
    print(f"\n[✓] Server running on http://localhost:{PORT} (Press Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=PORT, quiet=False)

if __name__ == "__main__":
    main()
