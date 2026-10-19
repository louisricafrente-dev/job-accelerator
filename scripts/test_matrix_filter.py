import sqlite3
import re
import sys
sys.path.insert(0, ".")
from src.classifier import (
    classify_experience_level,
    is_non_tech,
    is_virtual_assistant,
    is_entry_training_va,
    WEB_PATTERNS,
    DATA_AI_PATTERNS,
    TECH_WHITELIST_OVERRIDE
)

conn = sqlite3.connect('data/jobs.db')
c = conn.cursor()

c.execute("SELECT id, title, company, platform, date_posted FROM jobs WHERE status = 'new' ORDER BY id DESC LIMIT 50")
rows = c.fetchall()

def matches_matrix(title, desc=""):
    t_lower = title.lower()
    if is_non_tech(title, desc):
        return False, "non_tech"
    exp = classify_experience_level(title, desc)
    if exp == "Senior / Lead":
        return False, "senior_lead"
    if is_virtual_assistant(title, desc):
        if is_entry_training_va(title, desc):
            return True, "va_entry_training"
        return False, "va_non_entry"
    text = f"{title} {desc}".lower()
    is_web = any(re.search(pat, text) for pat in WEB_PATTERNS)
    is_data = any(re.search(pat, text) for pat in DATA_AI_PATTERNS)
    is_tech = any(re.search(pat, text) for pat in TECH_WHITELIST_OVERRIDE)
    if is_web or is_data or is_tech:
        return True, "tech_match"
    return False, "unmatched"

accepted = 0
rejected = 0
reasons = {}

for r in rows:
    ok, reason = matches_matrix(r[1])
    reasons[reason] = reasons.get(reason, 0) + 1
    if ok: accepted += 1
    else: rejected += 1

print(f"Sample 50 new jobs: {accepted} Accepted, {rejected} Rejected")
print("Breakdown:", reasons)

print("\nSample rejected jobs:")
for r in rows:
    ok, reason = matches_matrix(r[1])
    if not ok:
        print(f"  [{reason}] {r[1]} ({r[2]})")
