"""Run the scraper locally and send results to the shared dashboard API."""
import json
import os
import socket
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.database import get_user_setting, init_db, set_user_setting

LOCAL_DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "JobAccelerator"
DB_PATH = str(LOCAL_DATA / "jobs.db")
BASE_URL = os.environ.get("JOB_ACCELERATOR_URL", "https://job-accelerator.vercel.app").rstrip("/")
TOKEN_PATH = ROOT / ".vercel" / "local-worker.token"
POLL_SECONDS = 5
HEARTBEAT_SECONDS = 15
UPLOAD_BATCH_SIZE = 20


def api_call(path, method="GET", data=None):
    token = os.environ["LOCAL_WORKER_TOKEN"]
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = Request(f"{BASE_URL}{path}", data=body, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    with urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def local_telemetry():
    raw = get_user_setting(DB_PATH, "sync_status", "")
    try:
        status = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        status = {}
    return {key: status[key] for key in ("progress", "last_result", "last_sync_time", "logs", "telemetry", "total_boards") if key in status}


def heartbeat(worker_id, active_request_id=""):
    return api_call("/api/local-worker/heartbeat", "POST", {
        "worker_id": worker_id,
        "machine": socket.gethostname(),
        "active_request_id": active_request_id,
        "telemetry": local_telemetry(),
    })


def max_job_id():
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute("SELECT COALESCE(MAX(id), 0) FROM jobs").fetchone()[0]
    finally:
        conn.close()


def pending_jobs(after_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, title, company, location, platform, tier, job_url, salary, description, role_category, experience_level, date_posted, sources FROM jobs WHERE id > ? ORDER BY id", (after_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["sources"] = json.loads(item["sources"] or "[]")
            except (ValueError, TypeError):
                item["sources"] = []
            result.append(item)
        return result
    finally:
        conn.close()


def upload_pending(request_id):
    cursor = int(get_user_setting(DB_PATH, "local_worker_upload_id", "0") or 0)
    added = skipped = sent = 0
    while True:
        batch = pending_jobs(cursor)[:UPLOAD_BATCH_SIZE]
        if not batch:
            break
        result = api_call("/api/local-worker/jobs", "POST", {"request_id": request_id, "jobs": batch})
        added += result.get("added", 0)
        skipped += result.get("skipped", 0)
        sent += len(batch)
        cursor = batch[-1]["id"]
        set_user_setting(DB_PATH, "local_worker_upload_id", str(cursor))
    return added, skipped, sent


def run_request(request, aggregator):
    started_after = max_job_id()
    result = aggregator.run_sync(queries=request.get("queries"))
    added, skipped, uploaded = upload_pending(request["id"])
    result = {
        "status": result.get("status", "error"),
        "added": added,
        "skipped": skipped,
        "total_fetched": result.get("total_fetched", 0),
        "platforms": result.get("platforms", {}),
        "total_boards": result.get("total_boards", 0),
        "logs": result.get("logs", []),
        "progress": result.get("progress"),
        "error": result.get("error"),
        "uploaded": uploaded,
        "local_new": max_job_id() - started_after,
    }
    api_call("/api/local-worker/complete", "POST", {"request_id": request["id"], "result": result})


def load_token():
    if "LOCAL_WORKER_TOKEN" not in os.environ and TOKEN_PATH.exists():
        os.environ["LOCAL_WORKER_TOKEN"] = TOKEN_PATH.read_text(encoding="utf-8").strip()
    if not os.environ.get("LOCAL_WORKER_TOKEN"):
        raise RuntimeError(f"Local worker token is missing: {TOKEN_PATH}")


def main():
    load_token()
    LOCAL_DATA.mkdir(parents=True, exist_ok=True)
    init_db(DB_PATH)
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
    heartbeat(worker_id)
    from src.aggregator import Aggregator
    aggregator = Aggregator(DB_PATH)
    while True:
        try:
            request_data = api_call(f"/api/local-worker/request?worker_id={worker_id}")
            request = request_data.get("request")
            if request:
                heartbeat(worker_id, request.get("id", ""))
                run_request(request, aggregator)
                heartbeat(worker_id)
            else:
                heartbeat(worker_id)
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            return
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            if isinstance(exc, HTTPError) and exc.code == 409:
                time.sleep(HEARTBEAT_SECONDS)
                continue
            print(f"Local worker connection error: {exc}", flush=True)
            time.sleep(HEARTBEAT_SECONDS)
        except Exception as exc:
            print(f"Local worker error: {exc}", flush=True)
            time.sleep(HEARTBEAT_SECONDS)


if __name__ == "__main__":
    main()
