"""Short API-side dispatch; scraping runs on database workers."""
import json
import os
import time
import urllib.error
import urllib.request
from src import execution_inbox as inbox
from src.database import acquire_sync_lease, release_sync_lease, get_user_setting


def enabled():
    return os.environ.get("JOB_EXECUTOR") == "database"


def dispatch(command_id, workflow="scraper-worker.yml", inputs=None):
    token = os.environ.get("GITHUB_ACTIONS_TOKEN", "")
    if not token:
        raise RuntimeError("GitHub Actions dispatch token is not configured")
    repository = os.environ.get("GITHUB_SCRAPER_REPOSITORY", "louisricafrente-dev/job-accelerator")
    ref = os.environ.get("GITHUB_SCRAPER_REF", "master")
    request = urllib.request.Request(
        "https://api.github.com/repos/" + repository + "/actions/workflows/" + workflow + "/dispatches",
        data=json.dumps({"ref": ref, "inputs": inputs or {"command_id": command_id}}).encode(), method="POST",
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status not in (200, 204):
                raise RuntimeError("GitHub Actions did not accept the command")
    except urllib.error.HTTPError as error:
        raise RuntimeError("GitHub Actions dispatch failed (HTTP " + str(error.code) + ")") from None


def start(db_path, queries=None, automatic=False, resume=False, restart=False):
    if not os.environ.get("GITHUB_ACTIONS_TOKEN"):
        raise RuntimeError("GitHub Actions dispatch token is not configured")
    command = inbox.enqueue(db_path, queries, automatic=automatic, resume=resume, restart=restart)
    lease = str(int(time.time()) + 30) + "|" + command["id"]
    if not command.get("dispatched_at") and acquire_sync_lease(db_path, lease, int(time.time()), key="execution_dispatch"):
        try:
            dispatch(command["id"])
            for _ in range(5):
                raw = get_user_setting(db_path, inbox.KEY, "{}")
                current = json.loads(raw)
                if current.get("id") != command["id"]:
                    break
                current["dispatched_at"] = time.time()
                if inbox._replace(db_path, raw, current, inbox.KEY):
                    command = current
                    break
        finally:
            release_sync_lease(db_path, lease, key="execution_dispatch")
    return {"status": "queued", "is_syncing": True, "execution": inbox.public(command)}


def telemetry(db_path):
    command = inbox.public(inbox.read(db_path))
    shared = json.loads(get_user_setting(db_path, "sync_status", "{}") or "{}")
    shared["is_syncing"] = command.get("status") in inbox.ACTIVE
    if isinstance(command.get("result"), dict):
        shared["last_result"] = command["result"]
    if command.get("error"):
        shared["last_result"] = {"status": "error", "error": command["error"]}
    local = (command.get("executor") == "local" and command.get("status") == "running"
             and command.get("lease_until", 0) > time.time())
    presence = json.loads(get_user_setting(db_path, inbox.KEY + ":local", "{}") or "{}")
    shared.update(execution=command,
                  local_worker={"online": local, "last_seen_at": max(presence.get("last_seen_at", 0), command.get("local_last_seen", 0)), "presence_mode": "last_seen"},
                  local_request={**command, "status": command.get("status") if local else ""},
                  cloud_run={**command, "status": command.get("status") if not local else ""})
    return shared
