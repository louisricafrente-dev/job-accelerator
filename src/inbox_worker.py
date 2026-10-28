"""Local/cloud execution using the shared database, without dashboard polling."""
import json
import logging
import threading
import time
from src import execution_inbox as inbox
from src.database import ExecutionLeaseLost, get_user_setting, set_user_setting


def run_claimed(db_path, command, aggregator, key=inbox.KEY):
    guard = {**command, "key": key}
    aggregator.execution_guard = guard
    aggregator.daily_run = bool(command.get("automatic"))
    stop = threading.Event()
    lost = threading.Event()

    def renew():
        while not stop.wait(60):
            try:
                if not inbox.update_owned(db_path, command, key=key):
                    lost.set()
                    return
            except Exception:
                # A connectivity failure must stop new saves until ownership is checked.
                lost.set()
                return

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    totals = command.get("totals") or {"added": 0, "skipped": 0, "total_fetched": 0, "platforms": {}}
    try:
        while not lost.is_set() and inbox.owned(db_path, command, key=key):
            command["daily_requested"] = inbox.read(db_path, key).get("daily_requested", False)
            aggregator.daily_run = bool(command.get("automatic") or command["daily_requested"])
            if command.get("automatic") and get_user_setting(db_path, "auto_sync_enabled", "1") in ("0", "false"):
                inbox.cancel(db_path, key=key, status="paused")
                return
            remaining = command["expires_at"] - time.time()
            if remaining <= 0:
                return
            result = aggregator.run_sync(queries=command.get("queries"), budget_seconds=min(120, remaining),
                                         cycle_id=command.get("cycle_id", command["id"]), resume=command.get("resume", False),
                                         restart=command.get("restart", False))
            command["restart"] = False
            if result.get("status") == "already_syncing":
                stop.wait(15)
                continue
            for field in ("added", "skipped", "total_fetched"):
                totals[field] += result.get(field, 0)
            for board, count in result.get("platforms", {}).items():
                totals["platforms"][board] = totals["platforms"].get(board, 0) + count
            if not inbox.update_owned(db_path, command, key=key, totals=totals):
                return
            progress = result.get("progress", {})
            if result.get("status") == "error" or not progress.get("has_more") or not progress.get("can_continue", True):
                result = {**result, **totals}
                if progress.get("unfinished") and result.get("status") != "error":
                    result["status"] = "partial"
                if inbox.update_owned(db_path, command, result, key=key):
                    return result
                continue
            stop.wait(min(30, max(1, progress.get("next_run_at", time.time()) - time.time())))
    except ExecutionLeaseLost:
        return
    except Exception:
        inbox.update_owned(db_path, command, {"status": "error", "error": "Worker failed; checkpoint retained for resume"}, key=key)
        raise
    finally:
        stop.set()
        thread.join(timeout=5)
        aggregator.execution_guard = None


def run_cloud(db_path, command_id, aggregator, key=inbox.KEY, wait=time.sleep):
    # One Actions run supervises local execution and takes over an expired claim.
    deadline = time.monotonic() + inbox.CYCLE_SECONDS
    while time.monotonic() < deadline:
        try:
            command = inbox.read(db_path, key=key)
            if command.get("id") != command_id or inbox.public(command).get("status") not in inbox.ACTIVE:
                return
            now = time.time()
            boundary = command.get("lease_until", 0) if command.get("status") == "running" else command["local_deadline"]
            if boundary <= now:
                claimed = inbox.claim(db_path, "cloud", "github", key=key)
                if claimed:
                    return run_claimed(db_path, claimed, aggregator, key)
            delay = min(60, max(1, boundary - now))
        except Exception:
            logging.warning("Cloud worker operation failed; retrying in 60 seconds")
            delay = 60
        wait(min(delay, max(0, deadline - time.monotonic())))


def run_local(db_path, aggregator, stop=None, key=inbox.KEY):
    stop = stop or threading.Event()
    import socket
    import uuid
    worker_id = socket.gethostname() + "-" + uuid.uuid4().hex[:8]
    presence_key = key + ":local"
    presence_saved = False
    try:
        while not stop.is_set():
            try:
                if not presence_saved:
                    set_user_setting(db_path, presence_key, json.dumps({"worker_id": worker_id, "last_seen_at": time.time()}))
                    presence_saved = True
                command = inbox.read(db_path, key)
                if command.get("status") == "queued" and time.time() < command.get("local_deadline", 0):
                    claimed = inbox.claim(db_path, "local", worker_id, key=key)
                    if claimed:
                        run_claimed(db_path, claimed, aggregator, key)
            except Exception:
                logging.warning("Local worker operation failed; retrying in 60 seconds")
            stop.wait(inbox.POLL_SECONDS)
    finally:
        try:
            set_user_setting(db_path, presence_key, json.dumps({"worker_id": worker_id, "last_seen_at": time.time(), "stopped": True}))
        except Exception:
            logging.warning("Could not save local worker stopped status")
