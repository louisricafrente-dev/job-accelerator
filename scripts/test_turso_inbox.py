"""Exercise a uniquely namespaced inbox on existing Turso, never live jobs."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    for line in Path(args.env_file).read_text().splitlines():
        name, separator, raw = line.partition("=")
        if separator and name in {"TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"}:
            value = raw.strip().strip('"').strip("'")
            if not value or any(word in value.upper() for word in ("SENSITIVE", "REDACTED")):
                parser.error("Valid Turso credentials must be configured securely; placeholders detected")
            os.environ[name] = value
    if not all(os.environ.get(name) for name in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")):
        parser.error("Turso URL and token are required")
    from src.database import get_db_connection
    from src.execution_inbox import enqueue, claim, read, update_owned
    key = "integration:execution-inbox:" + uuid.uuid4().hex
    db = "integration-inbox.db"
    try:
        enqueue(db, ["integration-only-no-scrape"], key=key, now=100)
        assert claim(db, "cloud", "integration-gh", key=key, now=189) is None
        local = claim(db, "local", "integration-pc", key=key, now=160)
        assert local and update_owned(db, local, key=key, now=170)
        cloud = claim(db, "cloud", "integration-gh", key=key, now=351)
        assert cloud
        assert not update_owned(db, local, {"status": "ok"}, key=key, now=352)
        assert update_owned(db, cloud, {"status": "ok"}, key=key, now=352)
        assert read(db, key=key)["status"] == "complete"
        print(json.dumps({"integration": "passed", "jobs_modified": False}))
    finally:
        conn = get_db_connection(db)
        try:
            conn.execute("DELETE FROM user_settings WHERE key=?", (key,))
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    main()
