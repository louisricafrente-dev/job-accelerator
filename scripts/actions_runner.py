"""Run the existing scraper without Vercel; sandbox never touches shared data."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox", action="store_true")
    args = parser.parse_args()
    if not args.sandbox:
        parser.error("Shared-database execution is not enabled in this validation runner")
    # A cloud smoke test must never inherit credentials for the live database.
    os.environ.pop("TURSO_DATABASE_URL", None)
    os.environ.pop("TURSO_AUTH_TOKEN", None)
    os.environ.pop("VERCEL", None)
    from src.database import init_db
    from src.aggregator import Aggregator
    from src.connectors.remote_feed import RemoteOKConnector
    with tempfile.TemporaryDirectory() as directory:
        db = str(Path(directory) / "sandbox_test.db")
        init_db(db)
        connector = RemoteOKConnector()
        result = Aggregator(db, connectors=[connector]).run_sync(
            queries=["developer"], budget_seconds=20, cycle_id=uuid.uuid4().hex)
        print(json.dumps({"sandbox": True, "result": result}, default=str))
        if result.get("status") in {"error", "already_syncing"} or connector.last_error:
            raise SystemExit("Cloud source fetch failed; inspect source telemetry")


if __name__ == "__main__":
    main()
