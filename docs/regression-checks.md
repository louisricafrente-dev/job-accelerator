# Regression checks and guarded deployment

Run from the repository root with Python 3.12, Node.js, and the dependencies in requirements.txt installed:

```sh
python scripts/check_regressions.py
```

The command runs Python tests, explicit authentication functions, JavaScript syntax checks, both frontend regression suites, and Git whitespace validation. Python regression checks block real socket connections and replace default server connectors so tests do not scrape boards or send emails.

Regression checks run locally. No GitHub Actions workflow is included.

Use the guarded local deployment entry point:

```sh
python scripts/deploy.py --prod
```

This runs checks first and stops on any failure. Only after success does it invoke the already-installed, configured Vercel CLI. Omit --prod for a preview deployment. The script does not install the CLI or set credentials.

Direct Vercel CLI commands and hosting-provider automatic deployments bypass this local wrapper. Use the guarded local entry point when checks must pass before deployment.

## Tracking and notes

- Status updates affect only the selected job ID. Other postings with matching company/title/location keep their own history. Existing records affected by earlier propagation are not automatically rewritten because their correct prior state cannot be inferred safely.
- Inbox, Saved, Pipeline, Archived, and VA views remember independent filters. Saved and Pipeline start with all dates and unrestricted role/platform filters. A user's later filter choices are remembered across switching and reloads through the settings API.
- Notes save on blur or Enter. Pending means the change is queued; Saved requires a successful server acknowledgment; Failed - retry keeps the local edit and provides a retry button. Online/visibility events replay queued changes. Writes for the same job are serialized, and acknowledgment of an older revision does not discard a newer pending edit.

## Verification on 20 October 2026

- 83 Python unittest cases and two explicit authentication functions passed.
- Existing frontend regressions and new workflow regressions passed.
- A headless local browser check verified an old Pipeline job remains visible with all dates, a failed note save shows Failed - retry, retry saves the note, the note survives reload, and Saved defaults to all dates.
- Browser checks used a temporary database and mocked save failure. No deployment or live application submission was performed.

## Selected follow-up repairs

Guest access is temporarily disabled by default in `create_app`. New guest logins are rejected, existing guest tokens cannot access authenticated data, and guest login controls are disabled. Existing guest data is retained. The old guest-copy privacy defect is not repaired; do not reopen guest access until it is addressed. Explicit guest-enabled app construction is used only by the legacy isolated guest test.

Preference writes are serialized within a page and capture their originating session. This prevents a slower earlier request from overtaking a newer filter choice. Cross-device and concurrent-tab conflict resolution is not provided.

Cron routes now honor auto-sync pause, return skipped when paused, preserve partial/error/already-syncing results, return HTTP 500 for failed sync, and report partial when email delivery fails after a successful sync. Manual `/api/sync` remains available while scheduled work is paused.

The launcher probes public `/api/health`, recognizes an existing Job Accelerator instance, and leaves unknown listeners running. It no longer executes taskkill to reclaim a port.

## Preference recovery and requisition identity

Settings requests time out after 10 seconds. The newest pending value per key is stored in identity-scoped localStorage, coalesced and retried. Each flush makes up to two attempts, followed by a five-second retry delay if values remain pending. Authentication bootstrap, online, and visibility events also trigger recovery. Pending preferences take precedence over stale server values during hydration after reload.

Writes include per-key revisions. The database stores revision metadata with the value and atomically rejects older revisions, while API/settings readers continue returning plain preference values. This protects against an aborted request that completes server-side after a newer retry. Existing unversioned clients can still write preferences; mixed old/new-client writes and device clock skew are not a full distributed conflict-resolution system.

Distinct same-board URLs no longer merge merely because title/company/location/date match. Matching URLs in an existing source list are recognized on re-fetch. A cross-board group cannot absorb a second distinct requisition from a board it already contains. SQLite and the mocked Turso adapter path have regression coverage. Existing historically merged rows are not automatically split because their correct per-requisition history cannot be inferred safely.

Verification: 93 Python cases, two explicit auth functions, and three frontend suites passed. A local browser test verified failed preference persistence, reload hydration over stale server settings, and successful retry. Mocked frontend tests cover a stalled request and a late acknowledgment; API/database tests verify stale revisions cannot replace newer values. No production database changes or deployment occurred.

## Cloud matrix scheduling

Automatic sync now reads persisted target_stack on every run, deduplicates comma-separated keywords, and uses every selected keyword for query connectors. Explicit Manual Sync queries override the saved matrix for that run. Backend defaults are used only without a nonempty saved matrix. Automatic local runners are retired. The cloud cron schedule remains unchanged.

97 Python cases, two explicit auth functions and all three frontend suites passed before the cloud matrix deployment, including full saved-matrix execution, updated matrix loading, default fallback, manual override, and both cron aliases. Connectors were mocked; this did not exercise live boards. The existing limits on pacing, request volume and function duration still apply.
