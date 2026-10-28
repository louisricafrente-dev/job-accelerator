"""One scrape and one separate digest per Manila calendar day."""
import json
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from src.database import acquire_sync_lease, release_sync_lease, get_user_setting, set_user_setting


def day():
    return datetime.now(ZoneInfo("Asia/Manila")).date().isoformat()


def has_unfinished(db_path):
    for key in ("sync_status", "local_sync_request", "cloud_sync_run"):
        value = json.loads(get_user_setting(db_path, key, "{}") or "{}")
        result = value.get("last_result") or value.get("result") or {}
        progress = value.get("progress") or result.get("progress") or {}
        if progress:
            return bool(progress.get("has_more") or progress.get("unfinished"))
    return False


def start_daily(db_path, start):
    today = day()
    if get_user_setting(db_path, "daily_scrape_day", "") == today:
        return {"status": "already_scheduled", "day": today}
    lease = f"{int(time.time()) + 120}|{uuid.uuid4().hex}"
    if not acquire_sync_lease(db_path, lease, int(time.time()), key="daily_scrape_start"):
        return {"status": "already_scheduling"}
    try:
        if get_user_setting(db_path, "daily_scrape_day", "") == today:
            return {"status": "already_scheduled", "day": today}
        result = start(automatic=True, resume=has_unfinished(db_path))
        if result.get("status") not in {"error", "failed"}:
            set_user_setting(db_path, "daily_scrape_day", today)
        return result
    finally:
        release_sync_lease(db_path, lease, key="daily_scrape_start")


def send_digest(db_path, send):
    today = day()
    if get_user_setting(db_path, "daily_digest_day", "") == today:
        return {"success": True, "status": "already_sent", "day": today}
    lease = f"{int(time.time()) + 120}|{uuid.uuid4().hex}"
    if not acquire_sync_lease(db_path, lease, int(time.time()), key="daily_digest_send"):
        return {"success": False, "status": "already_sending"}
    try:
        if get_user_setting(db_path, "daily_digest_day", "") == today:
            return {"success": True, "status": "already_sent", "day": today}
        result = send(db_path)
        if result.get("success"):
            set_user_setting(db_path, "daily_digest_day", today)
        return result
    finally:
        release_sync_lease(db_path, lease, key="daily_digest_send")
