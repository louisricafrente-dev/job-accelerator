"""Local/cloud execution using the shared database, without dashboard polling."""
import json
import logging
import threading
import time
from src import execution_inbox as inbox
from src.database import ExecutionLeaseLost, get_user_setting, set_user_setting
from src.sync_batches import is_forbidden, is_rate_limited


BATCH_SECONDS = 120
# Allow in-flight fetches and checkpoint writes to finish before the lease expires.
FINALIZE_RESERVE_SECONDS = 60


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
    transient_retries = 0
    work_deadline = command["expires_at"] - FINALIZE_RESERVE_SECONDS
    result = {"status": "partial"}
    try:
        while not lost.is_set() and inbox.owned(db_path, command, key=key):
            command["daily_requested"] = inbox.read(db_path, key).get("daily_requested", False)
            aggregator.daily_run = bool(command.get("automatic") or command["daily_requested"])
            if command.get("automatic") and get_user_setting(db_path, "auto_sync_enabled", "1") in ("0", "false"):
                inbox.cancel(db_path, key=key, status="paused", claimed=command)
                return
            remaining = work_deadline - time.time()
            if remaining > 0:
                batch = aggregator.run_sync(queries=command.get("queries"), budget_seconds=min(BATCH_SECONDS, remaining),
                                            cycle_id=command.get("cycle_id", command["id"]), resume=command.get("resume", False),
                                            restart=command.get("restart", False))
                if batch.get("status") == "already_syncing":
                    stop.wait(max(0, min(15, work_deadline - time.time())))
                    continue
                result = batch
                command["restart"] = False
                for field in ("added", "skipped", "total_fetched"):
                    totals[field] += result.get(field, 0)
                for board, count in result.get("platforms", {}).items():
                    totals["platforms"][board] = totals["platforms"].get(board, 0) + count
                if not inbox.update_owned(db_path, command, key=key, totals=totals):
                    return
            progress = result.get("progress", {})
            remaining = work_deadline - time.time()
            if remaining > 5 and result.get("status") != "error" and not progress.get("has_more") and progress.get("unfinished") and transient_retries < 3:
                deferred = progress.get("deferred_boards", [])
                if any(not any(code in item.get("error", "").lower() for code in (
                    "429", "403", "404", "410", "captcha", "rate limit", "forbidden", "cloudflare challenge", "requires verification"
                )) for item in deferred):
                    transient_retries += 1
                    command["resume"] = True
                    stop.wait(5)
                    continue
            if result.get("status") != "error" and progress.get("unfinished") and not progress.get("can_continue", True):
                now = time.time()
                retry_at = min((item["retry_at"] for item in progress.get("deferred_boards", [])
                                if (is_rate_limited(item.get("error", "")) or is_forbidden(item.get("error", "")))
                                and item.get("retry_at")),
                               default=command["expires_at"])
                delay = max(1, retry_at - now)
                if now + delay < work_deadline:
                    lost.wait(delay)
                    continue
            if remaining <= 0 or result.get("status") == "error" or not progress.get("has_more") or not progress.get("can_continue", True):
                result = {**result, **totals}
                if (progress.get("unfinished") or progress.get("has_more")) and result.get("status") != "error":
                    result["status"] = "partial"
                if inbox.update_owned(db_path, command, result, key=key):
                    if aggregator.daily_run and progress and result.get("status") != "error":
                        from src.daily_schedule import day
                        set_user_setting(db_path, "daily_scrape_day", day())
                    return result
                continue
            stop.wait(min(remaining, 30, max(1, progress.get("next_run_at", time.time()) - time.time())))
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
    recovered_cycles = set()
    local_resume_counts = {}
    max_local_self_resumes = 3
    try:
        while not stop.is_set():
            try:
                if not presence_saved:
                    set_user_setting(db_path, presence_key, json.dumps({"worker_id": worker_id, "last_seen_at": time.time()}))
                    presence_saved = True
                now = time.time()
                command = inbox.read(db_path, key)
                if command.get("status") == "queued" and now < command.get("local_deadline", 0):
                    claimed = inbox.claim(db_path, "local", worker_id, key=key)
                    if claimed:
                        run_claimed(db_path, claimed, aggregator, key)
                elif command.get("status") == "partial" and (command.get("updated_at") or 0) >= now - 6 * 3600:
                    progress = (command.get("result") or {}).get("progress") or {}
                    deferred_boards = progress.get("deferred_boards") or []
                    cycle_key = command.get("cycle_id") or command.get("id")
                    recovery_token = None
                    is_local_self_resume = False
                    if command.get("executor") == "cloud" and bool(deferred_boards) and cycle_key:
                        recovery_token = (cycle_key, "cloud")
                    elif command.get("executor") == "local" and cycle_key and local_resume_counts.get(cycle_key, 0) < max_local_self_resumes:
                        ready_deferred = tuple(sorted(
                            str(b.get("platform") or "")
                            for b in deferred_boards
                            if isinstance(b, dict) and (b.get("retry_at") or 0) > 0 and (b.get("retry_at") or 0) <= now
                        ))
                        budget_continue = bool(progress.get("has_more")) and bool(progress.get("can_continue", True))
                        if ready_deferred or budget_continue:
                            recovery_token = (command.get("id") or cycle_key, "local", ready_deferred, budget_continue)
                            is_local_self_resume = True
                    if recovery_token and recovery_token not in recovered_cycles:
                        recovered_cycles.add(recovery_token)
                        if is_local_self_resume:
                            local_resume_counts[cycle_key] = local_resume_counts.get(cycle_key, 0) + 1
                        inbox.enqueue(
                            db_path,
                            queries=command.get("queries"),
                            key=key,
                            automatic=bool(command.get("automatic")),
                            resume=True,
                            restart=False,
                        )
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
