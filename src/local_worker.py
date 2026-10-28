"""Shared cloud queue and local-worker coordination."""
import json
import time
import uuid

from src.database import get_user_setting, set_user_setting

WORKER_KEY = "local_worker_status"
REQUEST_KEY = "local_sync_request"
WORKER_TTL = 45
LEASE_SECONDS = 90


def read_json_setting(db_path, key):
    raw = get_user_setting(db_path, key, "")
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def worker_status(db_path, now=None):
    status = read_json_setting(db_path, WORKER_KEY)
    status["online"] = bool(status.get("heartbeat_at", 0) > (now or time.time()) - WORKER_TTL)
    return status


def owns_execution(db_path, request, now=None):
    lease = get_user_setting(db_path, "sync_lease", "0|") or "0|"
    expiry, _, owner = lease.partition("|")
    return (expiry.isdigit() and int(expiry) > (time.time() if now is None else now)
            and owner == request.get("lease_owner") and bool(owner))


def public_request(db_path, request, worker=None):
    result = dict(request)
    worker = worker if worker is not None else worker_status(db_path)
    if result.get("status") in {"queued", "running"}:
        if not worker.get("online") or (result["status"] == "running" and not owns_execution(db_path, result)):
            result.update(status="interrupted", error="Local worker disconnected; click Sync to resume or use cloud fallback")
    return result


def request_local_sync(db_path, queries=None, automatic=False, resume=False, restart=False):
    now = time.time()
    worker = worker_status(db_path, now)
    if not worker["online"]:
        return None
    lease = get_user_setting(db_path, "sync_lease", "0|") or "0|"
    expiry, _, owner = lease.partition("|")
    if expiry.isdigit() and int(expiry) > now and not owner.startswith("local:"):
        return None
    if not queries:
        saved = get_user_setting(db_path, "target_stack", "") or ""
        queries = [query.strip() for query in saved.split(",") if query.strip()] or None
    current = read_json_setting(db_path, REQUEST_KEY)
    if restart:
        from src.database import release_sync_lease
        release_sync_lease(db_path, lease)
        set_user_setting(db_path, "sync_batch_progress", "")
        set_user_setting(db_path, "local_worker_scrape_totals", "{}")
        set_user_setting(db_path, "local_worker_upload_totals", "{}")
        request = {"id": uuid.uuid4().hex, "queries": queries, "automatic": automatic,
                   "status": "queued", "requested_at": now, "updated_at": now, "restart": True}
        set_user_setting(db_path, REQUEST_KEY, json.dumps(request))
        return {"status": "queued", "is_syncing": True, "local_request": request, "local_worker": worker}
    if current.get("status") in {"queued", "running"}:
        return {"status": "already_syncing", "is_syncing": True, "local_request": current,
                "local_worker": worker}
    previous = current.get("result") or {}
    if (resume and (previous.get("progress", {}).get("unfinished") or previous.get("progress", {}).get("has_more") or current.get("status") in {"paused", "stopped"}) and (not current.get("queries") or current.get("queries") == queries)
            and current.get("status") in {"complete", "partial", "error", "paused", "stopped"}):
        current.update(status="queued", requested_at=now, updated_at=now, automatic=automatic, resume=True)
        current.pop("completed_at", None)
        set_user_setting(db_path, REQUEST_KEY, json.dumps(current))
        return {"status": "queued", "is_syncing": True, "local_request": current, "local_worker": worker}
    request = {"id": uuid.uuid4().hex, "queries": queries, "automatic": automatic,
               "status": "queued", "requested_at": now, "updated_at": now}
    set_user_setting(db_path, REQUEST_KEY, json.dumps(request))
    return {"status": "queued", "is_syncing": True, "local_request": request,
            "local_worker": worker}


def pause_local_sync(db_path):
    now = time.time()
    current = read_json_setting(db_path, REQUEST_KEY)
    worker = worker_status(db_path, now)
    if current.get("status") in {"queued", "running"}:
        current.update(status="paused", updated_at=now)
        set_user_setting(db_path, REQUEST_KEY, json.dumps(current))
    from src.database import release_sync_lease
    lease = get_user_setting(db_path, "sync_lease", "0|") or "0|"
    release_sync_lease(db_path, lease)
    return {"status": "paused", "is_syncing": False, "local_request": current, "local_worker": worker}


def stop_local_sync(db_path):
    now = time.time()
    current = read_json_setting(db_path, REQUEST_KEY)
    worker = worker_status(db_path, now)
    current.update(status="stopped", updated_at=now, error="Stopped by user")
    set_user_setting(db_path, REQUEST_KEY, json.dumps(current))
    from src.database import release_sync_lease
    lease = get_user_setting(db_path, "sync_lease", "0|") or "0|"
    release_sync_lease(db_path, lease)
    return {"status": "stopped", "is_syncing": False, "local_request": current, "local_worker": worker}


def cancel_queued_local_sync(db_path):
    request = read_json_setting(db_path, REQUEST_KEY)
    if request.get("status") in {"queued", "running"} and not worker_status(db_path)["online"]:
        request.update(status="cancelled", updated_at=time.time())
        set_user_setting(db_path, REQUEST_KEY, json.dumps(request))


def clear_stale_worker(db_path, worker_id):
    current = read_json_setting(db_path, WORKER_KEY)
    if current.get("worker_id") == worker_id:
        set_user_setting(db_path, WORKER_KEY, json.dumps({"worker_id": worker_id,
            "heartbeat_at": 0, "online": False, "stopped_at": time.time()}))
