# Automatic scraping runs in the cloud

Local automatic runners have been retired. Launching the local dashboard does not schedule scraping. The legacy auto_runner.py and sync_and_notify.py entry points stop with a message directing users to cloud cron or the deployed dashboard.

Vercel cron calls /api/cron/sync on the schedule in vercel.json. Automatic runs read the persisted target_stack matrix on each run. All nonempty saved keywords are used, with repeated entries removed. Defaults apply only if no nonempty matrix is saved. The Auto sync checkbox pauses future cloud runs; Manual Sync remains available.

Query-based boards use the saved matrix as search terms. Feed-based boards fetch their feed through their existing connector; this change does not add a new per-keyword request loop to feeds. Existing relevance/date filtering remains active.

Matrix edits must finish saving to the server before a scheduled run can read them. Pending edits stored only in a browser are not yet available to cloud cron. Per-board rate limits, cooldowns and resumable batches remain separate pending work.
