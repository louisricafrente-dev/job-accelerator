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
PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
IS_CLOUD = bool(os.environ.get("PORT") or os.environ.get("RENDER") or os.environ.get("RAILWAY_STATIC_URL"))

def open_browser():
    if IS_CLOUD:
        return
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

    # 3. Check if server is already responding
    import urllib.request
    server_responding = False
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/stats", timeout=0.8)
        server_responding = True
    except Exception:
        server_responding = False

    if server_responding:
        print(f"[✓] Server is already active on http://localhost:{PORT}")
        print("[+] Opening browser to existing dashboard...")
        open_browser()
        time.sleep(1.5)
        return

    # Clear any stale listening process on PORT if needed
    if sys.platform == "win32":
        try:
            import subprocess
            out = subprocess.check_output(f"netstat -ano | findstr :{PORT}", shell=True, text=True, errors="replace")
            for line in out.strip().splitlines():
                if "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        print(f"[*] Reclaiming port {PORT} from stale process (PID {pid})...")
                        subprocess.call(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        time.sleep(0.5)
        except Exception:
            pass

    # 4. Schedule browser opening
    if not IS_CLOUD:
        threading.Thread(target=open_browser, daemon=True).start()

    # 5. Run threaded multi-client server
    from wsgiref.simple_server import WSGIServer, make_server
    from socketserver import ThreadingMixIn
    import bottle

    class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    class ThreadedServer(bottle.ServerAdapter):
        def run(self, handler):
            server = make_server(self.host, self.port, handler, server_class=ThreadedWSGIServer)
            server.serve_forever()

    app = create_app(DB_PATH)
    print(f"\n[✓] Server running on http://{HOST}:{PORT} (Press Ctrl+C to stop)")
    app.run(server=ThreadedServer(host=HOST, port=PORT), quiet=False)

if __name__ == "__main__":
    main()
