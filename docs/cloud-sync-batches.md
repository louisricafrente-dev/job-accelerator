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

`28/4130 searches saved` counts completed keyword-board pairs, not unique jobs and not just 28 of 295 keywords globally. A single Manual Sync click automatically requests the next cloud batch while work is immediately available. Keep the dashboard tab open for this continuation; closing it prevents the next request. Each active request still runs in the cloud. Cooldown-only work pauses rather than polling or repeatedly retrying blocked boards. Automatic cron advances one batch per daily invocation. Some boards may be waiting for a cooldown. Manual Sync reloads results and counts after each completed batch.

The existing cloud cron remains once per day. This change does not introduce a paid worker, more frequent schedule, or a guarantee that every keyword on every source is refreshed daily. Full 295-keyword rotation may require multiple runs. A more frequent supported cloud scheduler would be a separate hosting change.

## Validation

Offline tests simulate all 295 keywords across separate instances, time-budget stops, board rotation, incremental saving, retries, cooldowns, feed reuse, database failure, and a crash after ingestion. The Remotive fixture verifies a single request retains 250 relevant returned records. Existing query connector result limits remain unchanged. Frontend and browser checks verify partial batches show progress/continuation rather than claiming the full search is complete.

No live job-board scrape or load test was used for validation. Existing third-party restrictions, source errors, the cron authorization finding and dependency stalls remain separate risks; batching is not a no-blocking guarantee.

## Reduced ingestion overhead

The cloud batch retains its deduplication catalog in memory for the duration of that request. Nonempty fetches reuse it instead of downloading the full jobs table again per search. Empty results do not open an ingestion database connection. The catalog omits notes and other fields that are unnecessary for deduplication. Write failures discard the cache so retries reload persisted state. Existing Applied/Saved status and notes are preserved by database writes, including changes made while a cached batch is running.

No matrix entries or connector result limits were reduced. Up to twelve distinct boards can fetch concurrently; a given board still has at most one fetch in flight and keeps its existing gaps, page delays, and error cooldowns. Repeated matrix changes retain the absolute block timestamp.

Unchanged duplicate jobs now skip the database UPDATE, including its timestamp change. Changed salaries, newer dates, and additional source links still write normally. Completed fetches collected in the same scheduler pass share one progress checkpoint after their individual ingestion succeeds. A crash before that checkpoint can repeat those fetches; ingestion still deduplicates them. Query completion logs now include fetch and save duration in seconds, also exposed as the latest board telemetry fields `fetch_seconds` and `save_seconds`.

Validation now includes 113 Python cases, three JavaScript regression suites, and a mocked browser run confirming one click chains three cloud batches with the same keywords, displays the cumulative six new jobs, and stops when finished. The cloud-ingestion fixture verifies twenty nonempty searches require one catalog read rather than twenty. This is a database round-trip improvement, not a measured guarantee about live job-board speed. No live board load test was run.
