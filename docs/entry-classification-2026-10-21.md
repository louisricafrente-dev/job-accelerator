# Inclusive Junior / Entry classification - 2026-10-21

Deployed to https://job-accelerator.vercel.app/ (deployment dpl_4fY7XR5LoqQf9YvF7Rv9J1Sw4nTF).

Description eligibility now overrides generic/mid/senior title classification when a clear early-career signal is present. Explicit fresh/new/recent graduate invitations, graduating students, entry-level positions, no prior experience, 0-1/0-2/1-2 years, six months, one year, and accepted internship/personal/academic/capstone experience are recognized. Higher experience elsewhere is not a veto per user instruction. Negated fresh-grad invitations and generic degree/training mentions are not affirmative evidence.

JobSpy passes descriptions to the classifier. Shared database ingestion promotes new and enriched records, and a versioned Turso startup migration backfills existing records in batches. Only experience_level changes; status, notes and application tracking stay intact. Migration is idempotent.

Verification: 170 offline Python tests plus frontend/workflow/settings checks passed; final qualifier expansion passed 44 focused tests and the real long Regent JD check. Isolated release copied committed source plus only classifier/database/JobSpy/test changes, excluding unrelated pending aggregator, frontend, and batch edits.

Live authenticated production API confirmed Junior / Entry for Inbox records 39599 (L&T), 39539 (Sucre), 40048 (Asian Technology Solutions), 36823 (World Corp), 36178 (Regent), and 38734 (RELX). At final verification Inbox Junior / Entry count was 380. Totals remained 6520 overall, 6197 Inbox, 118 Saved, 68 Applied, and 137 Archived. Counts may change during active sync. No applications submitted.

Live evidence: C:/Users/PC/Documents/antigravity/resilient-pasteur/output/entry_classification_production_verification_2026-10-21.json
