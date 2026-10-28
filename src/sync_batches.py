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
CYCLE_SECONDS = 2 * 3600
OWNERSHIP_CHECK_SECONDS = 15


def run_batch(aggregator, queries, budget_seconds=150, workers=12, cycle_id=None, resume=False, restart=False):
    queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
    if not queries:
        return {"status": "error", "error": "No search keywords", "added": 0}
    if not aggregator._sync_lock.acquire(blocking=False):
        return {"status": "already_syncing", "is_syncing": True}
    guard = getattr(aggregator, "execution_guard", None)
    lease_expiry = int(guard["lease_until"]) if guard else int(time.time()) + 600
    lease = f"{lease_expiry}|{uuid.uuid4().hex}"
    acquired = False
    aggregator.is_syncing = True
    try:
        acquired = acquire_sync_lease(aggregator.db_path, lease, int(time.time()))
        if not acquired:
            return {"status": "already_syncing", "is_syncing": True}
        query_set = set(queries)
        signature = hashlib.sha256(json.dumps(queries).encode()).hexdigest()
        raw = get_user_setting(aggregator.db_path, PROGRESS_KEY, "")
        checkpoint = json.loads(raw) if raw and not restart else {}
        saved_status = json.loads(get_user_setting(aggregator.db_path, "sync_status", "{}") or "{}")
        aggregator.last_sync_time = saved_status.get("last_successful_fetch", 0)
        new_cycle = restart or (cycle_id is not None and checkpoint.get("cycle_id") != cycle_id)
        if checkpoint.get("signature") != signature or new_cycle:
            previous = {} if restart else checkpoint.get("boards", {})
            checkpoint = {"signature": signature, "boards": {}, "next_board": 0}
            for connector in aggregator.connectors:
                old = previous.get(connector.platform, {})
                is_feed = not restart and getattr(connector, "is_feed", False) and old.get("next_at", 0) > time.time() and not old.get("last_error")
                completed_queries = {
                    query: fetched_at for query, fetched_at in old.get("completed_queries", {}).items()
                    if query in query_set and fetched_at > time.time() - REFRESH_SECONDS
                } if (not restart and not getattr(connector, "is_feed", False)) else {}
                pending_queries = [index for index, query in enumerate(queries) if query not in completed_queries]
                checkpoint["boards"][connector.platform] = {
                    "feed_state": old.get("feed_state", {}),
                    "individual_queries": [q for q in old.get("individual_queries", []) if q in query_set],
                    "completed_queries": completed_queries,
                    "cursor": old.get("cursor", 0) if is_feed else len(queries) if completed_queries else 0,
                    "retry": old.get("retry", []) if is_feed else pending_queries if completed_queries else [],
                    "next_at": old.get("next_at", 0) if is_feed else max(
                        old.get("blocked_until", 0),
                        min(completed_queries.values()) + REFRESH_SECONDS if completed_queries and not pending_queries else 0,
                    ),
                    "blocked_until": old.get("blocked_until", 0),
                    "last_error": old.get("last_error", ""),
                    "revision": old.get("revision", 1),
                }
        refresh_completed = cycle_id is None or checkpoint.get("cycle_id") != cycle_id
        if cycle_id is not None:
            checkpoint["cycle_id"] = cycle_id
        valid_platforms = {c.platform for c in aggregator.connectors}
        checkpoint["boards"] = {p: s for p, s in checkpoint.get("boards", {}).items() if p in valid_platforms}
        boards = checkpoint["boards"]
        now = time.time()
        for connector in aggregator.connectors:
            state = boards.setdefault(connector.platform, {"cursor": 0, "retry": [], "next_at": 0})
            connector.daily_sync = bool(getattr(aggregator, "daily_run", False))
            if connector.platform == "Upwork" and connector.daily_sync:
                from src.daily_schedule import day
                if state.get("daily_day") != day():
                    state.update(cursor=0, retry=[], next_at=0, deferred=False, daily_day=day())
            total = 1 if getattr(connector, "is_feed", False) else len(queries)
            revision = getattr(connector, "revision", 1)
            if state.get("revision", 1) != revision:
                state.update(cursor=0, retry=[], completed_queries={}, individual_queries=[], feed_state={}, next_at=state.get("blocked_until", 0))
                if "404" in state.get("last_error", ""):
                    state.update(blocked_until=0, next_at=0, last_error="", deferred=False)
                state["revision"] = revision
            if state.get("blocked_until", 0) > now and state.get("last_error"):
                state["deferred"] = True
            elif resume or cycle_id is None:
                state["deferred"] = False
            if refresh_completed and state["cursor"] >= total and not state["retry"] and state.get("next_at", 0) <= now:
                state.update(cursor=0, retry=[], completed_queries={})
        result = {"status": "ok", "added": 0, "skipped": 0, "total_fetched": 0, "platforms": {}, "is_syncing": True}
        telemetry = {connector.platform: {
            "status": ("deferred" if boards[connector.platform].get("deferred") else "complete" if boards[connector.platform]["cursor"] >= (1 if getattr(connector, "is_feed", False) else len(queries)) and not boards[connector.platform]["retry"]
                       else "cooldown" if boards[connector.platform].get("next_at", 0) > now else "ready"),
            "count": 0, "tier": connector.tier, "error": boards[connector.platform].get("last_error", ""),
            "route": boards[connector.platform].get("route", ""), "connection_retries": boards[connector.platform].get("connection_retries", 0)
        } for connector in aggregator.connectors}

        def progress():
            query_boards = [c for c in aggregator.connectors if not getattr(c, "is_feed", False)]
            completed = sum(max(0, boards[c.platform]["cursor"] - len(boards[c.platform]["retry"])) for c in query_boards)
            total = len(queries) * len(query_boards)
            unfinished = [c for c in aggregator.connectors if boards[c.platform]["cursor"] < (1 if getattr(c, "is_feed", False) else len(queries)) or boards[c.platform]["retry"]]
            remaining = [boards[c.platform] for c in unfinished if not boards[c.platform].get("deferred")]
            deferred = [{"platform": c.platform, "error": boards[c.platform].get("last_error", ""),
                         "retry_at": boards[c.platform].get("blocked_until", 0)} for c in unfinished if boards[c.platform].get("deferred")]
            return {"next_run_at": min((state.get("next_at", 0) for state in remaining), default=0), "keywords": len(queries), "completed_searches": completed, "total_searches": total,
                    "can_continue": any(state.get("next_at", 0) <= time.time() + QUERY_DELAY_SECONDS + 0.1 for state in remaining),
                    "has_more": bool(remaining), "unfinished": bool(unfinished), "deferred_boards": deferred,
                    "boards": {c.platform: {key: value for key, value in boards[c.platform].items()
                                             if key not in ("completed_queries", "individual_queries")} for c in aggregator.connectors}}

        next_execution_check = 0

        def check_execution():
            nonlocal next_execution_check
            guard = getattr(aggregator, "execution_guard", None)
            if guard and time.monotonic() >= next_execution_check:
                from src.execution_inbox import owned
                from src.database import ExecutionLeaseLost
                if not owned(aggregator.db_path, guard, key=guard["key"]):
                    raise ExecutionLeaseLost("Execution ownership changed; discard stale results")
                next_execution_check = time.monotonic() + OWNERSHIP_CHECK_SECONDS

        def persist():
            check_execution()
            result["progress"] = progress()
            result["telemetry"] = telemetry
            result["logs"] = list(aggregator.sync_logs)
            aggregator.last_sync_result = result
            aggregator.platform_telemetry = telemetry
            set_sync_checkpoint(aggregator.db_path, json.dumps(checkpoint), json.dumps({
                "is_syncing": result["is_syncing"], "last_sync_time": aggregator.last_sync_time,
                "last_successful_fetch": aggregator.last_sync_time,
                "total_boards": len(aggregator.connectors), "last_result": {**result, "status": "running"} if result["is_syncing"] else result,
                "telemetry": telemetry, "logs": result["logs"], "progress": result["progress"]}), **({"execution_guard": aggregator.execution_guard} if getattr(aggregator, "execution_guard", None) else {}))

        def fetch(connector, indices):
            started_at = time.monotonic()
            connector.last_error = ""
            connector.last_route = "CACHE"
            connector.connection_retries = 0
            connector.retry_after = 0
            try:
                connector.last_fetch_mode = "individual"
                connector.last_group_incomplete = False
                if getattr(connector, "is_feed", False):
                    connector.last_fetch_mode = "feed"
                    if getattr(connector, "checkpointed_feed", False) is True:
                        connector.feed_state = dict(boards[connector.platform].get("feed_state", {}))
                    jobs = connector.fetch()
                elif len(indices) > 1:
                    method = connector.fetch_group_step if getattr(connector, "supports_group_steps", False) is True else connector.fetch_group
                    jobs = method([queries[index] for index in indices])
                else:
                    jobs = connector.fetch(query=queries[indices[0]])
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
                check_execution()
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
                        if connector.platform in active or state.get("deferred") or state.get("next_at", 0) > now:
                            continue
                        if state["cursor"] >= total and not state["retry"]:
                            continue
                        index = state["cursor"] if state["cursor"] < total else state["retry"][0]
                        # A failed search is deferred, not repeatedly attempted within this run.
                        task_key = (connector.platform, index)
                        if task_key in started:
                            continue
                        group_size = 1 if getattr(connector, "is_feed", False) else connector.query_group_size
                        if queries[index] in state.get("individual_queries", []) and not getattr(connector, "is_feed", False):
                            group_size = 1
                        candidates = (list(range(index, min(total, index + group_size)))
                                      if state["cursor"] < total else state["retry"][:group_size])
                        indices = [i for i in candidates if (connector.platform, i) not in started]
                        if len(indices) > 1 and any(queries[i] in state.get("individual_queries", []) for i in indices):
                            indices = indices[:1]
                        started.update((connector.platform, i) for i in indices)
                        active.add(connector.platform)
                        telemetry[connector.platform]["status"] = "fetching"
                        pending[executor.submit(fetch, connector, indices)] = (connector, indices)
                        checkpoint["next_board"] = (position + 1) % len(connectors)
                if not pending:
                    soon = []
                    for connector in connectors:
                        state = boards[connector.platform]
                        total = 1 if getattr(connector, "is_feed", False) else len(queries)
                        index = state["cursor"] if state["cursor"] < total else (state["retry"][0] if state["retry"] else None)
                        if not state.get("deferred") and index is not None and (connector.platform, index) not in started:
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
                    connector, indices = pending.pop(future)
                    jobs, error, fetch_seconds = future.result()
                    relevant = [job for job in jobs if is_within_15_days(job.date_posted)
                                and is_relevant_opportunity(job.title, job.description, allow_va_training=True)]
                    completed.append((connector, indices, jobs, error, fetch_seconds, relevant))
                    combined_jobs.extend(relevant)
                save_started_at = time.monotonic()
                save_error = ""
                if completed:
                    try:
                        check_execution()
                        added, skipped = insert_jobs(aggregator.db_path, combined_jobs, sync_cache=sync_cache, **({"execution_guard": aggregator.execution_guard} if getattr(aggregator, "execution_guard", None) else {})) if combined_jobs else (0, 0)
                        result["added"] += added
                        result["skipped"] += skipped
                    except Exception as exc:
                        ingestion_failed = True
                        save_error = f"Database ingestion failed: {exc}"
                        result["error"] = save_error
                        # A partial write can leave the in-memory dedup catalog ahead of storage.
                        sync_cache.clear()
                save_seconds = time.monotonic() - save_started_at
                for connector, indices, jobs, error, fetch_seconds, relevant in completed:
                    active.remove(connector.platform)
                    state = boards[connector.platform]
                    state["route"] = getattr(connector, "last_route", "")
                    state["connection_retries"] = getattr(connector, "connection_retries", 0)
                    result["total_fetched"] += len(jobs)
                    result["platforms"][connector.platform] = result["platforms"].get(connector.platform, 0) + len(jobs)
                    if save_error:
                        state["next_at"] = time.time() + ERROR_COOLDOWN_SECONDS
                        state["last_error"] = save_error
                        telemetry[connector.platform] = {"status": "error", "count": len(jobs), "tier": connector.tier, "error": save_error}
                        continue
                    group_pending = not error and getattr(connector, "last_group_incomplete", False) is True
                    more_pages = not error and getattr(connector, "checkpointed_feed", False) is True and connector.has_more
                    if not more_pages:
                        for index in indices:
                            if index == state["cursor"]:
                                state["cursor"] += 1
                    if error:
                        state["deferred"] = True
                        state["last_error"] = error
                        for index in indices:
                            if index not in state["retry"]:
                                state["retry"].append(index)
                        blocked = any(code in error.lower() for code in ("429", "403", "404", "410", "captcha", "rate limit", "forbidden", "cloudflare challenge", "requires verification"))
                        cooldown_secs = BLOCK_COOLDOWN_SECONDS if blocked else ERROR_COOLDOWN_SECONDS
                        state["next_at"] = time.time() + max(cooldown_secs, getattr(connector, "retry_after", 0))
                        state["blocked_until"] = state["next_at"]
                        result["status"] = "partial"
                    else:
                        state["last_error"] = ""
                        aggregator.last_sync_time = time.time()
                        if getattr(connector, "checkpointed_feed", False) is True:
                            state["feed_state"] = dict(connector.next_feed_state)
                            if more_pages:
                                state["cursor"] = 0
                                started.difference_update((connector.platform, index) for index in indices)
                        if not getattr(connector, "is_feed", False) and not group_pending:
                            for index in indices:
                                state.setdefault("completed_queries", {})[queries[index]] = time.time()
                        for index in indices:
                            if group_pending:
                                if index not in state["retry"]:
                                    state["retry"].append(index)
                                if queries[index] not in state.setdefault("individual_queries", []):
                                    state["individual_queries"].append(queries[index])
                                started.discard((connector.platform, index))
                            elif index in state["retry"]:
                                state["retry"].remove(index)
                        total = 1 if getattr(connector, "is_feed", False) else len(queries)
                        state["next_at"] = time.time() + (REFRESH_SECONDS if state["cursor"] >= total and not state["retry"] else QUERY_DELAY_SECONDS)
                    telemetry[connector.platform] = {"status": "error" if error else "active", "count": len(jobs), "tier": connector.tier, "error": error,
                                                     "fetch_seconds": round(fetch_seconds, 3), "save_seconds": round(save_seconds, 3),
                                                     "keywords_searched": len(indices), "search_mode": connector.last_fetch_mode,
                                                     "route": getattr(connector, "last_route", ""), "connection_retries": getattr(connector, "connection_retries", 0)}
                    if getattr(connector, "checkpointed_feed", False) is True:
                        feed = state.get("feed_state", {})
                        label = f"catalogue page {feed.get('pages_saved', 0)}, {feed.get('total', 0)} source listings"
                        if feed.get("days"):
                            label += f" in {feed['days']}-day window"
                    else:
                        label = f"{len(indices)} keyword(s), search {indices[0] + 1}-{indices[-1] + 1} ({connector.last_fetch_mode})"
                    aggregator.log_event(f"[{connector.platform}] Saved {label}: {len(relevant)} relevant jobs (fetch {fetch_seconds:.2f}s, save {save_seconds:.2f}s; {getattr(connector, 'last_route', 'DIRECT')}; {getattr(connector, 'connection_retries', 0)} connection retries)" + (f"; {error}" if error else ""))
                if done:
                    persist()
        if ingestion_failed:
            result["status"] = "error"
        elif any(state["retry"] or state.get("deferred") for state in boards.values()):
            result["status"] = "partial"
        result["is_syncing"] = False
        result["timestamp"] = time.time()
        aggregator.last_sync_result = result
        aggregator.platform_telemetry = telemetry
        persist()
        return result
    finally:
        aggregator.is_syncing = False
        if acquired:
            release_sync_lease(aggregator.db_path, lease)
        aggregator._sync_lock.release()
