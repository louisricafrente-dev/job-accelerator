"""Run the scraper locally and send results to the shared dashboard API."""
import json
import os
import socket
import sqlite3
import sys
import threading
import time
import uuid
import hashlib
from contextlib import contextmanager
from pathlib import Path
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
UPLOAD_BATCH_SIZE = 8


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


def local_telemetry(aggregator=None):
    if aggregator is not None:
        status = aggregator.get_telemetry()
    else:
        raw = get_user_setting(DB_PATH, "sync_status", "")
        try:
            status = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            status = {}
    telemetry = {key: status[key] for key in ("progress", "last_result", "last_sync_time", "logs", "telemetry", "total_boards") if key in status}
    checkpoint = json.loads(get_user_setting(DB_PATH, "sync_batch_progress", "{}") or "{}")
    scrape = json.loads(get_user_setting(DB_PATH, "local_worker_scrape_totals", "{}") or "{}")
    uploads = json.loads(get_user_setting(DB_PATH, "local_worker_upload_totals", "{}") or "{}")
    if scrape.get("request_id") and scrape.get("request_id") == checkpoint.get("cycle_id"):
        telemetry["run_totals"] = dict(scrape)
        if uploads.get("request_id") == scrape["request_id"]:
            telemetry["run_totals"].update({key: uploads.get(key, 0) for key in ("added", "skipped", "sent")})
    return telemetry


def heartbeat(worker_id, active_request_id="", aggregator=None):
    return api_call("/api/local-worker/heartbeat", "POST", {
        "worker_id": worker_id,
        "machine": socket.gethostname(),
        "active_request_id": active_request_id,
        "telemetry": local_telemetry(aggregator),
    })


def keep_alive(worker_id, active_request, stop, aggregator=None):
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            heartbeat(worker_id, active_request[0], aggregator)
        except Exception as exc:
            print(f"Local worker heartbeat failed: {exc}", flush=True)


def pending_jobs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS worker_upload_ack (job_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL)")
        conn.commit()
        acknowledged = dict(conn.execute("SELECT job_id, fingerprint FROM worker_upload_ack").fetchall())
        rows = conn.execute("SELECT id, title, company, location, platform, tier, job_url, salary, description, role_category, experience_level, date_posted, sources FROM jobs ORDER BY id").fetchall()
        result = []
        batch_bytes = 0
        for row in rows:
            item = dict(row)
            try:
                item["sources"] = json.loads(item["sources"] or "[]")
            except (ValueError, TypeError):
                item["sources"] = []
            raw_item = json.dumps(item, sort_keys=True, ensure_ascii=True)
            fingerprint = hashlib.sha256(raw_item.encode()).hexdigest()
            if acknowledged.get(item["id"]) != fingerprint:
                if result and batch_bytes + len(raw_item) > 70000:
                    break
                batch_bytes += len(raw_item)
                item["_fingerprint"] = fingerprint
                result.append(item)
                if len(result) >= UPLOAD_BATCH_SIZE:
                    break
        return result
    finally:
        conn.close()


def upload_pending(request_id, worker_id):
    totals = json.loads(get_user_setting(DB_PATH, "local_worker_upload_totals", "{}") or "{}")
    if totals.get("request_id") != request_id:
        totals = {"request_id": request_id, "added": 0, "skipped": 0, "sent": 0}
    while True:
        batch = pending_jobs()
        if not batch:
            break
        payload = [{key: value for key, value in item.items() if key != "_fingerprint"} for item in batch]
        result = api_call("/api/local-worker/jobs", "POST", {"request_id": request_id, "worker_id": worker_id, "jobs": payload})
        totals["added"] += result.get("added", 0)
        totals["skipped"] += result.get("skipped", 0)
        totals["sent"] += len(batch)
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.executemany("INSERT OR REPLACE INTO worker_upload_ack (job_id, fingerprint) VALUES (?, ?)",
                             [(item["id"], item["_fingerprint"]) for item in batch])
            conn.execute("INSERT INTO user_settings (key,value) VALUES ('local_worker_upload_totals',?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(totals),))
            conn.commit()
        finally:
            conn.close()
    return totals["added"], totals["skipped"], totals["sent"]


def run_request(request, aggregator):
    pending = json.loads(get_user_setting(DB_PATH, "local_worker_pending_result", "{}") or "{}")
    if pending.get("request_id") == request["id"]:
        result = pending["result"]
    else:
        from src.sync_batches import CYCLE_SECONDS
        remaining = max(0, request.get("requested_at", time.time()) + CYCLE_SECONDS - time.time())
        result = aggregator.run_sync(queries=request.get("queries"), budget_seconds=min(30, remaining), cycle_id=request["id"], resume=request.get("resume", False), restart=request.get("restart", False))
        if result.get("status") == "already_syncing":
            raise RuntimeError("Local scraper is busy; retaining request for retry")
        totals = json.loads(get_user_setting(DB_PATH, "local_worker_scrape_totals", "{}") or "{}")
        if totals.get("request_id") != request["id"]:
            totals = {"request_id": request["id"], "total_fetched": 0, "platforms": {}}
        totals["total_fetched"] += result.get("total_fetched", 0)
        for platform, count in result.get("platforms", {}).items():
            totals["platforms"][platform] = totals["platforms"].get(platform, 0) + count
        result = {**result, "total_fetched": totals["total_fetched"], "platforms": totals["platforms"]}
        set_user_setting(DB_PATH, "local_worker_scrape_totals", json.dumps(totals))
        set_user_setting(DB_PATH, "local_worker_pending_result", json.dumps({"request_id": request["id"], "result": result}))
    added, skipped, uploaded = upload_pending(request["id"], request["worker_id"])
    progress = result.get("progress") or {}
    from src.sync_batches import CYCLE_SECONDS
    if (result.get("status") != "error" and progress.get("has_more")
            and (progress.get("can_continue") is not False or progress.get("next_run_at", time.time()) <= time.time() + 30)
            and time.time() - request.get("requested_at", time.time()) < CYCLE_SECONDS):
        set_user_setting(DB_PATH, "local_worker_pending_result", "{}")
        return progress
    result = {
        "status": "error" if result.get("status") == "error" else "partial" if progress.get("has_more") else result.get("status", "error"),
        "added": added,
        "skipped": skipped,
        "total_fetched": result.get("total_fetched", 0),
        "platforms": result.get("platforms", {}),
        "total_boards": len(aggregator.connectors),
        "telemetry": result.get("telemetry", {}),
        "logs": result.get("logs", []),
        "progress": result.get("progress"),
        "error": result.get("error") or ("Cycle finished with deferred searches; saved progress is available via Resume unfinished" if progress.get("unfinished") or progress.get("has_more") else None),
        "uploaded": uploaded,
        "last_sync_time": local_telemetry().get("last_sync_time", 0),
    }
    api_call("/api/local-worker/complete", "POST", {"request_id": request["id"], "worker_id": request["worker_id"], "result": result})
    set_user_setting(DB_PATH, "local_worker_pending_result", "{}")


def load_token():
    if "LOCAL_WORKER_TOKEN" not in os.environ and TOKEN_PATH.exists():
        os.environ["LOCAL_WORKER_TOKEN"] = TOKEN_PATH.read_text(encoding="utf-8").strip()
    if not os.environ.get("LOCAL_WORKER_TOKEN"):
        raise RuntimeError(f"Local worker token is missing: {TOKEN_PATH}")
    if os.name == "nt" and not os.environ.get("FLCONSOLE_MCP_TOKEN"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                os.environ["FLCONSOLE_MCP_TOKEN"] = winreg.QueryValueEx(key, "FLCONSOLE_MCP_TOKEN")[0]
        except OSError:
            pass


@contextmanager
def worker_lock():
    LOCAL_DATA.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_DATA / "worker.lock", "a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def run_worker():
    load_token()
    LOCAL_DATA.mkdir(parents=True, exist_ok=True)
    init_db(DB_PATH)
    # This database belongs exclusively to the process holding worker.lock.
    from src.database import release_sync_lease
    old_lease = get_user_setting(DB_PATH, "sync_lease", "")
    if old_lease:
        release_sync_lease(DB_PATH, old_lease)
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
    from src.aggregator import Aggregator
    aggregator = Aggregator(DB_PATH)
    active_request = [""]
    stop = threading.Event()
    heartbeat_thread = threading.Thread(target=keep_alive, args=(worker_id, active_request, stop, aggregator), daemon=True)
    heartbeat_thread.start()
    try:
        while True:
            try:
                heartbeat(worker_id, active_request[0])
                request_data = api_call(f"/api/local-worker/request?worker_id={worker_id}")
                for key, value in request_data.get("proxy_settings", {}).items():
                    if key in {"proxy_mode", "proxy_list"} and isinstance(value, str) and get_user_setting(DB_PATH, key, "") != value:
                        set_user_setting(DB_PATH, key, value)
                request = request_data.get("request")
                if request:
                    active_request[0] = request.get("id", "")
                    progress = run_request(request, aggregator)
                    if progress and progress.get("has_more"):
                        stop.wait(min(30, max(1, progress.get("next_run_at", time.time()) - time.time())))
                    else:
                        active_request[0] = ""
                else:
                    heartbeat(worker_id)
                    time.sleep(POLL_SECONDS)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"Local worker error: {exc}", flush=True)
                stop.wait(HEARTBEAT_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        heartbeat_thread.join(timeout=HEARTBEAT_SECONDS + 1)


def main():
    LOCAL_DATA.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(LOCAL_DATA / "worker.log", "a", encoding="utf-8", buffering=1)
    with worker_lock():
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} Local worker starting", flush=True)
        run_worker()


if __name__ == "__main__":
    main()
