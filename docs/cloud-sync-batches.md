# Cloud sync batches

Automatic cron and production Manual Sync use the same durable search queue. The saved matrix is retained in full; no selected keywords or connector result limits are reduced.

- Each board keeps its own keyword cursor and failed-search retry list in shared database settings. Progress survives function-instance changes.
- New work is dispatched for up to 150 seconds, with at most twelve board fetches in flight and one fetch at a time per board. In-flight fetches finish before the response is returned. This is a dispatch budget, not a hard cancellation mechanism for a stalled dependency.
- Each completed fetch is filtered and ingested before its cursor is checkpointed. A crash between ingestion and checkpoint may repeat a fetch, but normal ingestion deduplicates the results. Ingestion failure does not advance the cursor.
- Board rotation is checkpointed so a short run does not continually favor the first sources.
- There is a two-second gap between successive query fetches on a board, in addition to existing per-page delays. A fetch may internally make multiple HTTP requests; this is not a two-second limit on every individual HTTP request.
- Errors defer the board for 15 minutes; detected 429/403/CAPTCHA/rate-limit errors defer it for six hours. Failed keywords remain queued for retry. These protections depend on the connector surfacing the error; an upstream library returning empty results without an error is not distinguishable from a successful empty search.
- Completed board cycles wait six hours before refreshing. Manual force requests do not bypass this shared batch state.
- Feed connectors fetch once per refresh cycle, independent of the number of matrix keywords. Remotive now uses one unfiltered public API call, retaining all returned relevant recent jobs instead of four category calls capped at 50 each. Arc is treated as a feed to avoid repeatedly fetching the same page for different keywords.
- A changed matrix resets query cursors. Feed refresh times and active error cooldowns remain protected.

## Using the progress indicator

`28/4130 searches saved` counts completed keyword-board pairs, not unique jobs. Manual Sync publishes a durable cloud run. A private queue worker executes 120-second batches and publishes the next delivery; the browser can close. Cron still executes an initial 150-second batch and requests queue continuation.

The API-directory deployment explicitly routes `/api/queue_worker` to its private queue function before the dashboard catch-all. The callback registers the consumer group supplied in Vercel's private delivery headers before SDK dispatch; this must match the deployment trigger's generated group.

Queued work is distinct from an active scrape. Status only shows Syncing while a sync lease is active. A run with no worker update for ten minutes past its scheduled delivery is reported as stalled; expired runs are reported as partial. Clicking Sync or the next cron invocation republishes stalled work with a new message step, retaining its run ID, snapshotted keywords, search cursors, and cooldowns. Runs from another deployment are similarly republished into the current deployment partition, preserving a future scheduled retry. A worker lease serializes deliveries and recovery, so late or duplicate messages cannot fork continuation. Failed recovery retains the old step and reports an error.

The cron schedule remains once daily. Source blocking and hosting failures can still prevent a complete rotation; unfinished searches remain checkpointed.

## Validation

Offline tests simulate all 295 keywords across separate instances, time-budget stops, board rotation, incremental saving, retries, cooldowns, feed reuse, database failure, and a crash after ingestion. The Remotive fixture verifies a single request retains 250 relevant returned records. Existing query connector result limits remain unchanged. Frontend and browser checks verify partial batches show progress/continuation rather than claiming the full search is complete.

No live job-board scrape or load test was used for validation. Existing third-party restrictions, source errors, the cron authorization finding and dependency stalls remain separate risks; batching is not a no-blocking guarantee.

## Reduced ingestion overhead

The cloud batch retains its deduplication catalog in memory for the duration of that request. Nonempty fetches reuse it instead of downloading the full jobs table again per search. Empty results do not open an ingestion database connection. The catalog omits notes and other fields that are unnecessary for deduplication. Write failures discard the cache so retries reload persisted state. Existing Applied/Saved status and notes are preserved by database writes, including changes made while a cached batch is running.

No matrix entries or connector result limits were reduced. Up to twelve distinct boards can fetch concurrently; a given board still has at most one fetch in flight and keeps its existing gaps, page delays, and error cooldowns. Repeated matrix changes retain the absolute block timestamp.

Unchanged duplicate jobs now skip the database UPDATE, including its timestamp change. Changed salaries, newer dates, and additional source links still write normally. Completed fetches collected in the same scheduler pass share one progress checkpoint after their individual ingestion succeeds. A crash before that checkpoint can repeat those fetches; ingestion still deduplicates them. Query completion logs now include fetch and save duration in seconds, also exposed as the latest board telemetry fields `fetch_seconds` and `save_seconds`.

Validation now includes 113 Python cases, three JavaScript regression suites, and a mocked browser run confirming one click chains three cloud batches with the same keywords, displays the cumulative six new jobs, and stops when finished. The cloud-ingestion fixture verifies twenty nonempty searches require one catalog read rather than twenty. This is a database round-trip improvement, not a measured guarantee about live job-board speed. No live board load test was run.

## Reuse recent keyword searches

Successful query searches now keep a durable timestamp per board and keyword, recorded only after ingestion succeeds. Matrix edits, reordering, and new cloud/local cycles reuse successful searches from the existing six-hour refresh window. Only new, expired, failed, or unfinished keywords need requests. Connector revision changes invalidate that board's cache; access-block cooldowns remain in force. Feed boards retain their existing single-fetch refresh behavior.

The keyword cache stays in the private checkpoint and is omitted from progress/telemetry payloads. All selected keywords still count toward coverage, including reused completed work. Legacy checkpoints without query timestamps do one full pass before they can benefit from reuse. No keyword truncation or hard-coded substitute searches are used.


## Grouped searches on fresh cycles

JobStreet, LinkedIn and Indeed now attempt OR groups of up to five selected keywords, with a 250-character expression limit. Other query boards keep individual searches; feeds still fetch once. Existing per-board concurrency limits remain. Complex user expressions bypass grouping unchanged.

Each group covers its original keyword indices in the durable checkpoint only after successful fetching and ingestion. Progress counts keyword/board coverage, not HTTP requests; board telemetry/logs report grouped versus individual fallback. Group membership does not remove any keyword from the matrix.

JobStreet paginates up to its existing three-page safety limit and verifies exhaustion via short pages or totalCount. If a group exceeds that capacity, repeats a page, is empty or rejects Boolean syntax, its partial union is discarded and each original keyword uses its existing individual search. Known oversized unions stop after the first page. JobSpy handles LinkedIn/Indeed pagination internally, with a larger raw result budget per group. Reaching that budget, or an empty group, triggers the same fallback. Raw rows before local relevance filtering decide saturation. Access blocks/server failures defer the group and keep every member unfinished; fallback does not hammer a blocked board.

References: [LinkedIn Boolean help](https://www.linkedin.com/help/linkedin/answer/a524335), [Indeed advanced search help](https://www.indeed.com/help/job-seekers/articles/204488950-improving-your-job-searches-tips-and-help), [JobSpy source/API](https://github.com/speedyapply/jobspy). JobStreet live read-only check: Jetpack Compose returned 4 raw IDs, Rust 10; their OR group returned exactly the 14-ID union. The implemented grouped connector returned 7 locally relevant jobs from those 14 with no error. Nothing from the check was inserted.

Savings depend on result density and source behavior: sparse complete groups avoid repeated searches, whereas broad or uncertain groups cost an extra probe before fallback. Existing individual result limits remain; this is not a guarantee of exhaustive access to every listing on third-party boards.


## JobStreet catalogue ingestion (supersedes keyword searches there)

The default JobStreet connector now imports the PH catalogue once and uses existing local relevance/skill scoring, independently of the number of selected matrix keywords. The old JobStreet keyword connector remains available for regression comparisons; LinkedIn/Indeed grouping is unchanged. Other boards retain their existing behavior.

Bootstrap scans the complete 14-day catalogue in pages of 100, with a durable page checkpoint committed only after job ingestion. Each page is one scheduler task; time limits, process restarts, matrix edits, and new cycle IDs retain unfinished pages. Access blocks keep the current page pending. Repeated/truncated pages fail explicitly rather than being marked complete.

After bootstrap, a fresh cycle scans the elapsed time since the last completed catalogue pass plus six hours of overlap, rounded up to whole days (maximum 14). The initial pass start is used as the watermark, so time spent importing is not skipped. A weekly 14-day reconciliation catches late/backdated source changes. The existing six-hour refresh cooldown remains. Changing the matrix only changes local matching; it does not force a second download of already indexed posts.

Read-only endpoint checks on 2026-10-25 found 31,647 raw posts in the 14-day window, with page 100 and final page 317 accessible (100 and 47 records respectively). A warm-checkpoint benchmark six hours after a simulated completed import used a one-day window and fetched 234 records in 3 page requests, completing in 7.14 seconds including two-second page gaps; 17 records passed existing local relevance filters. No benchmark records were inserted. This is a measured JobStreet warm-refresh result, not a benchmark for bootstrap, all boards, peak weekday volume or database ingestion. Full bootstrap remains substantially longer and resumable.

The monitored search counter now excludes JobStreet's per-keyword tasks because it is a catalogue source. Logs show catalogue page, source total and window length; selected matrix keywords are preserved. Direct calls without a time budget use a 150-second batch when a checkpointed catalogue source is present, returning explicit unfinished progress rather than claiming one page is the whole import.


## 2026-10-25: catalogue verification and bounded group probes

The full preset matrix now contains 545 terms. Discovery keeps every supplied term; this is not an 80-search cap. Kalibrr now joins JobStreet as a checkpointed catalogue source. Live checks established that Kalibrr ignores the old `name` and `page` parameters: page 1, page 2, and an impossible keyword returned the same first records. Its `offset` parameter returned distinct pages, with 2,694 records and a 94-record final page. The connector uses 100-record pages, the real `id` and nested company `code`, plain-text descriptions, source country, and existing eligibility/date filters. Each page advances only after ingestion succeeds. The full catalogue refreshes on the existing six-hour feed cooldown; it does not falsely assume chronological ordering to stop early.

LinkedIn/Indeed now use one bounded OR probe per scheduled operation (16/36 records requested, rather than 76/176 for five terms). Results from saturated probes are saved immediately. Each unresolved member remains pending and is searched individually through the durable scheduler, including after a restart or matrix edit. Unsafe expressions skip the OR probe. Empty or rejected unions still require individual searches; access errors defer the source. No partial union is reported as complete coverage. Individual result limits are unchanged; neither query completion nor feed completion promises every posting on a third-party website.

Local batches request 30 seconds before uploading available jobs, rather than 90 seconds. A running provider call can finish after that batch scheduling budget. Local and cloud cycles allow at most a two-hour scheduling window, check the remaining time before each new batch, and retain unfinished work with partial status. This is not a guarantee that a blocked provider becomes available within two hours, nor a hard process-kill deadline for in-flight network calls/uploads.

Run `python scripts/benchmark_discovery.py` for a fresh, all-preset, all-connector benchmark (up to two hours). It uses a disposable SQLite database, disables proxy routing, excludes cloud DB credentials and the Upwork token, and never uploads jobs. Its JSON report separates elapsed time, first save, unique saved jobs, completed query coverage, catalogue checkpoints, and deferred boards. Transport counts do not count JobSpy internal HTTP pages. Live source data changes between runs. Benchmark files in `scratch/` are local evidence, not deployment assets.
