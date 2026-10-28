"""Read-only provider benchmark; writes jobs only to a disposable local database."""
import argparse
from collections import Counter
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=7200)
    parser.add_argument("--platforms", default="")
    parser.add_argument("--output", default="scratch/discovery-benchmark.json")
    args = parser.parse_args()
    for key in ("VERCEL", "RENDER", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "FLCONSOLE_MCP_TOKEN"):
        os.environ.pop(key, None)
    from src.aggregator import Aggregator, get_default_connectors
    from src.connectors.base import BaseConnector
    from src.database import init_db, insert_jobs, get_jobs, set_user_setting
    source = (ROOT / "src/static/app.js").read_text(encoding="utf-8")
    categories = source.split("const PRESET_CATEGORIES = [", 1)[1].split("const PRESET_SKILLS", 1)[0]
    queries = list(dict.fromkeys(term for block in re.findall(r"skills:\s*\[(.*?)\]", categories, re.S)
                                for term in json.loads("[" + block + "]")))
    connectors = get_default_connectors()
    if args.platforms:
        connectors = [c for c in connectors if c.platform in args.platforms.split(",")]
    counts = Counter()
    lock = threading.Lock()
    first_saved = None
    started = time.monotonic()
    original_request = BaseConnector.request_with_fallback

    def request(connector, send):
        def counted(proxy):
            with lock:
                counts[connector.platform] += 1
            return send(proxy)
        return original_request(connector, counted)

    def save(*a, **kw):
        nonlocal first_saved
        result = insert_jobs(*a, **kw)
        if result[0] and first_saved is None:
            first_saved = round(time.monotonic() - started, 2)
        return result

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="discovery-benchmark-") as tmp:
        db = str(Path(tmp) / "jobs.db")
        init_db(db)
        set_user_setting(db, "proxy_mode", "disabled")
        aggregator = Aggregator(db, connectors)
        with patch.object(BaseConnector, "request_with_fallback", request), patch("src.sync_batches.insert_jobs", save):
            while True:
                remaining = args.seconds - (time.monotonic() - started)
                if remaining <= 0:
                    break
                result = aggregator.run_sync(queries, budget_seconds=min(30, remaining), cycle_id="benchmark")
                jobs = get_jobs(db, limit=100000)
                report = {"matrix_terms": len(queries), "elapsed_seconds": round(time.monotonic() - started, 2),
                          "first_saved_seconds": first_saved, "saved_unique_jobs": len(jobs),
                          "jobs_by_platform": dict(Counter(j["platform"] for j in jobs)),
                          "transport_attempts": dict(counts), "progress": result.get("progress"),
                          "status": result["status"], "scope": "all UI preset terms; disposable SQLite, no production writes or uploads",
                          "count_note": "transport attempts exclude JobSpy internal HTTP pages; saved jobs pass existing date/role/location filters, not proof of individual suitability"}
                output.write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(json.dumps({k: report[k] for k in ("elapsed_seconds", "first_saved_seconds", "saved_unique_jobs", "status")}), flush=True)
                if not result.get("progress", {}).get("has_more") or result["status"] == "error":
                    break
                if not result["progress"].get("can_continue"):
                    break
    print(str(output), flush=True)


if __name__ == "__main__":
    main()
