"""Start the database worker explicitly; the existing scheduled task is unchanged."""
import argparse
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--executor", choices=["local", "cloud"], required=True)
    parser.add_argument("--command-id")
    args = parser.parse_args()
    if not all(os.environ.get(key) and not any(marker in os.environ[key].upper() for marker in ("SENSITIVE", "REDACTED"))
               for key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")):
        parser.error("Valid Turso credentials are required; refusing a local database fallback")
    if args.executor == "cloud" and not args.command_id:
        parser.error("Cloud execution requires an explicit command ID")
    from src.aggregator import Aggregator
    from src.inbox_worker import run_cloud, run_local
    db = "data/shared-worker.db"
    aggregator = Aggregator(db)
    if args.executor == "cloud":
        run_cloud(db, args.command_id, aggregator)
    else:
        from scripts.local_worker import worker_lock, LOCAL_DATA
        LOCAL_DATA.mkdir(parents=True, exist_ok=True)
        with worker_lock():
            run_local(db, aggregator)


if __name__ == "__main__":
    main()
