"""
Automated Daily Email Digest Notifier
Compiles a local job digest and sends new-job notifications by email
to michael18ricafrente@gmail.com.
"""
import os
import sys
import smtplib
import datetime
from html import escape
import json
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is available in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Load local .env variables if present
env_file = os.path.join(root_dir, ".env")
if os.path.exists(env_file):
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

from src.database import get_jobs, get_stats, init_db, get_user_setting, get_db_connection

RECIPIENT_EMAIL = "michael18ricafrente@gmail.com"
SENDER_EMAIL = os.environ.get("SMTP_USER", "michael18ricafrente@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", os.environ.get("GMAIL_APP_PASSWORD", ""))
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

def generate_digest_data(db_path: str = "data/jobs.db"):
    init_db(db_path)
    stats = get_stats(db_path)
    
    # Fetch jobs from today or recent 24h
    today_str = datetime.date.today().isoformat()
    recent_jobs = get_jobs(db_path, date_filter="today", limit=100)
    if not recent_jobs:
        # Fallback to 7d or latest active new jobs if today filter is narrow
        recent_jobs = get_jobs(db_path, date_filter="7d", limit=60)
    if not recent_jobs:
        recent_jobs = get_jobs(db_path, status="new", limit=30)

    # Group by platform
    platform_counts = {}
    for j in recent_jobs:
        plat = j.get("platform", "Unknown")
        platform_counts[plat] = platform_counts.get(plat, 0) + 1

    # Filter top relevant matches for candidate stack (Android, Kotlin, Web, Full Stack, Junior)
    top_matches = []
    keywords = ["android", "kotlin", "junior", "entry", "react", "node", "full stack", "frontend", "mobile"]
    for j in recent_jobs:
        title_lower = (j.get("title") or "").lower()
        if any(k in title_lower for k in keywords):
            top_matches.append(j)
        if len(top_matches) >= 8:
            break

    if len(top_matches) < 5:
        top_matches = recent_jobs[:8]

    gmail = {"available": False}
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("SELECT COUNT(*),COALESCE(SUM(action_required),0),COALESCE(SUM(stage_applied),0) FROM gmail_messages WHERE received_at>=?", (time.time() - 86400,)).fetchone()
        scan = json.loads(get_user_setting(db_path, "gmail_daily_scan_v1", "{}") or "{}")
        gmail = {"available": True, "total": row[0], "action": row[1], "updated": row[2], "scan_status": scan.get("status", "not_run")}
    except Exception:
        pass
    finally:
        conn.close()
    return {
        "stats": stats,
        "recent_count": len(recent_jobs),
        "platform_counts": platform_counts,
        "top_matches": top_matches,
        "date_str": today_str,
        "gmail": gmail
    }

def build_html_content(data: dict, dashboard_url: str = "") -> str:
    stats = data["stats"]
    recent_count = data.get("new_jobs_count", data["recent_count"])
    count_label = "Added in This Sync" if "new_jobs_count" in data else "Recent Jobs"
    platform_counts = data["platform_counts"]
    top_matches = data["top_matches"]
    date_str = data["date_str"]

    dash_link = dashboard_url or "https://job-accelerator.vercel.app"
    gmail = data.get("gmail", {})
    gmail_section = ""
    if gmail.get("available"):
        state = "Mailbox scan completed" if gmail.get("scan_status") == "complete" else "Mailbox scan did not complete; messages may be out of date"
        gmail_section = f'''<section style="padding:20px 28px;border-bottom:1px solid #e2e8f0;color:#1e293b">
          <h2 style="font-size:18px">Gmail · last 24 hours</h2><p>{state}</p>
          <p>{int(gmail['total'])} messages · {int(gmail['action'])} may need action · {int(gmail['updated'])} Pipeline updates</p>
          <p>Uncertain matches leave the Pipeline unchanged. Review the full original messages in your Hub.</p>
          <a href="{escape(dash_link, quote=True)}?view=gmail">Open Gmail Hub</a></section>'''

    platform_rows = ""
    for plat, count in sorted(platform_counts.items(), key=lambda x: x[1], reverse=True):
        platform_rows += f"""
        <tr>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-weight: 500; color: #1e293b;">{plat}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; text-align: right; color: #0284c7; font-weight: 700;">+{count} jobs</td>
        </tr>
        """

    job_cards = ""
    for j in top_matches:
        title = j.get("title", "Developer Opportunity")
        company = j.get("company", "Direct Client")
        salary = j.get("salary") or "Competitive / Disclosed in post"
        url = j.get("job_url", "#")
        platform = j.get("platform", "Job Board")
        level = j.get("experience_level", "Junior / Entry")

        job_cards += f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                <span style="font-size: 11px; font-weight: 700; background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 12px; text-transform: uppercase;">{platform}</span>
                <span style="font-size: 11px; color: #64748b; font-weight: 600;">{level}</span>
            </div>
            <h3 style="margin: 0 0 4px 0; font-size: 15px; color: #0f172a;">
                <a href="{url}" target="_blank" style="color: #0284c7; text-decoration: none; font-weight: 600;">{title}</a>
            </h3>
            <p style="margin: 0 0 6px 0; font-size: 13px; color: #475569;">🏢 {company}</p>
            <div style="font-size: 12px; color: #16a34a; font-weight: 600;">💰 {salary}</div>
            <div style="margin-top: 8px;">
                <a href="{url}" target="_blank" style="display: inline-block; background: #0284c7; color: #ffffff; text-decoration: none; font-size: 12px; font-weight: 600; padding: 6px 12px; border-radius: 6px;">View &amp; Apply &rarr;</a>
            </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px;">
        <div style="max-width: 620px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
            <!-- Header Banner -->
            <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #ffffff; padding: 24px 28px;">
                <div style="font-size: 12px; font-weight: 700; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;">Job Application Accelerator</div>
                <h1 style="margin: 0 0 8px 0; font-size: 22px; font-weight: 700; line-height: 1.3;">Automated Daily Scraping Digest</h1>
                <p style="margin: 0; font-size: 13px; color: #94a3b8;">Report Date: {date_str} &bull; Connected job sites searched</p>
            </div>

            {gmail_section}
            <!-- Stats Highlight Grid -->
            <div style="padding: 24px 28px; background: #f1f5f9; border-bottom: 1px solid #e2e8f0;">
                <table width="100%" cellpadding="0" cellspacing="0" style="table-layout: fixed;">
                    <tr>
                        <td align="center" style="background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0;">
                            <div style="font-size: 24px; font-weight: 800; color: #0284c7;">{stats.get('total', 0)}</div>
                            <div style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-top: 2px;">Total in Database</div>
                        </td>
                        <td style="width: 12px;"></td>
                        <td align="center" style="background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0;">
                            <div style="font-size: 24px; font-weight: 800; color: #16a34a;">+{recent_count}</div>
                            <div style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-top: 2px;">{count_label}</div>
                        </td>
                        <td style="width: 12px;"></td>
                        <td align="center" style="background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0;">
                            <div style="font-size: 24px; font-weight: 800; color: #eab308;">{stats.get('saved', 0)}</div>
                            <div style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-top: 2px;">Saved / Starred</div>
                        </td>
                    </tr>
                </table>
            </div>

            <!-- Platform Breakdown -->
            <div style="padding: 24px 28px; border-bottom: 1px solid #e2e8f0;">
                <h2 style="margin: 0 0 14px 0; font-size: 16px; font-weight: 700; color: #0f172a;">📊 Platform Yield Breakdown</h2>
                <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; background: #f8fafc; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0;">
                    {platform_rows}
                </table>
            </div>

            <!-- Top Opportunities for Louis -->
            <div style="padding: 24px 28px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                <h2 style="margin: 0 0 14px 0; font-size: 16px; font-weight: 700; color: #0f172a;">🎯 Curated High-Match Opportunities</h2>
                <p style="margin: 0 0 16px 0; font-size: 13px; color: #64748b;">Direct matches for Android (Kotlin/Compose), Full-Stack, and Junior Developer roles:</p>
                {job_cards}
            </div>

            <!-- CTA / Live Dashboard Link -->
            <div style="padding: 24px 28px; text-align: center; background: #ffffff;">
                <p style="margin: 0 0 16px 0; font-size: 14px; color: #475569;">Access your live interactive dashboard to filter, review AI pitches, and manage pipeline:</p>
                <a href="{dash_link}" target="_blank" style="display: inline-block; background: #0f172a; color: #ffffff; font-size: 14px; font-weight: 700; padding: 12px 24px; border-radius: 8px; text-decoration: none; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">🚀 Open Job Accelerator Dashboard</a>
            </div>

            <!-- Footer -->
            <div style="padding: 16px 28px; background: #f1f5f9; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
                Automated Daily Notification &bull; Job Application Accelerator &bull; Louis Michael Ricafrente
            </div>
        </div>
    </body>
    </html>
    """
    return html

def send_daily_email(db_path: str = "data/jobs.db", dashboard_url: str = "", new_jobs_count: int = None) -> dict:
    data = generate_digest_data(db_path)
    if new_jobs_count is not None:
        data["new_jobs_count"] = max(0, int(new_jobs_count))
    html_content = build_html_content(data, dashboard_url)
    
    # Save local snapshot of digest
    out_dir = os.path.dirname(os.path.abspath(db_path))
    digest_path = os.path.join(out_dir, "latest_email_digest.html")
    with open(digest_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    new_count = data.get("new_jobs_count", data["recent_count"])
    count_description = "bagong jobs naidagdag" if new_jobs_count is not None else "recent jobs"
    subject = f"[Job Accelerator] {new_count} {count_description} ({data['stats'].get('total', 0)} total)"

    result = {
        "success": False,
        "recipient": RECIPIENT_EMAIL,
        "subject": subject,
        "new_jobs": new_count,
        "total_jobs": data["stats"].get("total", 0),
        "digest_file": digest_path
    }

    if not SMTP_PASSWORD:
        print(f"[!] SMTP_PASSWORD / GMAIL_APP_PASSWORD not detected in environment.")
        print(f"[✓] Daily email digest compiled and saved to: {digest_path}")
        print(f"[*] Preview Subject: {subject}")
        result["message"] = "Digest saved locally. Add Gmail SMTP credentials to .env to enable email delivery."
        return result

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Job Application Accelerator <{SENDER_EMAIL}>"
        msg["To"] = RECIPIENT_EMAIL

        part = MIMEText(html_content, "html")
        msg.attach(part)

        print(f"[*] Connecting to SMTP server {SMTP_HOST}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
        server.ehlo()
        server.starttls()
        server.login(SENDER_EMAIL, SMTP_PASSWORD)
        server.sendmail(SENDER_EMAIL, [RECIPIENT_EMAIL], msg.as_string())
        server.quit()

        print(f"[✓] Daily notification email dispatched successfully to {RECIPIENT_EMAIL}!")
        result["success"] = True
        result["message"] = f"Dispatched successfully to {RECIPIENT_EMAIL}"
    except Exception as e:
        print(f"[!] SMTP Dispatch Error: {e}")
        result["error"] = str(e)

    return result

if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "data/jobs.db"
    res = send_daily_email(db)
    print(res)
