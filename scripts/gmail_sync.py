"""Cloud Gmail scan; IMAP PEEK never changes the original mailbox read flags."""
import argparse
import email
from email import policy
from email.utils import parseaddr
import imaplib
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import gmail_hub as hub
from src.database import get_db_connection, get_user_setting, set_user_setting, acquire_sync_lease, release_sync_lease


def window_start(window, now):
    local = datetime.fromtimestamp(now, ZoneInfo("Asia/Manila"))
    if window == "today":
        return local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return now - {"24h": 1, "7d": 7, "30d": 30}[window] * 86400


def parse_message(raw, metadata, account=hub.ACCOUNT):
    msg = email.message_from_bytes(raw, policy=policy.default)
    mid = re.search(rb"X-GM-MSGID (\d+)", metadata)
    tid = re.search(rb"X-GM-THRID (\d+)", metadata)
    received = imaplib.Internaldate2tuple(metadata)
    if not mid or not tid or not received:
        raise RuntimeError("Gmail did not return stable message identity/date")
    sender = str(msg.get("From", ""))
    # Keep archived/inbox mail; exclude Sent mail and the app's own digest.
    if parseaddr(sender)[1].lower() == account.lower() or re.search(rb"X-GM-LABELS \([^)]*\\Sent", metadata):
        return None
    part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if part:
        try:
            body = part.get_content()
        except (LookupError, UnicodeError):
            body = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
        if part.get_content_type() == "text/html":
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(body, "html.parser")
            for tag in soup(["script", "style", "head", "img"]):
                tag.decompose()
            for anchor in soup.find_all("a", href=True):
                href = anchor["href"]
                if href.startswith(("https://", "http://")):
                    anchor.append(" (" + href + ")")
            body = soup.get_text("\n", strip=True)
    # Only Gmail's own first authentication result can establish sender authentication.
    auth = str(msg.get("Authentication-Results", ""))
    domain = parseaddr(sender)[1].rpartition("@")[2].lower()
    authenticated = (auth.lstrip().startswith("mx.google.com;") and bool(re.search(r"\bdmarc=pass\b", auth))
                     and bool(domain) and bool(re.search(r"header\.from=" + re.escape(domain) + r"(?:[;\s]|$)", auth, re.I)))
    truncated = len(body) > 100000
    if truncated:
        body = body[:100000] + "\n[Long message truncated; open original Gmail message.]"
    if not body:
        body = "[No readable text body; open original Gmail message.]"
        authenticated = False
    return {"id": format(int(mid[1]), "x"), "thread_id": format(int(tid[1]), "x"),
            "subject": str(msg.get("Subject", "(No subject)")), "sender": sender,
            "body_text": body, "received_at": time.mktime(received),
            "is_read": bool(re.search(rb"FLAGS \([^)]*\\Seen", metadata)),
            "trusted": authenticated and not truncated}


def all_mailbox(client):
    status, folders = client.list()
    if status != "OK":
        raise RuntimeError("Could not list Gmail folders")
    for line in folders or []:
        if line and re.search(rb"\\All(?:\s|\))", line, re.I):
            match = re.match(rb'\([^)]*\)\s+(?:"[^"]*"|NIL)\s+(.+)$', line)
            if match:
                return match[1].decode("ascii")
    raise RuntimeError("Gmail All Mail folder is unavailable; enable IMAP folder access")


def scan(db_path, window="24h", client_factory=imaplib.IMAP4_SSL, now=None):
    now = time.time() if now is None else now
    start = window_start(window, now)
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not password:
        raise RuntimeError("GMAIL_APP_PASSWORD is not configured")
    hub.init_hub(db_path)
    conn = get_db_connection(db_path)
    conn.row_factory = __import__("sqlite3").Row
    try:
        existing = {row[0] for row in conn.execute("SELECT id FROM gmail_messages WHERE received_at>=?", (start - 86400,)).fetchall()}
        jobs = [dict(r) for r in conn.execute("SELECT * FROM jobs WHERE status IN ('applied','saved','in_progress')").fetchall()]
    finally:
        conn.close()
    client = client_factory("imap.gmail.com", timeout=40)
    inserted, checked = 0, 0
    deadline = time.monotonic() + 900
    try:
        client.login(hub.ACCOUNT, password)
        status, _ = client.select(all_mailbox(client), readonly=True)
        if status != "OK":
            raise RuntimeError("Cannot open Gmail All Mail")
        # IMAP calendar-day search is a superset; INTERNALDATE supplies exact rolling bounds below.
        since = datetime.fromtimestamp(start - 86400, timezone.utc).strftime("%d-%b-%Y")
        status, data = client.uid("search", None, "SINCE", since)
        if status != "OK":
            raise RuntimeError("Gmail search failed")
        uids = (data[0] or b"").split()
        for offset in range(0, len(uids), 100):
            if time.monotonic() > deadline:
                raise RuntimeError("Scan time budget reached; retry the same window to continue")
            status, metadata_rows = client.uid("fetch", b",".join(uids[offset:offset+100]),
                "(UID X-GM-MSGID X-GM-THRID X-GM-LABELS INTERNALDATE FLAGS RFC822.SIZE)")
            if status != "OK":
                raise RuntimeError("Gmail metadata fetch failed")
            for metadata in metadata_rows or []:
                if not isinstance(metadata, bytes):
                    continue
                mid = re.search(rb"X-GM-MSGID (\d+)", metadata)
                uid = re.search(rb"UID (\d+)", metadata)
                received = imaplib.Internaldate2tuple(metadata)
                if not mid or not uid or not received:
                    raise RuntimeError("Incomplete Gmail metadata")
                stamp = time.mktime(received)
                if not start <= stamp <= now or format(int(mid[1]), "x") in existing:
                    continue
                if time.monotonic() > deadline:
                    raise RuntimeError("Scan time budget reached; retry the same window to continue")
                size = re.search(rb"RFC822.SIZE (\d+)", metadata)
                large = size and int(size[1]) > 2_000_000
                spec = "(BODY.PEEK[HEADER])" if large else "(BODY.PEEK[])"
                status, contents = client.uid("fetch", uid[1], spec)
                if status != "OK":
                    raise RuntimeError("Gmail message fetch failed")
                raw = next((item[1] for item in contents if isinstance(item, tuple)), None)
                if raw is None:
                    raise RuntimeError("Gmail returned no message body")
                message = parse_message(raw, metadata)
                checked += 1
                if message:
                    if large:
                        message.update(body_text="[Message exceeds 2 MB. Read the original in Gmail.]", trusted=False)
                    inserted += int(hub.ingest(db_path, message, jobs))
        updated = hub.apply_pending(db_path)
        return {"checked": checked, "imported": inserted, "pipeline_updated": updated,
                "window_start": start, "window_end": now}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def run_request(db_path, request_id):
    from src.daily_schedule import day, send_digest
    request = {}
    key = hub.SCAN_KEY
    for candidate in (hub.SCAN_KEY, hub.DAILY_KEY):
        value = json.loads(get_user_setting(db_path, candidate, "{}") or "{}")
        if value.get("id") == request_id:
            request, key = value, candidate
            break
    if request.get("id") != request_id or request.get("status") != "queued":
        return {"status": "stale_request"}
    lease = f"{int(time.time()) + 1200}|{request_id}"
    if not acquire_sync_lease(db_path, lease, int(time.time()), key="gmail_scan_worker"):
        raise RuntimeError("Another Gmail scan is still running")
    try:
        request.update(status="running")
        set_user_setting(db_path, key, json.dumps(request))
        try:
            result = scan(db_path, request["window"])
            request.update(status="complete", completed_at=time.time(), result=result)
            set_user_setting(db_path, key, json.dumps(request))
        except Exception as error:
            request.update(status="error", completed_at=time.time(), error="Gmail scan failed; retry. See cloud run for the failure type.")
            set_user_setting(db_path, key, json.dumps(request))
            print("Gmail scan failed:", type(error).__name__, flush=True)
            # Digest still goes out with an explicit failed-scan banner.
            result = {"scan_failed": True}
        if request.get("digest"):
            from scripts.daily_notifier import send_daily_email
            digest = send_digest(db_path, lambda db: send_daily_email(db, "https://job-accelerator.vercel.app"))
            if not digest.get("success"):
                raise RuntimeError("Daily digest delivery failed")
        if result.get("scan_failed"):
            raise RuntimeError("Gmail scan failed; no successful sync claimed")
        return result
    finally:
        release_sync_lease(db_path, lease, key="gmail_scan_worker")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args()
    print(json.dumps(run_request("data/jobs.db", args.request_id)))
