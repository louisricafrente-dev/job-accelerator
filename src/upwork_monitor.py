"""One shared polling slot for the local collector and cloud fallback."""
import asyncio
import json
import os
import time
import uuid

from src.database import acquire_sync_lease, get_user_setting, insert_jobs, release_sync_lease, set_user_setting

INTERVAL = 600
LOCAL_GRACE = 900
RUN_KEY = "upwork_monitor_run"


def read(db_path, key):
    return json.loads(get_user_setting(db_path, key, "{}") or "{}")


def claim(db_path, source):
    now = time.time()
    if get_user_setting(db_path, "auto_sync_enabled", "1").strip().lower() in ("0", "false"):
        return False
    if source == "local":
        set_user_setting(db_path, "upwork_local_seen", str(now))
    slot = f"{int(now) + INTERVAL}|{source}-{uuid.uuid4().hex}"
    return acquire_sync_lease(db_path, slot, int(now), key="upwork_poll_slot")


def poll_cloud(db_path, ignore_local=False):
    if get_user_setting(db_path, "auto_sync_enabled", "1").strip().lower() in ("0", "false"):
        return {"status": "paused"}
    seen = float(get_user_setting(db_path, "upwork_local_seen", "0") or "0")
    if not ignore_local and time.time() - seen < LOCAL_GRACE:
        return {"status": "local_online"}
    if not claim(db_path, "cloud"):
        return {"status": "cooldown"}
    from src.connectors.remote_feed import UpworkConnector
    from src.connectors.upwork_flconsole import fetch_jobs
    connector = UpworkConnector()
    connector.last_error = ""
    jobs = fetch_jobs(connector)
    added, skipped = insert_jobs(db_path, jobs) if not connector.last_error else (0, 0)
    status = {"checked_at": time.time(), "fetched": len(jobs), "added": added,
              "skipped": skipped, "error": connector.last_error, "source": "cloud"}
    set_user_setting(db_path, "upwork_feed_status", json.dumps(status))
    return status


async def publish(run_id, step, delay=0):
    from vercel.queue import send
    from src.cloud_sync import TOPIC
    await send(TOPIC, {"kind": "upwork_monitor", "run_id": run_id, "step": step},
               idempotency_key=f"upwork:{run_id}:{step}", delay=delay, retention=3600)


async def start(db_path):
    now = time.time()
    lease = f"{int(now) + 60}|{uuid.uuid4().hex}"
    if not acquire_sync_lease(db_path, lease, int(now), key="upwork_monitor_start"):
        return {"status": "already_running"}
    try:
        run = read(db_path, RUN_KEY)
        deployment = os.environ.get("VERCEL_DEPLOYMENT_ID", "")
        if not run.get("paused") and run.get("deployment") == deployment and run.get("next_at", 0) + 900 > now:
            return {"status": "already_running", "next_at": run["next_at"]}
        run = {"id": uuid.uuid4().hex, "step": 0, "next_at": now, "deployment": deployment}
        set_user_setting(db_path, RUN_KEY, json.dumps(run))
        await publish(run["id"], 0)
        return {"status": "queued"}
    finally:
        release_sync_lease(db_path, lease, key="upwork_monitor_start")


async def process(db_path, payload):
    run = read(db_path, RUN_KEY)
    if payload.get("run_id") != run.get("id") or payload.get("step") != run.get("step"):
        return
    if get_user_setting(db_path, "auto_sync_enabled", "1").strip().lower() in ("0", "false"):
        run.update(paused=True, next_at=0)
        set_user_setting(db_path, RUN_KEY, json.dumps(run))
        return
    await asyncio.to_thread(poll_cloud, db_path)
    if read(db_path, RUN_KEY).get("id") != run["id"]:
        return
    step = run["step"] + 1
    # Idempotent send precedes checkpoint advancement so interrupted callbacks retry safely.
    await publish(run["id"], step, INTERVAL)
    run.update(step=step, next_at=time.time() + INTERVAL)
    set_user_setting(db_path, RUN_KEY, json.dumps(run))
