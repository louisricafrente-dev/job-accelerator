import os
import sqlite3
import time
import libsql_client

TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "https://job-accelerator-rhettrina.aws-ap-northeast-1.turso.io")
TURSO_TOKEN = os.environ["TURSO_AUTH_TOKEN"]

if TURSO_URL.startswith("libsql://"):
    TURSO_URL = TURSO_URL.replace("libsql://", "https://")

def migrate():
    local_db_path = "data/jobs.db"
    if not os.path.exists(local_db_path):
        print(f"Error: {local_db_path} not found.")
        return

    print(f"Connecting to local SQLite database: {local_db_path}")
    local_conn = sqlite3.connect(local_db_path)
    local_conn.row_factory = sqlite3.Row
    local_cur = local_conn.cursor()

    local_cur.execute("SELECT * FROM jobs")
    jobs = local_cur.fetchall()
    print(f"Found {len(jobs)} jobs in local database.")

    local_cur.execute("SELECT key, value FROM user_settings")
    settings = local_cur.fetchall()
    print(f"Found {len(settings)} user settings.")

    print(f"Connecting to Turso: {TURSO_URL}")
    client = libsql_client.create_client_sync(TURSO_URL, auth_token=TURSO_TOKEN)

    # 1. Migrate user settings
    print("Migrating user settings...")
    for s in settings:
        client.execute(
            "INSERT INTO user_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;",
            [s["key"], s["value"]]
        )
    print("User settings migrated successfully.")

    # 2. Migrate jobs in batches of 50
    print("Migrating jobs in batches...")
    batch_size = 50
    total = len(jobs)
    inserted = 0

    insert_sql = """
    INSERT INTO jobs (
        id, dedup_hash, title, company, location, platform, tier, job_url, salary,
        role_category, experience_level, date_posted, status, pipeline_stage,
        follow_up_date, notes, sources, applied_at, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(dedup_hash) DO UPDATE SET
        title = excluded.title,
        company = excluded.company,
        location = excluded.location,
        platform = excluded.platform,
        tier = excluded.tier,
        job_url = excluded.job_url,
        salary = excluded.salary,
        role_category = excluded.role_category,
        experience_level = excluded.experience_level,
        date_posted = excluded.date_posted,
        status = excluded.status,
        pipeline_stage = excluded.pipeline_stage,
        follow_up_date = excluded.follow_up_date,
        notes = excluded.notes,
        sources = excluded.sources,
        applied_at = excluded.applied_at,
        updated_at = excluded.updated_at;
    """

    for i in range(0, total, batch_size):
        batch = jobs[i:i + batch_size]
        statements = []
        for j in batch:
            params = [
                j["id"],
                j["dedup_hash"],
                j["title"],
                j["company"],
                j["location"] or "",
                j["platform"],
                j["tier"],
                j["job_url"],
                j["salary"] or "",
                j["role_category"],
                j["experience_level"],
                j["date_posted"] or "",
                j["status"],
                j["pipeline_stage"] or "applied",
                j["follow_up_date"] or "",
                j["notes"] or "",
                j["sources"] or "[]",
                j["applied_at"] or None,
                j["created_at"] or None,
                j["updated_at"] or None,
            ]
            statements.append((insert_sql, params))

        client.batch(statements)
        inserted += len(batch)
        print(f"Migrated {inserted}/{total} jobs ({inserted*100//total}%)...")

    # Verify count on Turso
    rs = client.execute("SELECT count(*) as total FROM jobs")
    turso_count = rs.rows[0][0]
    print(f"\nVerification: Total jobs in Turso Cloud = {turso_count}")

    rs_applied = client.execute("SELECT count(*) as applied_cnt FROM jobs WHERE status = 'applied'")
    applied_count = rs_applied.rows[0][0]
    print(f"Applied jobs in Turso Cloud = {applied_count}")

    client.close()
    local_conn.close()
    print("MIGRATION COMPLETE! ALL DATA IS NOW PERMANENTLY IN TURSO CLOUD.")

if __name__ == "__main__":
    migrate()
