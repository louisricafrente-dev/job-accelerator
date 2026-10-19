import os
import sys

# Ensure project root in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from scripts.consolidate_duplicates import consolidate_database

def purge_same_timeline_duplicates(db_path: str = "data/jobs.db") -> int:
    consolidate_database(db_path)
    return 0

if __name__ == "__main__":
    db_file = sys.argv[1] if len(sys.argv) > 1 else "data/jobs.db"
    purge_same_timeline_duplicates(db_file)
