"""Poll one targeted flconsole search into the existing cloud dashboard."""
import json
import os
from pathlib import Path
import sys
import time
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if os.name == "nt" and not os.environ.get("FLCONSOLE_MCP_TOKEN"):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            os.environ["FLCONSOLE_MCP_TOKEN"] = winreg.QueryValueEx(key, "FLCONSOLE_MCP_TOKEN")[0]
    if not os.environ.get("FLCONSOLE_MCP_TOKEN"):
        raise SystemExit("Upwork polling requires FLCONSOLE_MCP_TOKEN")
    from src.connectors.remote_feed import UpworkConnector
    from scripts.local_worker import LOCAL_DATA, load_token, api_call
    load_token()
    LOCAL_DATA.mkdir(parents=True, exist_ok=True)
    checkpoint = LOCAL_DATA / "upwork-feed.json"
    connector = UpworkConnector()
    # Avoid repeating the same search when this task is manually restarted.
    previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    if time.time() < previous.get("next_at", 0):
        print("Upwork: waiting for the next scheduled check")
        return
    if not api_call("/api/local-worker/upwork/claim", "POST", {}).get("claimed"):
        print("Upwork: cloud/local polling slot is cooling down")
        return
    jobs = connector.fetch()
    error = getattr(connector, "last_error", "")
    # Persist before uploading so a transient dashboard outage cannot lose matches.
    pending = previous.get("pending", []) + [asdict(job) for job in jobs]
    status = {"checked_at": time.time(), "next_at": time.time() + 600,
              "fetched": len(jobs), "error": error, "provider": "flconsole", "pending": pending}
    checkpoint.write_text(json.dumps(status), encoding="utf-8")
    added = skipped = 0
    while pending:
        result = api_call("/api/local-worker/upwork", "POST", {"jobs": pending[:30], "error": error})
        added += result.get("added", 0)
        skipped += result.get("skipped", 0)
        pending = pending[30:]
        status["pending"] = pending
        checkpoint.write_text(json.dumps(status), encoding="utf-8")
    if not jobs:
        api_call("/api/local-worker/upwork", "POST", {"jobs": [], "error": error})
    print(json.dumps({"fetched": len(jobs), "added": added, "skipped": skipped, "error": error}))
    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--background" in sys.argv:
        log_dir = Path(os.environ["LOCALAPPDATA"]) / "JobAccelerator"
        log_dir.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(log_dir / "upwork.log", "a", encoding="utf-8", buffering=1)
    main()
