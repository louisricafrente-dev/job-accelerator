# Scraping performance review - 20 October 2026

The current cloud design already supports one-click continuation while the dashboard stays open. A full remake is not justified by this review. The dominant workload is the full keyword-by-board matrix, followed by upstream page requests and database writes. The deployed version was not inspected for source parity and these changes have not been deployed.

## Workload and runtime limits

- The default connector list contains 20 boards: 14 query connectors and six feed connectors. With 295 selected keywords, that is 4,130 keyword-board searches plus six feeds per complete cycle. A fetch can request several pages.
- Cloud execution dispatches work for 150 seconds per request, with up to 12 different boards in flight. One board processes its keywords sequentially, with a two-second gap between fetches. The dashboard chains requests until work is complete or only cooldown work remains. In-flight work can run beyond the dispatch budget.
- For one healthy query board alone, 295 fetches averaging four seconds plus 294 two-second gaps already take 1,768 seconds (29 minutes 28 seconds), before database time and cloud request boundaries. This is arithmetic, not a measured live benchmark. Slower fetches, internal retries, pagination, or more than 12 competing boards extend that time.
- Transient errors defer a board for 15 minutes; recognized blocks defer it for six hours. A 30-minute completion guarantee cannot include unavailable or blocked boards under the present cooldown rules.
- The local background path runs the older unbudgeted orchestrator, rather than the durable cloud queue. A local run is not a reliable benchmark for the deployed cloud path. Its 600-second distributed lease can also expire before a long full-matrix run finishes; this review does not change that path.
- "Complete" currently means all configured searches have run, not every posting on each website: JobSpy requests 35 results per keyword; other connectors also have page/result caps. These limits and the saved matrix are unchanged.

## Implemented changes and evidence

1. Skip unchanged duplicate database updates. The mocked cloud ingestion test inserts one job and repeats it 20 times: one SQL write total, with one catalog read. Previously that path issued 21 writes. Salary changes and new source links still write, and unchanged results preserve candidate status, notes, and timestamps.
2. Save one checkpoint for the completed group of fetches. A deterministic 12-board completion fixture needs three checkpoints (initial, group, final), compared with 14 in the previous per-board loop. Jobs are ingested before cursor advancement; existing crash/retry tests still cover repeated fetches after a checkpoint failure. The reduction depends on how many fetches complete together.
3. Record fetch and save timings for each completed search in the existing logs and board telemetry. These allow a real run to distinguish upstream waiting from ingestion overhead without changing the dashboard UI.

These are operation-count improvements, not a measured end-to-end speedup. No live board scrape, production database mutation, application submission, or deployment was performed.

## Validation and review boundary

The local regression runner passed 117 Python cases, two explicit authentication/isolation functions, three JavaScript regression suites, JavaScript syntax, and Git whitespace checks. The focused ingestion/batch/database suites also passed 42 cases before the timing log addition; the full runner was repeated after that addition.

Read completely: `src/aggregator.py`, `src/sync_batches.py`, `src/connectors/base.py`, `src/connectors/jobspy_adapter.py`, `src/connectors/ph_jobs.py`, `src/connectors/remote_feed.py`, `tests/test_sync_batches.py`, `tests/test_sync_optimization.py`, `scripts/check_regressions.py`, and `docs/cloud-sync-batches.md`. Read targeted sections of `src/database.py`, `src/server.py`, `src/static/app.js`, `run.py`, and adjacent tests. This is a scraping-path performance review, not a complete security audit of every modified file in the existing worktree.

Checklist within changed paths: SQL injection - parameterized writes retained; XSS - no new rendering sink; authentication/authorization/CSRF - no route changes; races - live tracking state remains protected by existing conditional SQL and unchanged fetches no longer touch it; session handling - unchanged; cryptography - unchanged; disclosure - only elapsed durations added; resource exhaustion - concurrency and cooldowns retained, existing dependency stalls remain; business logic - matrix, limits, ingestion-before-checkpoint ordering, retry behavior, source merging, and archive behavior exercised by regressions. External availability, production database latency, upstream library retry duration, and actual 30-minute throughput remain unverified.

Next evidence needed is a representative cloud cycle with the new timing logs. A separate worker service would let one click continue after the dashboard closes, but worker hosting alone does not shorten slow site requests or remove cooldowns. Increase per-board concurrency only after source-specific timing and rate-limit evidence supports it; multiplying requests blindly risks longer cooldowns.


## Implemented October 20 follow-up

- Completed fetches share one ingestion batch and one atomic two-key checkpoint/status write. Query cursors advance only after successful ingestion. Clear cached dedup data after write failures.
- Preserve all production matrix keywords and per-board rate-limit cooldowns. Manual browser loop continues immediately runnable cloud batches after one click.
- Store available source descriptions through an additive description-column migration; preserve longer existing descriptions and application notes/status. Render escaped plain text in expandable job cards. Existing rows enrich when rediscovered; no fabricated descriptions.
- Remove mislabeled Himalayas fallback from Bossjob. A failed Bossjob endpoint is reported as failed.
- JobStreet no longer stops pagination because the first page contains no matching recent titles. JobSpy errors metadata propagates instead of silently claiming an empty success.
- 125 Python regression cases, explicit auth/isolation checks and three frontend suites passed before deployment.

Limits: full matrix completion is not proof every posting on a source was enumerated. Existing connector page/result limits remain. Sites may block cloud IPs or restrict access. Manual continuation needs the dashboard open. No paid hosting change or guarantee of a 30-minute complete crawl.


Production verification: final deployment dpl_CE7gQUcWZT7KN6gu9PdBXuqM8hri is READY and aliased to job-accelerator.vercel.app. One manual click continued into subsequent cloud batches. Observed progress rose from 105/4130 to 561/4130; database listing count from 2143 to 2692 during observation. Saved descriptions were present in authenticated production API results and expandable cards. These counts are a live sample, not a completed crawl or a controlled before/after benchmark. No emails sent. Saved 83 and Pipeline 53 remained unchanged. Active browser tab retained for continuation.

Relevance follow-up: removed ambiguous bare 'ml' match that interpreted perfume volume as machine learning, and rejected explicit physical-engineering titles unless they identify a software role. Historical rows were not deleted. This remains rule-based screening, not human-equivalent evaluation.
