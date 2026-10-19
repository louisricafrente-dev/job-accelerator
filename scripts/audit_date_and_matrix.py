import sys
sys.path.insert(0, ".")
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('data/jobs.db')
c = conn.cursor()

today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
cutoff_14d = (datetime.now(timezone.utc) - timedelta(days=14)).strftime('%Y-%m-%d')

print('Today UTC:', today)
print('14-day cutoff:', cutoff_14d)

older_than_14d = c.execute("SELECT count(*) FROM jobs WHERE date_posted < ? AND date_posted != ''", (cutoff_14d,)).fetchone()[0]
within_14d = c.execute("SELECT count(*) FROM jobs WHERE date_posted >= ?", (cutoff_14d,)).fetchone()[0]
empty_date = c.execute("SELECT count(*) FROM jobs WHERE date_posted = '' OR date_posted IS NULL").fetchone()[0]
total = c.execute("SELECT count(*) FROM jobs").fetchone()[0]

print(f'Total jobs in DB: {total}')
print(f'Jobs OLDER than 14 days: {older_than_14d} ({older_than_14d/total*100:.1f}%)')
print(f'Jobs WITHIN 14 days: {within_14d} ({within_14d/total*100:.1f}%)')
print(f'Jobs with EMPTY date: {empty_date} ({empty_date/total*100:.1f}%)')

# Check older jobs by status
by_status = c.execute("SELECT status, count(*) FROM jobs WHERE date_posted < ? AND date_posted != '' GROUP BY status", (cutoff_14d,)).fetchall()
print('\nOlder than 14d breakdown by status:')
for s, cnt in by_status:
    print(f'  {s}: {cnt}')

from src.classifier import is_relevant_opportunity
rows = c.execute("SELECT id, title, notes FROM jobs WHERE status = 'new'").fetchall()
match = 0
non_match = 0
for _, title, notes in rows:
    if is_relevant_opportunity(title, notes or ""):
        match += 1
    else:
        non_match += 1

print(f'\n\"new\" jobs total: {len(rows)}')
print(f'  Matches Match Matrix: {match}')
print(f'  Non-match (Senior/Lead/Non-tech/Non-entry VA): {non_match}')
