import os
import sys
import shutil

# Ensure project root is available in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from src.server import create_app
from src.database import init_db

# Writable directory configuration:
# Vercel Serverless environment provides /tmp for writable operations
if os.environ.get("VERCEL"):
    db_dir = "/tmp/data"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "jobs.db")
    local_db = os.path.join(root_dir, "data", "jobs.db")
    if os.path.exists(local_db) and not os.path.exists(db_path):
        try:
            shutil.copy2(local_db, db_path)
        except Exception:
            init_db(db_path)
    else:
        init_db(db_path)
else:
    db_path = os.path.join(root_dir, "data", "jobs.db")
    init_db(db_path)

app = create_app(db_path)
