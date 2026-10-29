"""Persistent Gmail inbox and conservative, event-ordered application updates."""
import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from src.database import get_db_connection, get_user_setting, set_user_setting, acquire_sync_lease, release_sync_lease

ACCOUNT = "michael18ricafrente@gmail.com"
SCAN_KEY = "gmail_scan_v1"
DAILY_KEY = "gmail_daily_scan_v1"
WINDOWS = {"today", "24h", "7d", "30d"}
SCHEMA = """CREATE TABLE IF NOT EXISTS gmail_messages (
 id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, subject TEXT NOT NULL, sender TEXT NOT NULL,
 received_at REAL NOT NULL, body_text TEXT NOT NULL, category TEXT NOT NULL,
 action_required INTEGER NOT NULL, is_read INTEGER NOT NULL DEFAULT 0,
 job_id INTEGER, match_reason TEXT NOT NULL, pipeline_result TEXT NOT NULL,
 target_stage TEXT, stage_applied INTEGER NOT NULL DEFAULT 0, trusted INTEGER NOT NULL DEFAULT 0);
 CREATE INDEX IF NOT EXISTS idx_gmail_received ON gmail_messages(received_at DESC, id);
 CREATE INDEX IF NOT EXISTS idx_gmail_job_event ON gmail_messages(job_id,stage_applied,received_at);
"""


def init_hub(db_path):
    conn = get_db_connection(db_path)
    try:
        # Execute explicitly: the Turso executescript adapter intentionally swallows errors.
        for sql in SCHEMA.split(";"):
            if sql.strip():
                conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def normalized(value):
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def fresh_text(body):
    # Quoted history is retained in the viewer but never drives a new stage change.
    return re.split(r"(?im)^\s*(?:On .+wrote:|From:|[-_]{3,}\s*(?:Original Message|Forwarded message))", body)[0]


def classify(subject, body):
    text = (subject + "\n" + fresh_text(body)).lower()
    if re.search(r"(?:cancel(?:led|ed)|reschedul|not (?:a |an )?(?:offer|interview)|not yet|job alert|recommended jobs)", text):
        return "OTHER", None, True
    rules = [
        ("REJECTED", "rejected", r"not (?:be )?moving forward|regret to inform|unsuccessful|position has been filled|decided (?:not to proceed|to pursue other)"),
        ("OFFER", "offer", r"(?:formal|job) offer|offer letter|pleased to offer you"),
        ("INTERVIEW", "final_interview", r"final (?:round|interview)|executive interview|client interview"),
        ("ASSESSMENT", "tech_exam", r"technical (?:assessment|exam)|coding (?:challenge|assessment)|hackerrank|codility|take.home test"),
        ("INTERVIEW", "hr_screening", r"initial interview|hr screening|invitation to interview|schedule (?:an interview|a call)|appointment booked"),
        ("REQUIREMENT", "", r"candidate nda|complete (?:your|the) (?:application|form)|submit (?:the following|your) documents|pre.employment"),
        ("RECEIVED", "applied", r"application (?:received|submitted)|thank you for applying|received your application|successfully submitted"),
    ]
    hits = [(category, stage) for category, stage, pattern in rules if re.search(pattern, text)]
    if not hits:
        return "OTHER", None, False
    category, stage = hits[0]
    # A rejection wins over quoted interview terminology. Other conflicting milestones need review.
    if category != "REJECTED" and len({s for _, s in hits if s and s != "applied"}) > 1:
        return "OTHER", None, True
    return category, stage or None, category in {"OFFER", "INTERVIEW", "ASSESSMENT", "REQUIREMENT"}


def match_job(message, jobs):
    text = normalized(message["subject"] + " " + fresh_text(message["body_text"]))
    links = set(re.findall(r"https?://[^\s<>\"']+", fresh_text(message["body_text"])))
    candidates = []
    for job in jobs:
        # Only explicit role + company or exact listing URL is strong enough; no fuzzy first match.
        company, title = normalized(job.get("company")), normalized(job.get("title"))
        names = (len(company) >= 4 and len(title) >= 6 and
                 " " + company + " " in " " + text + " " and
                 " " + title + " " in " " + text + " ")
        urls = [job.get("job_url", "")]
        sources = job.get("sources") or []
        if isinstance(sources, str):
            try:
                sources = json.loads(sources)
            except ValueError:
                sources = []
        urls.extend(s.get("url", "") for s in sources if isinstance(s, dict))
        exact_link = any(u and u in links for u in urls)
        if names or exact_link:
            candidates.append(job)
    if len(candidates) != 1:
        return None, "Multiple possible jobs; Pipeline unchanged" if candidates else "No exact application match; Pipeline unchanged"
    return candidates[0], "Exact listing URL or company and role"


def ingest(db_path, message, jobs):
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if conn.execute("SELECT id FROM gmail_messages WHERE id=?", (message["id"],)).fetchone():
            return False
        job, reason = match_job(message, jobs)
        category, stage, action = classify(message["subject"], message["body_text"])
        result = "Needs review"
        if job and not message.get("trusted"):
            result = "Sender authentication not verified; Pipeline unchanged"
        elif job and job.get("status") != "applied":
            result = "Not an applied job; Pipeline unchanged"
        elif job and not stage:
            result = "No unambiguous milestone; Pipeline unchanged"
        elif job:
            result = "Pending update"
        conn.execute("""INSERT INTO gmail_messages
            (id,thread_id,subject,sender,received_at,body_text,category,action_required,is_read,
             job_id,match_reason,pipeline_result,target_stage,trusted)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (message["id"], message["thread_id"], message["subject"], message["sender"], message["received_at"],
             message["body_text"], category, int(action), int(message.get("is_read", False)),
             job["id"] if job else None, reason, result, stage, int(message.get("trusted", False))))
        conn.commit()
        return True
    finally:
        conn.close()


def apply_pending(db_path):
    """Single-statement CAS updates: preserve manual edits and never regress a milestone."""
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    ranks = {"applied": 0, "screening": 1, "hr_screening": 1, "technical": 2,
             "tech_exam": 2, "interview": 3, "final_interview": 3, "offer": 4}
    updated = 0
    try:
        pending = conn.execute("SELECT * FROM gmail_messages WHERE pipeline_result='Pending update' ORDER BY received_at DESC,id DESC").fetchall()
        for row in pending:
            m = dict(row)
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (m["job_id"],)).fetchone()
            reason = "Job changed; Pipeline unchanged"
            if job and job["status"] == "applied":
                job = dict(job)
                old = job.get("pipeline_stage") or "applied"
                stage = m["target_stage"]
                last = conn.execute("SELECT MAX(received_at) FROM gmail_messages WHERE job_id=? AND stage_applied=1", (job["id"],)).fetchone()[0] or 0
                def timestamp(value):
                    if not value:
                        return 0
                    try:
                        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()
                    except ValueError:
                        return float("inf")
                boundary = max(last, timestamp(job.get("applied_at")), timestamp(job.get("updated_at")))
                if m["received_at"] <= boundary:
                    reason = "Older than latest job change; Pipeline unchanged"
                elif old in {"rejected", "withdrawn", "offer"} or stage == old or (stage != "rejected" and ranks.get(stage, -1) <= ranks.get(old, 99)):
                    reason = "Existing stage preserved"
                else:
                    note = "[Gmail " + m["id"] + "] " + m["subject"] + "\nhttps://mail.google.com/mail/u/" + ACCOUNT + "/#all/" + m["id"]
                    cursor = conn.execute("""UPDATE jobs SET pipeline_stage=?,notes=?,updated_at=CURRENT_TIMESTAMP
                        WHERE id=? AND status='applied' AND COALESCE(pipeline_stage,'applied')=?
                        AND COALESCE(notes,'')=? AND COALESCE(updated_at,'')=?
                        AND NOT EXISTS (SELECT 1 FROM gmail_messages WHERE job_id=? AND stage_applied=1 AND received_at>=?)""",
                        (stage, ((job.get("notes") or "") + "\n" + note).strip(), job["id"], old,
                         job.get("notes") or "", job.get("updated_at") or "", job["id"], m["received_at"]))
                    if cursor.rowcount == 1:
                        reason = "Updated Pipeline to " + stage
                        updated += 1
            conn.execute("UPDATE gmail_messages SET pipeline_result=?,stage_applied=? WHERE id=?",
                         (reason, int(reason.startswith("Updated Pipeline")), m["id"]))
            conn.commit()
        return updated
    finally:
        conn.close()


def messages(db_path, limit=40, offset=0, category="", read="", match="", search="", summary=False):
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        stats = dict(conn.execute("""SELECT COUNT(*) total,COALESCE(SUM(is_read=0),0) unread,
            COALESCE(SUM(action_required),0) action_required,COALESCE(SUM(category='INTERVIEW'),0) interviews,
            COALESCE(SUM(stage_applied=1),0) updated,COALESCE(SUM(stage_applied=0),0) review
            FROM gmail_messages""").fetchone())
        if summary:
            return {"stats": stats}
        clauses, args = [], []
        if category:
            if category == "action_required":
                clauses.append("action_required=1")
            else:
                clauses.append("category=?")
                args.append(category)
        if read in {"read", "unread"}:
            clauses.append("is_read=?")
            args.append(int(read == "read"))
        if match in {"updated", "review"}:
            clauses.append("stage_applied=?")
            args.append(int(match == "updated"))
        if search:
            clauses.append("(subject LIKE ? ESCAPE '\\' OR sender LIKE ? ESCAPE '\\')")
            term = "%" + search[:150].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            args.extend([term, term])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = conn.execute("SELECT COUNT(*) FROM gmail_messages" + where, args).fetchone()[0]
        rows = conn.execute("""SELECT id,thread_id,subject,sender,received_at,category,action_required,is_read,
            job_id,match_reason,pipeline_result,stage_applied,substr(body_text,1,220) snippet
            FROM gmail_messages""" + where + " ORDER BY received_at DESC,id DESC LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        return {"account": ACCOUNT, "messages": [dict(r) for r in rows], "stats": stats,
                "total": total, "has_more": offset + len(rows) < total, "scan": scan_status(db_path)}
    finally:
        conn.close()


def detail(db_path, message_id):
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM gmail_messages WHERE id=?", (message_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def mark_read(db_path, message_id, value):
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("UPDATE gmail_messages SET is_read=? WHERE id=? AND is_read<>?", (int(value), message_id, int(value)))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def scan_status(db_path):
    scans = [json.loads(get_user_setting(db_path, key, "{}") or "{}") for key in (SCAN_KEY, DAILY_KEY)]
    return max(scans, key=lambda item: item.get("requested_at", 0))


def request_scan(db_path, window="24h", digest=False):
    if window not in WINDOWS:
        raise ValueError("Choose today, 24h, 7d or 30d")
    from src.daily_schedule import day
    if digest and get_user_setting(db_path, "daily_digest_day", "") == day():
        return {"success": True, "status": "already_sent"}
    key = DAILY_KEY if digest else SCAN_KEY
    lease = f"{int(time.time()) + 30}|{uuid.uuid4().hex}"
    if not acquire_sync_lease(db_path, lease, int(time.time()), key="gmail_dispatch"):
        return {"success": False, "status": "busy", "error": "A scan request is being queued; retry shortly."}
    try:
        current = json.loads(get_user_setting(db_path, key, "{}") or "{}")
        now = time.time()
        if current.get("status") in {"queued", "running"} and now - current.get("requested_at", 0) < 2700:
            return {"success": True, "status": "already_queued", "scan": current}
        if not digest and now - max(current.get("requested_at", 0), current.get("completed_at", 0)) < 300:
            return {"success": False, "status": "cooldown", "error": "Wait five minutes between mailbox scans."}
        request = {"id": uuid.uuid4().hex, "status": "queued", "window": "24h" if digest else window,
                   "digest": digest, "requested_at": now}
        from src.execution_dispatch import dispatch
        set_user_setting(db_path, key, json.dumps(request))
        try:
            dispatch(request["id"], workflow="gmail-digest.yml", inputs={"request_id": request["id"]})
        except Exception:
            request.update(status="error", error="Cloud dispatch failed; retry scan.")
            set_user_setting(db_path, key, json.dumps(request))
            raise
        return {"success": True, "status": "queued", "scan": request}
    finally:
        release_sync_lease(db_path, lease, key="gmail_dispatch")
