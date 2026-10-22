"""Durable cloud continuation; only a queue consumer executes batches."""
import asyncio
import json
import math
import os
import time
import uuid
from src.database import acquire_sync_lease, release_sync_lease, get_user_setting, set_user_setting
from src.sync_batches import CYCLE_SECONDS

RUN_KEY = "cloud_sync_run"
TOPIC = "job-sync"
ACTIVE = {"queued", "running", "waiting"}
RUN_SECONDS = CYCLE_SECONDS
STALE_SECONDS = 600


def read_run(db_path):
    raw = get_user_setting(db_path, RUN_KEY, "")
    return json.loads(raw) if raw else {}


def is_stale(run, check_deployment=True):
    deployment = os.environ.get("VERCEL_DEPLOYMENT_ID")
    moved = check_deployment and deployment and run.get("deployment_id") != deployment
    return (run.get("status") in ACTIVE and
            (moved or time.time() > max(run.get("updated_at", 0), run.get("next_at", 0)) + STALE_SECONDS))


def public_run(run):
    public = {key: value for key, value in run.items() if key != "queries"}
    if public.get("status") == "waiting" and public.get("next_at", 0) > time.time() + 30:
        public.update(status="partial", error="Cycle ended; unavailable sources are deferred to a later sync")
    if public.get("status") in ACTIVE:
        if public.get("expires_at", 0) <= time.time():
            public.update(status="partial", error="Cloud run expired; sync again to resume saved searches")
        elif is_stale(run, check_deployment=False):
            public.update(status="stalled", error="Cloud worker has not continued; sync again to recover")
    return public


async def publish(run_id, step, delay=0):
    from vercel.queue import send
    return await send(TOPIC, {"run_id": run_id, "step": step},
                      idempotency_key=f"{run_id}:{step}", delay=delay, retention=RUN_SECONDS)


def start_run(db_path, queries=None, automatic=False, resume=False):
    lease = f"{int(time.time()) + 30}|queue-start-{uuid.uuid4().hex}"
    if not acquire_sync_lease(db_path, lease, int(time.time()), key="cloud_sync_start_lease"):
        return {"status": "already_syncing", "is_syncing": True,
                "cloud_run": public_run(read_run(db_path))}
    try:
        return _start_run(db_path, queries, automatic, resume)
    finally:
        release_sync_lease(db_path, lease, key="cloud_sync_start_lease")


def _start_run(db_path, queries, automatic, resume=False):
    current = read_run(db_path)
    now = time.time()
    if current.get("status") == "waiting" and current.get("next_at", 0) > now + 30:
        current.update(status="partial", completed_at=now)
        set_user_setting(db_path, RUN_KEY, json.dumps(current))
    if current.get("status") in ACTIVE and current.get("expires_at", 0) > now:
        if is_stale(current):
            for key in ("sync_lease", "cloud_sync_worker_lease"):
                lease = get_user_setting(db_path, key, "0|")
                if int(lease.split("|", 1)[0]) > now:
                    return {"status": "already_syncing", "cloud_run": public_run(current), "is_syncing": True}
            recovery_lease = f"{int(now) + 30}|recover-{uuid.uuid4().hex}"
            if not acquire_sync_lease(db_path, recovery_lease, int(now), key="cloud_sync_worker_lease"):
                return {"status": "already_syncing", "cloud_run": public_run(current), "is_syncing": True}
            try:
                current = read_run(db_path)
                if not is_stale(current):
                    return {"status": "queued", "cloud_run": public_run(current), "is_syncing": True}
                # Invalidate late deliveries without resetting the saved search cycle.
                step = current.get("step", 0) + 1
                try:
                    delay = 1
                    asyncio.run(publish(current["id"], step, delay))
                except Exception as exc:
                    raise RuntimeError("Could not recover the cloud queue; saved searches are retained") from exc
                current.update(status="waiting" if delay > 2 else "queued", step=step,
                               updated_at=time.time(), next_at=time.time() + delay,
                               deployment_id=os.environ.get("VERCEL_DEPLOYMENT_ID"))
                set_user_setting(db_path, RUN_KEY, json.dumps(current))
            finally:
                release_sync_lease(db_path, recovery_lease, key="cloud_sync_worker_lease")
        return {"status": "queued", "cloud_run": public_run(current), "is_syncing": True}
    if not queries:
        from src.aggregator import DEFAULT_QUERIES
        saved = get_user_setting(db_path, "target_stack", "")
        queries = [q.strip() for q in saved.split(",") if q.strip()] or DEFAULT_QUERIES
    run = {"id": uuid.uuid4().hex, "queries": list(dict.fromkeys(queries)),
           "status": "queued", "automatic": automatic, "started_at": now,
           "expires_at": now + RUN_SECONDS, "step": 0, "updated_at": now,
           "deployment_id": os.environ.get("VERCEL_DEPLOYMENT_ID")}
    run["resume"] = resume
    if resume and current.get("status") != "complete" and current.get("queries") == run["queries"]:
        run["cycle_id"] = current.get("cycle_id", current.get("id", run["id"]))
    set_user_setting(db_path, RUN_KEY, json.dumps(run))
    try:
        asyncio.run(publish(run["id"], 0))
    except Exception as exc:
        run.update(status="error", error=f"Cloud queue unavailable: {exc}")
        set_user_setting(db_path, RUN_KEY, json.dumps(run))
        raise RuntimeError("Could not start the cloud queue; no unattended run was accepted") from exc
    return {"status": "queued", "cloud_run": public_run(run), "is_syncing": True}


def continuation_delay(progress, now):
    if progress.get("can_continue"):
        return 1
    return max(1, math.ceil(progress.get("next_run_at", now + 60) - now))



async def process_message(db_path, payload, aggregator):
    lease = f"{int(time.time()) + 360}|{uuid.uuid4().hex}"
    if not await asyncio.to_thread(acquire_sync_lease, db_path, lease, int(time.time()), key="cloud_sync_worker_lease"):
        raise RuntimeError("Another cloud worker is processing this run; retry delivery")
    try:
        await _process_message(db_path, payload, aggregator)
    finally:
        await asyncio.to_thread(release_sync_lease, db_path, lease, key="cloud_sync_worker_lease")


async def _process_message(db_path, payload, aggregator):
    run = await asyncio.to_thread(read_run, db_path)
    if run.get("id") != payload.get("run_id") or run.get("status") not in ACTIVE:
        return
    step = int(payload.get("step", 0))
    if step < run.get("step", 0):
        return
    now = time.time()
    if now >= run["expires_at"]:
        run.update(status="partial", completed_at=now, error="One-hour cycle limit reached; unfinished searches remain saved")
    elif run.get("automatic") and await asyncio.to_thread(get_user_setting, db_path, "auto_sync_enabled", "1") in ("0", "false"):
        run.update(status="paused")
    else:
        run.update(status="running", updated_at=now, deployment_id=os.environ.get("VERCEL_DEPLOYMENT_ID"))
        await asyncio.to_thread(set_user_setting, db_path, RUN_KEY, json.dumps(run))
        result = await asyncio.to_thread(aggregator.run_sync, queries=run["queries"], budget_seconds=120, cycle_id=run.get("cycle_id", run["id"]), resume=run.get("resume", False))
        if result.get("status") != "already_syncing":
            totals = run.setdefault("totals", {"added": 0, "skipped": 0, "total_fetched": 0, "platforms": {}})
            for key in ("added", "skipped", "total_fetched"):
                totals[key] += result.get(key, 0)
            for platform, count in result.get("platforms", {}).items():
                totals["platforms"][platform] = totals["platforms"].get(platform, 0) + count
            run["result"] = {**result, **totals}
            await asyncio.to_thread(set_user_setting, db_path, RUN_KEY, json.dumps(run))
        progress = result.get("progress", {})
        if result.get("status") == "already_syncing":
            delay = 30
        elif result.get("status") == "error":
            run.update(status="error", completed_at=time.time(), error=result.get("error", "Database ingestion failed; checkpoint retained"))
            delay = None
        elif not progress.get("has_more"):
            run.update(status="partial" if result.get("status") == "partial" or progress.get("unfinished") else "complete", completed_at=time.time())
            delay = None
        elif not progress.get("can_continue", True) and progress.get("next_run_at", 0) > time.time() + 30:
            run.update(status="partial", completed_at=time.time(), error="Unavailable sources deferred; cycle finished")
            delay = None
        else:
            delay = continuation_delay(progress, time.time())
        if delay is not None:
            if time.time() + delay >= run["expires_at"]:
                run.update(status="partial", completed_at=time.time(), error="One-hour cycle limit reached; unfinished searches remain saved")
            else:
                # Publish before advancing step: an interrupted send is retried with the same key.
                await publish(run["id"], step + 1, delay)
                run.update(status="waiting" if delay > 2 else "queued", step=step + 1,
                           next_at=time.time() + delay)
    run["updated_at"] = time.time()
    await asyncio.to_thread(set_user_setting, db_path, RUN_KEY, json.dumps(run))
