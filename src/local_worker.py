"""Shared cloud queue and local-worker coordination."""
import json
import time
import uuid

from src.database import get_user_setting, set_user_setting

WORKER_KEY = "local_worker_status"
REQUEST_KEY = "local_sync_request"
WORKER_TTL = 45


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


def request_local_sync(db_path, queries=None, automatic=False):
    now = time.time()
    worker = worker_status(db_path, now)
    if not worker["online"]:
        return None
    current = read_json_setting(db_path, REQUEST_KEY)
    if current.get("status") in {"queued", "running"}:
        return {"status": "already_syncing", "is_syncing": True, "local_request": current,
                "local_worker": worker}
    request = {"id": uuid.uuid4().hex, "queries": queries, "automatic": automatic,
               "status": "queued", "requested_at": now, "updated_at": now}
    set_user_setting(db_path, REQUEST_KEY, json.dumps(request))
    return {"status": "queued", "is_syncing": True, "local_request": request,
            "local_worker": worker}


def cancel_queued_local_sync(db_path):
    request = read_json_setting(db_path, REQUEST_KEY)
    if request.get("status") == "queued":
        request.update(status="cancelled", updated_at=time.time())
        set_user_setting(db_path, REQUEST_KEY, json.dumps(request))


def clear_stale_worker(db_path, worker_id):
    current = read_json_setting(db_path, WORKER_KEY)
    if current.get("worker_id") == worker_id:
        set_user_setting(db_path, WORKER_KEY, json.dumps({"worker_id": worker_id,
            "heartbeat_at": 0, "online": False, "stopped_at": time.time()}))
