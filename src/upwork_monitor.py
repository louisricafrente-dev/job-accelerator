"""Daily Upwork slot, consumed only from the midnight scrape queue."""
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from src.database import acquire_sync_lease, get_user_setting

RUN_KEY = "upwork_monitor_run"


def claim(db_path, source):
    if source != "daily" or get_user_setting(db_path, "auto_sync_enabled", "1").strip().lower() in ("0", "false"):
        return False
    now = datetime.now(ZoneInfo("Asia/Manila"))
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    lease = f"{int(tomorrow.timestamp())}|daily-{uuid.uuid4().hex}"
    return acquire_sync_lease(db_path, lease, int(time.time()), key="upwork_daily_slot")


def poll_cloud(db_path, ignore_local=False):
    return {"status": "disabled", "reason": "Upwork runs in the midnight scrape only"}


async def start(db_path):
    return poll_cloud(db_path)


async def process(db_path, payload):
    # Drain old deliveries without fetching or scheduling another callback.
    return
