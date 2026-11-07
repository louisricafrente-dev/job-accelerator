"""Isolated, synthetic guest data. No master rows or settings are copied."""

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from src.database import init_db


SAMPLES = (
    ("Junior Software Developer", "Sample Studio", "Remote - Philippines", "Web/Software Dev"),
    ("Android Developer", "Example Mobile", "Remote - Philippines", "Mobile / Android"),
    ("Frontend Developer", "Sample Digital", "Manila, Philippines", "Web/Software Dev"),
    ("Backend Developer", "Example Systems", "Remote - Philippines", "Web/Software Dev"),
    ("Video Editor", "Sample Creative", "Remote - Philippines", "Video Editor"),
)


def guest_path(guest_id: str, master_db_path: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(master_db_path))
    guests_dir = os.path.join(base_dir, "guests")
    os.makedirs(guests_dir, exist_ok=True)
    clean_id = "".join(c for c in guest_id if c.isalnum() or c in ("-", "_"))[:32]
    if not clean_id:
        raise ValueError("Invalid guest identifier")
    return os.path.join(guests_dir, f"guest_{clean_id}.db")


def ensure_guest_db(guest_id: str, master_db_path: str) -> str:
    path = guest_path(guest_id, master_db_path)
    if not os.path.exists(path):
        init_db(path)
        today = datetime.now(timezone.utc).date().isoformat()
        with closing(sqlite3.connect(path)) as conn:
            with conn:
                conn.executemany("""INSERT INTO jobs
                (dedup_hash,title,company,location,platform,tier,job_url,salary,description,
                 role_category,experience_level,date_posted,status,notes,sources)
                VALUES (?,?,?,?, 'Demo Board',1,'','','Sample opportunity. No live application link.',
                        ?,'Junior / Entry',?,'new','','[]')""",
                    [(f"demo-{i}", title, company, location, category, today)
                     for i, (title, company, location, category) in enumerate(SAMPLES, 1)])
                conn.execute("INSERT INTO user_settings(key,value) VALUES ('target_stack','Kotlin, React, JavaScript')")
    return path


def reset_guest_db(guest_id: str, master_db_path: str) -> str:
    path = guest_path(guest_id, master_db_path)
    if os.path.exists(path):
        os.remove(path)
    return ensure_guest_db(guest_id, master_db_path)
