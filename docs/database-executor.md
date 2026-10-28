# Database executor (not deployed)

`JOB_EXECUTOR=database` selects the new transport. Without it, the existing deployed worker/queue behavior remains available. No production scheduled task, Vercel environment or default branch has been changed by this patch.

## Flow

1. Sync stores one command in the indexed `user_settings` inbox and requests a GitHub Actions supervisor. Repeated clicks retain the same active command.
2. `python scripts/inbox_worker.py --executor local` reads the small inbox once every 60 seconds. It sends no idle dashboard requests or periodic idle presence writes. Startup/shutdown records supply Last seen, which is not an online guarantee.
3. The PC may claim within 90 seconds. The cloud supervisor waits for this acknowledgment deadline or an expired active claim, then uses the same scraper and shared checkpoint. GitHub queue startup time is additional; 90 seconds is not a guaranteed cloud start time.
4. Active claims renew every 60 seconds with a 180-second expiry. Atomic compare-and-swap claims and database-side fence predicates protect job/checkpoint writes after cancellation or takeover. The existing scraper lease remains in place.
5. Existing deduplication and job tracking rules remain unchanged. Automatic runs with additions retain the digest call; duplicate supervisors do not repeat a completed command. Provider blocks finish as Partial rather than pretending retrieval succeeded.

The main scraper no longer needs repeated 8-job dashboard uploads. It inserts via the existing ingestion code directly into Turso. The separate Upwork monitor remains on its existing queue/local task for continuity; paused auto-sync now stops that queue chain and enabling auto-sync restarts it. This patch does not claim zero Vercel requests or zero provider usage.

## Usage changes

- Idle PC: existing theoretical 8,640 Vercel worker calls/day becomes zero worker calls to Vercel plus 1,440 indexed inbox reads/day, while continuously online. A powered-off PC makes none of these reads.
- Active work: lease/checkpoint/database traffic remains necessary. Cloud supervision also reads the command while waiting for local completion.
- Dashboard stats: one grouped jobs query instead of five. A regression test verifies tracking counts and the single-query budget.
- Gmail navigation badge: summary payload, at most one fetch per five minutes per page rather than downloading all message bodies with each stats refresh.
- Static assets: browser cache 60 seconds, shared cache one hour; authenticated API responses remain uncached.
- Dashboard cadence remains 60 seconds idle/5 seconds active, with hidden-tab cancellation and one polling loop.
- Webshare is no longer an implicit proxy default. The configured 100-proxy pool is supplied through a secret for sandbox validation. A successful DIRECT scrape does not prove proxy health.

These are request/query changes, not a guarantee of equivalent billing savings or unlimited provider capacity.

## Validation

- `python scripts/check_regressions.py`: full offline Python, auth/isolation and Node regressions. Tests clear provider/cloud credentials and block network access.
- `python scripts/test_turso_inbox.py --env-file <ignored-local-file>`: existing Turso, UUID-prefixed test settings only, ownership/takeover/SQL fence tests and exact-key cleanup; never invokes the scraper, `init_db`, or writes jobs. Can also read credentials from environment in GitHub.
- `python scripts/actions_runner.py --sandbox`: bounded actual source fetch into temporary SQLite with the existing scraper/deduplication.
- `.github/workflows/scraper-sandbox.yml`: test-branch validation; Vercel automatic deployment is disabled for `codex/actions-migration`.

## Configuration and cutover prerequisites

Do not enable the new transport before completing these checks:

- Make `scraper-worker.yml` available to GitHub workflow dispatch on the intended/default branch. Do not merge the feature branch or deploy as part of testing without the user's deployment approval.
- Supply a repository-scoped dispatch credential (`GITHUB_ACTIONS_TOKEN`, Actions write) to the API environment. Existing local CLI authorization is not silently reused or copied into Vercel. No new access credential has been created by this patch.
- Set production runner `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `SCRAPER_PROXY_LIST` and relevant existing SMTP/flconsole secrets. Test-only Turso credentials use `TURSO_INTEGRATION_DATABASE_URL`/`TURSO_INTEGRATION_AUTH_TOKEN` in the sandbox workflow.
- Wait for active legacy scrape completion, stop the old Windows worker, set up the direct worker using securely supplied Turso environment, and verify command/lease/ingestion behavior before turning on `JOB_EXECUTOR=database`.
- Verify all chosen sources with bounded runs; target-site restrictions, exhausted proxies and external quotas remain independent of runner availability.
- Keep the legacy path available for rollback. Do not simultaneously run both local worker entry points; both use the same local process lock.

No deploy, merge, production worker restart, schema migration or billing change is included in the completed testing work.
