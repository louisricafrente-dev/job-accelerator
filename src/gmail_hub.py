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

NOISE_SENDERS = (
    "jobalerts-noreply@linkedin.com", "jobs-listings@linkedin.com", "jobs-noreply@linkedin.com",
    "editors-noreply@linkedin.com", "messages-noreply@linkedin.com", "invitations@linkedin.com",
    "updates-noreply@linkedin.com", "security-noreply@linkedin.com", "linkedin@e.linkedin.com",
    "connections@linkedin.com", "Groups-noreply@linkedin.com",
    "noreply@glassdoor.com", "jobs@glassdoor.com",
    "alert@indeed.com", "donotreply@jobalert.indeed.com",
    "Jobstreet Alerts", "Jobstreet Driver Alerts", "Jobstreet Notifications", "Jobstreet Reminders", "siva@jobstreet.com",
    "no-reply@ashbyhq.com", "notifications@github.com", "noreply@github.com",
    "registration@vercel.com", "no-reply@accounts.google.com", "google-Workspace-alerts-noreply@google.com",
    "no-reply@spotify.com", "info@mailer.netflix.com", "noreply@redditmail.com", "notify@x.com",
    "notification@facebookmail.com", "no-reply@canva.com", "engage@canva.com",
    "team@hi.Wellfound.com", "daily@daily.dev", "hello@daily.dev", "digest@medium.com",
    "noreply@medium.com", "no-reply@substack.com", "no-reply@duolingo.com",
    "no-reply@udemy.com", "no-reply@coursera.org", "noreply@kaggle.com",
    "noreply@youtube.com", "no-reply@ twitch.tv", "no-reply@discord.com",
    "no-reply@grammarly.com", "info@ grammarly.com", "hello@ollama.com",
    "team@supabase.com", "noreply@render.com", "no-reply@railway.app",
    "Job Accelerator <michael18ricafrente@gmail.com>",
)


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


def classify(subject, body, sender=""):
    sender_low = (sender or "").lower()
    if any(ns.lower() in sender_low for ns in NOISE_SENDERS):
        return "OTHER", None, False

    subj_low = re.sub(r"\s+", " ", (subject or "").lower()).strip()
    fresh_low = re.sub(r"\s+", " ", fresh_text(body or "").lower()).strip()
    text = subj_low + "\n" + fresh_low

    if re.search(
        r"(?:job alert|recommended jobs|jobs for you|new jobs? matching|daily job digest|"
        r"jobs similar to|new jobs similar to|is hiring for|hiring:|apply now to|"
        r"still accepting applications - don['\u2019]t forget to submit yours|"
        r"don['\u2019]t forget to complete your application to|"
        r"wish you luck on your interview.*helpful tips|"
        r"has viewed your application|your application was viewed by|"
        r"your application was sent to|job with .* has closed|was closed$|"
        r"new activity in jobs you applied for|save your searches for matching jobs|"
        r"your profile is being discovered|your profile is almost there)",
        subj_low,
    ):
        return "OTHER", None, False

    rej_pattern = (
        r"not (?:be )?moving forward|decided to move forward with (?:other|another) candidate|"
        r"regret to inform|unsuccessful|position has been filled|"
        r"decided (?:not to proceed|to pursue other)|unlikely to progress further|"
        r"application (?:for .* )?was not selected|has not accepted your application|"
        r"did not align with our (?:certification )?criteria"
    )
    if re.search(rej_pattern, text):
        return "REJECTED", "rejected", False

    if re.search(r"(?:cancel(?:led|ed)|not (?:a |an )?(?:job )?(?:offer|interview)|not yet)", text):
        return "OTHER", None, False

    req_pattern = (
        r"candidate nda|nda acceptance|"
        r"complete (?:your|the|this) (?:application|job application|kooapps application|form|screening form|pre-application form|ai interview)|"
        r"finish your (?:incomplete |job )?application|(?:job )?application is incomplete|"
        r"instructions for completing your form|return to the form you recently saved|"
        r"additional information needed for your application|verify your credentials|"
        r"candidate home account pending action|submit (?:the following|your) documents|pre.employment|"
        r"to complete your application and move forward in the process, please apply directly|"
        r"log in to view and respond to the message|received a message or interview invite from .* respond now"
    )

    if re.search(
        r"(?:thanks? for (?:your application|applying)|thank you for (?:your application|applying)|"
        r"confirming your .* job application|your application was successfully submitted|"
        r"application (?:has been )?received|we (?:have )?received your .*application|"
        r"job application successful|^indeed application:)",
        subj_low,
    ):
        if not re.search(req_pattern, text):
            return "RECEIVED", "applied", False

    rules = [
        ("OFFER", "offer", r"(?:formal|job) offer|offer letter|pleased to offer you"),
        ("INTERVIEW", "final_interview", r"final (?:round|interview)|executive interview|client interview"),
        ("ASSESSMENT", "tech_exam", r"technical (?:assessment|exam)|coding (?:challenge|assessment)|hackerrank|codility|take.home test|online exam|complete your ai interview"),
        ("INTERVIEW", "hr_screening", r"initial interview|hr screening|invitation to interview|invited you (?:to|for) an? (?:[\w-]+\s+)?interview|interview invitation|schedule (?:an|your) (?:interview|call)|book (?:an|your) interview|claim your .* interview spot|appointment booked|your (?:new )?interview (?:time|for|is (?:at|tomorrow|happening|today))|decided to move forward with your application"),
        ("REQUIREMENT", "", req_pattern),
        ("RECEIVED", "applied", r"application (?:received|submitted)|thank you for applying|received your (?:online )?application|successfully submitted"),
    ]
    hits = [(category, stage) for category, stage, pattern in rules if re.search(pattern, text)]
    if not hits:
        return "OTHER", None, False
    category, stage = hits[0]
    # A rejection wins over quoted interview terminology. Other conflicting milestones need review.
    if category != "REJECTED" and len({c for c, s in hits if s and s != "applied"}) > 1:
        return "REQUIREMENT", None, True
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
    if len(candidates) > 1:
        # When one title at the same company is a more specific superstring of another, keep the specific role.
        pairs = [(normalized(j.get("company")), normalized(j.get("title"))) for j in candidates]
        candidates = [
            j for j, (c1, t1) in zip(candidates, pairs)
            if not any(c1 == c2 and t1 != t2 and t1 in t2 for c2, t2 in pairs)
        ]
        # If remaining candidates are duplicate rows of the exact same company + title, pick the active applied row.
        if len({(normalized(j.get("company")), normalized(j.get("title"))) for j in candidates}) == 1:
            candidates.sort(key=lambda j: (j.get("status") == "applied", j.get("id") or 0), reverse=True)
            candidates = [candidates[0]]
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
        category, stage, action = classify(message["subject"], message["body_text"], message.get("sender", ""))
        result = "Needs review"
        if job and not message.get("trusted"):
            result = "Sender authentication not verified; Pipeline unchanged"
        elif job and job.get("status") != "applied":
            result = "Not an applied job; Pipeline unchanged"
        elif job and not stage:
            result = "No unambiguous milestone; Pipeline unchanged"
        elif job:
            result = "Pending update"
        stored_body = message["body_text"] if action else ""
        conn.execute("""INSERT INTO gmail_messages
            (id,thread_id,subject,sender,received_at,body_text,category,action_required,is_read,
             job_id,match_reason,pipeline_result,target_stage,trusted)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (message["id"], message["thread_id"], message["subject"], message["sender"], message["received_at"],
             stored_body, category, int(action), int(message.get("is_read", False)),
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
                job_ts = max(timestamp(job.get("applied_at")), timestamp(job.get("updated_at")))
                boundary = last if (job_ts - m["received_at"] > 90 * 86400) else max(last, job_ts)
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
        stats = dict(conn.execute("""SELECT
            COALESCE(SUM(action_required=1),0) total,
            COALESCE(SUM(action_required=1 AND is_read=0),0) unread,
            COALESCE(SUM(action_required=1),0) action_required,
            COALESCE(SUM(action_required=1 AND category='REQUIREMENT'),0) requirements,
            COALESCE(SUM(action_required=1 AND category IN ('INTERVIEW','ASSESSMENT','OFFER')),0) interviews,
            COALESCE(SUM(stage_applied=1),0) updated,
            COALESCE(SUM(action_required=1 AND stage_applied=0),0) review
            FROM gmail_messages""").fetchone())
        if summary:
            return {"stats": stats}
        clauses, args = ["action_required=1"], []
        if category and category != "action_required":
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
        where = " WHERE " + " AND ".join(clauses)
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
