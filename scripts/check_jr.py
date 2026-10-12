import sqlite3
import re

conn = sqlite3.connect('data/jobs.db')
rows = conn.execute("SELECT id, title, company, experience_level FROM jobs WHERE experience_level != 'Junior / Entry'").fetchall()

keywords = [
    r'\bjr\b', r'\bjr\.', r'\bjunior\b', r'\bentry\b', r'\bintern\b', r'\binternship\b',
    r'\bassociate\b', r'\bgrad\b', r'\bgraduate\b', r'\btrainee\b', r'\bapprentice\b',
    r'\bojt\b', r'\bbootcamp\b', r'\bbeginner\b', r'\b0-1\b', r'\b0-2\b', r'\blevel 1\b',
    r'\bl1\b', r'\bdeveloper i\b', r'\bengineer i\b', r'\bearly career\b'
]

hits = []
for r in rows:
    title = r[1].lower()
    for kw in keywords:
        if re.search(kw, title):
            hits.append(r)
            break

print(f"Total hidden junior/entry jobs in database: {len(hits)}")
for h in hits[:20]:
    print(h)
