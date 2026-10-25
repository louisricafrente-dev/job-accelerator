# Role filter controls and matching - 2026-10-21

Production deployment: dpl_6njT8WhGRmQiArQMWYwKpkFGncy2, https://job-accelerator.vercel.app/.

Preserved the existing visual style. Replaced the long undifferentiated role chip list with All jobs, Tech & IT, Data & Analytics, Virtual Assistance and a category-scoped Specific role selector. Added data analyst/BI, data science, data engineering, AI/ML, business/systems analyst, other analysts, IT support/infrastructure, cybersecurity, and administrative/executive/customer-support/data-entry filters. Existing saved specialty values restore to their parent family. Selecting VA in Saved or Pipeline no longer jumps to the separate remote VA feed. All jobs includes VA; removed the contradictory Include VA toggle.

Root fixes: Both is no longer accepted as proof of every specialty. Parameterized, word-bounded title matching replaces broad substring matches such as ios/ai/java; React Native is not frontend, BIOS is not iOS, brand-only China Mobile is not mobile development, AI Growth Marketer is not AI/ML engineering. Unsynced local Saved/Applied records cannot bypass role, site, date or other server filters. Counts and pagination use the same SQL predicates as the results. Narrow specialties are based on title or a stored exact specialty, not every skill mentioned in a JD; cross-disciplinary titles may legitimately appear in multiple applicable categories.

Validation: 174 Python tests, frontend/workflow/settings checks, and git diff check passed before final guarded deployment. Actual browser tests against an isolated SQLite fixture verified Data Science results, VA staying in Saved, Mobile excluding cached VA jobs, category-specific options, and restoration after refresh. Production API verified the categories; production browser verified the new controls and Saved Mobile results. Saved/Applied job statuses were not changed in production.

Production screenshot: C:/Users/PC/Documents/antigravity/resilient-pasteur/output/job_role_filters_2026-10-21.png
Live API evidence: C:/Users/PC/Documents/antigravity/resilient-pasteur/output/role_filter_production_verification_2026-10-21.json
