"""Exercise a uniquely namespaced inbox on existing Turso, never live jobs."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    args = parser.parse_args()
    if args.env_file:
        for line in Path(args.env_file).read_text().splitlines():
            name, separator, raw = line.partition("=")
            if separator and name in {"TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"}:
                value = raw.strip().strip('"').strip("'")
                if not value or any(word in value.upper() for word in ("SENSITIVE", "REDACTED")):
                    parser.error("Valid Turso credentials must be configured securely; placeholders detected")
                os.environ[name] = value
    if not all(os.environ.get(name) for name in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")):
        parser.error("Turso URL and token are required")
    from src.database import get_db_connection, execution_condition
    from src.execution_inbox import enqueue, claim, read, update_owned
    key = "integration:execution-inbox:" + uuid.uuid4().hex
    probe_key = key + ":fence-probe"
    clock = time.time()
    db = "integration-inbox.db"
    try:
        enqueue(db, ["integration-only-no-scrape"], key=key, now=clock)
        assert claim(db, "cloud", "integration-gh", key=key, now=clock + 89) is None
        local = claim(db, "local", "integration-pc", key=key, now=clock + 60)
        assert local and update_owned(db, local, key=key, now=clock + 70)
        guard = {**local, "key": key}
        predicate, params = execution_condition(guard)
        conn = get_db_connection(db)
        try:
            conn.execute("INSERT INTO user_settings(key,value) VALUES (?,?)", (probe_key, "initial"))
            cursor = conn.execute("UPDATE user_settings SET value='owned' WHERE key=? AND " + predicate, [probe_key, *params])
            if cursor.rowcount != 1:
                raise RuntimeError("Valid owner was rejected by database fence")
            conn.commit()
        finally:
            conn.close()
        cloud = claim(db, "cloud", "integration-gh", key=key, now=clock + 251)
        assert cloud
        assert not update_owned(db, local, {"status": "ok"}, key=key, now=clock + 252)
        assert update_owned(db, cloud, {"status": "ok"}, key=key, now=clock + 252)
        assert read(db, key=key)["status"] == "complete"
        conn = get_db_connection(db)
        try:
            cursor = conn.execute("UPDATE user_settings SET value='stale' WHERE key=? AND " + predicate, [probe_key, *params])
            if cursor.rowcount != 0:
                raise RuntimeError("Stale owner passed the database write fence")
            conn.commit()
        finally:
            conn.close()
    finally:
        conn = get_db_connection(db)
        try:
            conn.execute("DELETE FROM user_settings WHERE key IN (?,?)", (key, probe_key))
            conn.commit()
            remaining = conn.execute("SELECT COUNT(*) FROM user_settings WHERE key IN (?,?)", (key, probe_key)).fetchone()[0]
            if remaining:
                raise RuntimeError("Integration records were not cleaned up")
        finally:
            conn.close()
    print(json.dumps({"integration": "passed", "jobs_modified": False, "test_records_remaining": 0}))


if __name__ == "__main__":
    main()
