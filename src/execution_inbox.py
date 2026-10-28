"""Database command inbox with atomic claims and fenced completion."""
import json
import time
import uuid
from src.database import get_db_connection, get_user_setting

POLL_SECONDS = 60
LOCAL_ACK_SECONDS = 90
LEASE_SECONDS = 180
KEY = "execution_inbox_v1"
ACTIVE = {"queued", "running"}


def read(db_path, key=KEY):
    return json.loads(get_user_setting(db_path, key, "{}") or "{}")


def _replace(db_path, before, after, key):
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "UPDATE user_settings SET value=? WHERE key=? AND value=?",
            (json.dumps(after, sort_keys=True), key, before))
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def enqueue(db_path, queries=None, key=KEY, now=None):
    now = time.time() if now is None else now
    conn = get_db_connection(db_path)
    try:
        conn.execute("INSERT INTO user_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO NOTHING", (key, "{}"))
        conn.commit()
    finally:
        conn.close()
    for _ in range(5):
        raw = get_user_setting(db_path, key, "{}")
        current = json.loads(raw)
        if current.get("status") in ACTIVE:
            return current
        command = {"id": uuid.uuid4().hex, "status": "queued", "queries": queries,
                   "requested_at": now, "local_deadline": now + LOCAL_ACK_SECONDS}
        if _replace(db_path, raw, command, key):
            return command
    raise RuntimeError("Inbox changed concurrently; retry enqueue")


def claim(db_path, executor, worker_id, key=KEY, now=None):
    if executor not in {"local", "cloud"}:
        raise ValueError("Executor must be local or cloud")
    now = time.time() if now is None else now
    raw = get_user_setting(db_path, key, "{}")
    command = json.loads(raw)
    if command.get("status") not in ACTIVE:
        return None
    if command["status"] == "running" and command.get("lease_until", 0) > now:
        return None
    # Once the local acknowledgment window closes only the cloud can claim.
    if (executor == "local") != (now < command["local_deadline"]):
        return None
    command.update(status="running", executor=executor, worker_id=worker_id,
                   fence=uuid.uuid4().hex, lease_until=now + LEASE_SECONDS, updated_at=now)
    return command if _replace(db_path, raw, command, key) else None


def update_owned(db_path, claimed, result=None, key=KEY, now=None):
    now = time.time() if now is None else now
    raw = get_user_setting(db_path, key, "{}")
    command = json.loads(raw)
    if (command.get("status") != "running" or command.get("id") != claimed.get("id")
            or command.get("fence") != claimed.get("fence") or command.get("lease_until", 0) <= now):
        return False
    command.update(updated_at=now, lease_until=now + LEASE_SECONDS)
    if result is not None:
        command.update(status="error" if result.get("status") == "error" else "complete", result=result)
    return _replace(db_path, raw, command, key)


def cancel(db_path, key=KEY):
    raw = get_user_setting(db_path, key, "{}")
    command = json.loads(raw)
    if command.get("status") not in ACTIVE:
        return False
    command.update(status="cancelled", updated_at=time.time())
    return _replace(db_path, raw, command, key)
