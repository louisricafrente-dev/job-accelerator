"""Cloud sync with durable per-board cursors and incremental ingestion."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
import time
import uuid

from src.classifier import is_relevant_opportunity
from src.database import acquire_sync_lease, release_sync_lease, get_user_setting, set_sync_checkpoint, insert_jobs
from src.models import is_within_15_days

PROGRESS_KEY = "sync_batch_progress"
QUERY_DELAY_SECONDS = 2
REFRESH_SECONDS = 6 * 3600
ERROR_COOLDOWN_SECONDS = 15 * 60
BLOCK_COOLDOWN_SECONDS = 6 * 3600


def run_batch(aggregator, queries, budget_seconds=150, workers=12, cycle_id=None):
    try:
        from src.proxy_manager import apply_proxy_environment
        apply_proxy_environment(aggregator.db_path)
    except Exception:
        pass
    queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
    if not queries:
        return {"status": "error", "error": "No search keywords", "added": 0}
    if not aggregator._sync_lock.acquire(blocking=False):
        return {"status": "already_syncing", "is_syncing": True}
    lease = f"{int(time.time()) + 600}|{uuid.uuid4().hex}"
    acquired = False
    aggregator.is_syncing = True
    try:
        acquired = acquire_sync_lease(aggregator.db_path, lease, int(time.time()))
        if not acquired:
            return {"status": "already_syncing", "is_syncing": True}
        signature = hashlib.sha256(json.dumps(queries).encode()).hexdigest()
        raw = get_user_setting(aggregator.db_path, PROGRESS_KEY, "")
        checkpoint = json.loads(raw) if raw else {}
        if checkpoint.get("signature") != signature:
            previous = checkpoint.get("boards", {})
            checkpoint = {"signature": signature, "boards": {}, "next_board": 0}
            for connector in aggregator.connectors:
                old = previous.get(connector.platform, {})
                is_feed = getattr(connector, "is_feed", False)
                checkpoint["boards"][connector.platform] = {
                    "cursor": old.get("cursor", 0) if is_feed else 0,
                    "retry": old.get("retry", []) if is_feed else [],
                    "next_at": old.get("next_at", 0) if is_feed else old.get("blocked_until", 0),
                    "blocked_until": old.get("blocked_until", 0),
                    "last_error": old.get("last_error", ""),
                }
        refresh_completed = cycle_id is None or checkpoint.get("cycle_id") != cycle_id
        if cycle_id is not None:
            checkpoint["cycle_id"] = cycle_id
        boards = checkpoint["boards"]
        now = time.time()
        for connector in aggregator.connectors:
            state = boards.setdefault(connector.platform, {"cursor": 0, "retry": [], "next_at": 0})
            total = 1 if getattr(connector, "is_feed", False) else len(queries)
            if refresh_completed and state["cursor"] >= total and not state["retry"] and state.get("next_at", 0) <= now:
                state.update(cursor=0, retry=[])
        result = {"status": "ok", "added": 0, "skipped": 0, "total_fetched": 0, "platforms": {}, "is_syncing": True}
        telemetry = {connector.platform: {
            "status": "cooldown" if boards[connector.platform].get("next_at", 0) > now else "ready",
            "count": 0, "tier": connector.tier, "error": boards[connector.platform].get("last_error", "")
        } for connector in aggregator.connectors}

        def progress():
            query_boards = [c for c in aggregator.connectors if not getattr(c, "is_feed", False)]
            completed = sum(max(0, boards[c.platform]["cursor"] - len(boards[c.platform]["retry"])) for c in query_boards)
            total = len(queries) * len(query_boards)
            remaining = [boards[c.platform] for c in aggregator.connectors
                         if boards[c.platform]["cursor"] < (1 if getattr(c, "is_feed", False) else len(queries)) or boards[c.platform]["retry"]]
            return {"next_run_at": min((state.get("next_at", 0) for state in remaining), default=0), "keywords": len(queries), "completed_searches": completed, "total_searches": total,
                    "can_continue": any(state.get("next_at", 0) <= time.time() + QUERY_DELAY_SECONDS + 0.1 for state in remaining),
                    "has_more": any(boards[c.platform]["cursor"] < (1 if getattr(c, "is_feed", False) else len(queries)) or boards[c.platform]["retry"] for c in aggregator.connectors), "boards": {c.platform: dict(boards[c.platform]) for c in aggregator.connectors}}

        def persist():
            result["progress"] = progress()
            result["telemetry"] = telemetry
            result["logs"] = list(aggregator.sync_logs)
            aggregator.last_sync_result = result
            aggregator.platform_telemetry = telemetry
            set_sync_checkpoint(aggregator.db_path, json.dumps(checkpoint), json.dumps({
                "is_syncing": result["is_syncing"], "last_sync_time": aggregator.last_sync_time,
                "total_boards": len(aggregator.connectors), "last_result": {**result, "status": "running"} if result["is_syncing"] else result,
                "telemetry": telemetry, "logs": result["logs"], "progress": result["progress"]}))

        def fetch(connector, index):
            started_at = time.monotonic()
            connector.last_error = ""
            try:
                jobs = connector.fetch() if getattr(connector, "is_feed", False) else connector.fetch(query=queries[index])
                error = getattr(connector, "last_error", "")
                return jobs, error if isinstance(error, str) else "", time.monotonic() - started_at
            except Exception as exc:
                return [], str(exc) or type(exc).__name__, time.monotonic() - started_at

        persist()
        deadline = time.monotonic() + max(0, budget_seconds)
        pending = {}
        active = set()
        started = set()
        ingestion_failed = False
        sync_cache = {}
        connectors = aggregator.connectors
        with ThreadPoolExecutor(max_workers=workers) as executor:
            while True:
                now = time.time()
                can_start = time.monotonic() < deadline
                if can_start and connectors:
                    start = checkpoint.get("next_board", 0) % len(connectors)
                    for offset in range(len(connectors)):
                        if len(pending) >= workers or time.monotonic() >= deadline:
                            break
                        position = (start + offset) % len(connectors)
                        connector = connectors[position]
                        state = boards[connector.platform]
                        total = 1 if getattr(connector, "is_feed", False) else len(queries)
                        if connector.platform in active or state.get("next_at", 0) > now:
                            continue
                        if state["cursor"] >= total and not state["retry"]:
                            continue
                        index = state["cursor"] if state["cursor"] < total else state["retry"][0]
                        # A failed search is deferred, not repeatedly attempted within this run.
                        task_key = (connector.platform, index)
                        if task_key in started:
                            continue
                        started.add(task_key)
                        active.add(connector.platform)
                        telemetry[connector.platform]["status"] = "fetching"
                        pending[executor.submit(fetch, connector, index)] = (connector, index)
                        checkpoint["next_board"] = (position + 1) % len(connectors)
                if not pending:
                    soon = []
                    for connector in connectors:
                        state = boards[connector.platform]
                        total = 1 if getattr(connector, "is_feed", False) else len(queries)
                        index = state["cursor"] if state["cursor"] < total else (state["retry"][0] if state["retry"] else None)
                        if index is not None and (connector.platform, index) not in started:
                            soon.append(state.get("next_at", 0) - time.time())
                    if can_start and soon and min(soon) <= QUERY_DELAY_SECONDS + 0.1:
                        time.sleep(min(0.25, max(0.01, min(soon))))
                        continue
                    break
                done, _ = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                # Include boards that finished while earlier results were being saved.
                done.update(future for future in pending if future.done())
                completed = []
                combined_jobs = []
                for future in done:
                    connector, index = pending.pop(future)
                    jobs, error, fetch_seconds = future.result()
                    relevant = [job for job in jobs if is_within_15_days(job.date_posted)
                                and is_relevant_opportunity(job.title, job.description, allow_va_training=True)]
                    completed.append((connector, index, jobs, error, fetch_seconds, relevant))
                    combined_jobs.extend(relevant)
                save_started_at = time.monotonic()
                save_error = ""
                if completed:
                    try:
                        added, skipped = insert_jobs(aggregator.db_path, combined_jobs, sync_cache=sync_cache) if combined_jobs else (0, 0)
                        result["added"] += added
                        result["skipped"] += skipped
                    except Exception as exc:
                        ingestion_failed = True
                        save_error = f"Database ingestion failed: {exc}"
                        result["error"] = save_error
                        # A partial write can leave the in-memory dedup catalog ahead of storage.
                        sync_cache.clear()
                save_seconds = time.monotonic() - save_started_at
                for connector, index, jobs, error, fetch_seconds, relevant in completed:
                    active.remove(connector.platform)
                    state = boards[connector.platform]
                    result["total_fetched"] += len(jobs)
                    result["platforms"][connector.platform] = result["platforms"].get(connector.platform, 0) + len(jobs)
                    if save_error:
                        state["next_at"] = time.time() + ERROR_COOLDOWN_SECONDS
                        state["last_error"] = save_error
                        telemetry[connector.platform] = {"status": "error", "count": len(jobs), "tier": connector.tier, "error": save_error}
                        continue
                    if index == state["cursor"]:
                        state["cursor"] += 1
                    if error:
                        state["last_error"] = error
                        if index not in state["retry"]:
                            state["retry"].append(index)
                        blocked = any(code in error.lower() for code in ("429", "403", "captcha", "rate limit", "forbidden"))
                        state["next_at"] = time.time() + (BLOCK_COOLDOWN_SECONDS if blocked else ERROR_COOLDOWN_SECONDS)
                        state["blocked_until"] = state["next_at"]
                        result["status"] = "partial"
                    else:
                        state["last_error"] = ""
                        if index in state["retry"]:
                            state["retry"].remove(index)
                        total = 1 if getattr(connector, "is_feed", False) else len(queries)
                        state["next_at"] = time.time() + (REFRESH_SECONDS if state["cursor"] >= total and not state["retry"] else QUERY_DELAY_SECONDS)
                    telemetry[connector.platform] = {"status": "error" if error else "active", "count": len(jobs), "tier": connector.tier, "error": error,
                                                     "fetch_seconds": round(fetch_seconds, 3), "save_seconds": round(save_seconds, 3)}
                    aggregator.log_event(f"[{connector.platform}] Saved search {index + 1}: {len(relevant)} relevant jobs (fetch {fetch_seconds:.2f}s, save {save_seconds:.2f}s)" + (f"; {error}" if error else ""))
                if done:
                    persist()
        if ingestion_failed:
            result["status"] = "error"
        elif any(state["retry"] for state in boards.values()):
            result["status"] = "partial"
        result["is_syncing"] = False
        result["timestamp"] = time.time()
        if not ingestion_failed:
            aggregator.last_sync_time = time.time()
        aggregator.last_sync_result = result
        aggregator.platform_telemetry = telemetry
        persist()
        return result
    finally:
        aggregator.is_syncing = False
        if acquired:
            release_sync_lease(aggregator.db_path, lease)
        aggregator._sync_lock.release()
