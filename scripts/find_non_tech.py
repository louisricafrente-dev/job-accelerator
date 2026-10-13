import sqlite3

conn = sqlite3.connect("data/jobs.db")
c = conn.cursor()

keywords = [
    "accountant", "accounting", "bookkeeper", "bookkeeping", "nurse",
    "cashier", "telemarketer", "call center", "customer service",
    "bilingual receptionist", "sales agent", "medical", "graphic designer",
    "social media manager", "content writer", "copywriter", "virtual assistant"
]

clauses = " OR ".join(["LOWER(title) LIKE ?" for _ in keywords])
params = [f"%{k}%" for k in keywords]

c.execute(f"SELECT id, title, company, platform, role_category FROM jobs WHERE {clauses}", params)
rows = c.fetchall()
print(f"Found {len(rows)} non-tech / borderline jobs in jobs.db:")
platform_counts = {}
for r in rows:
    p = r[3]
    platform_counts[p] = platform_counts.get(p, 0) + 1
    print(f"[{r[3]}] {r[1]} @ {r[2]} -> Category: {r[4]}")

print("\nBreakdown by platform:")
for p, cnt in platform_counts.items():
    print(f"  {p}: {cnt}")
