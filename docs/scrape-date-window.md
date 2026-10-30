# Source retrieval and publication-date coverage

All automatic/manual local/cloud collection accepts only today and yesterday in Asia/Manila. Existing stored jobs and Pipeline history are preserved. Unknown dates are never invented. A successful network request does not establish complete jobsite coverage.

## Collection protocol

Sources with verified source-side filters receive them on every page. Small pages continue through a persisted source cursor/offset, not a fixed total-result cap. Query completion is recorded only after its final page is ingested. Feed/query state is window-scoped and resets at Manila day rollover. Source failures and database write failures retain the last committed page; one keyword's failed cursor survives other keywords finishing. Repeated pages/cursors, invalid dates and reversed publication order cannot silently mark the window complete. Internal per-query cursors/page fingerprints are excluded from dashboard progress payloads.

Date-boundary stopping is used only on verified publication-ordered routes. Unknown/unordered sources retain bounded samples and explicit coverage warnings rather than walking historical catalogues or claiming full coverage. `progress.coverage_issues`, board warning/error text and logs identify these limits; a run with a persistent coverage warning finishes Partial without automatically re-fetching the same source indefinitely. Existing UI may label these warnings DEFERRED; read the accompanying coverage reason.

## Every configured source

| Source | Retrieval rule | Remaining limitation |
| --- | --- | --- |
| LinkedIn | JobSpy15 per keyword page with offset; hours since yesterday Manila midnight, rounded up | Provider/library search ceiling approximately1000. A reached ceiling is reported limited; blocks remain errors. Library pagination may internally replay earlier filtered pages. |
| Indeed | JobSpy35 per keyword page with offset and the same hours filter | Same provider ceiling; Indeed's indexed-date filter can differ from employer publication date, so final publication-date guard remains. |
| Glassdoor | JobSpy35 per keyword page with offset and provider day rounding | Same ceiling/blocks; provider dates are day-granularity estimates. |
| ZipRecruiter | JobSpy35 per feed page with offset and hours/day filter | HTML fallback uses days-filtered search but has no verified continuation; flagged limited. |
| JobStreet | Primary catalogue100/page, ListedDate and daterange2 on every request | Provider-relative2days can include older calendar-boundary rows; final Manila date guard remains. Legacy keyword helper is bounded and now reports truncation; production uses full paged catalogue. Timestamp conversion retains yesterday midnight when source is UTC. |
| Kalibrr |50/page, verified activation_date descending, checkpoint until all-old page/provider end | Missing dates or broken order are partial/error, not successful boundary evidence. |
| OnlineJobs.ph |30-row pages via actual `/jobseekers/jobsearch/<offset>` next links; per-keyword checkpoints | Verified date order required to stop at old page. Removed ineffective page= and arbitrary two-request stop. |
| Jobicy | Current `/api/jobs`,50/page, opaque cursor, newest publication order | Walks global recent feed so fixed dev tag cannot silently exclude other configured roles. Stop when past yesterday; seven-day upstream availability still applies. |
| Himalayas | `/jobs/api?limit=20`, opaque browse cursor, verified publication-date order | Search page1 contains mixed promoted results, so it is not used as date-boundary evidence. pubDate is source publication/update date; many fresh source rows can legitimately require many pages. |
| Freelancer |25/page per keyword with offset and from_time/to_time for Manila yesterday00:00 through tomorrow00:00 exclusive | Continues to provider total/last page; repeated pages report failure. |
| Bossjob | Latest sort1, at most two30-row sample pages per keyword | Latest is not verified original-publication order; page1 old records do not rule out fresh page2. Full window remains explicitly limited. No full historical catalogue walk. |
| Remotive | Public recent feed request limit100; strict final date acceptance | Public API24hdelay and no verified date-range/cursor; explicit limited coverage. |
| Remote OK | Read the provider's recent API feed | No verified date-range/history pagination; explicit provider-feed-only coverage. |
| We Work Remotely | All five configured category RSS feeds | Feed snapshots can include years-old rows and do not establish the entire jobsite window; explicit limited coverage. |
| Arc | Public initial listing data | No verified date-ordered continuation from this integration; explicit limited coverage. |
| Wellfound | Four public role landing pages | Ranking/pagination not verified; public access may be blocked; explicit limited coverage. |
| Contra | Public anonymous page when usable | Anonymous probe exposed no opportunity feed; authenticated account/route needed; explicit limited coverage. |
| FlexJobs | Existing authorized search/custom-feed path | Public probe403, no complete publication-date/pagination route verified. No undated full sitemap fallback. |
| Upwork | Existing once/day flconsole request, last30min, limit10 | Provider cannot backfill two days through this interface. Daily low-volume policy unchanged, now explicitly limited. |

The configured19 sources remain enabled. Completing configured source requests is not a claim that every jobsite's full inventory has been enumerated. Relative provider hours/days may overfetch around midnight; invalid/future/old rows remain excluded. A fresh-window source with thousands of real rows requires more small pages; no arbitrary total cap disguises that volume. Existing two-hour execution budget/checkpoints remain, so an unfinished real cycle can require resume.

## Validation

`tests/test_source_coverage.py` exercises later-page fresh jobs, provider cursor/offset arguments, date-boundary stopping, Zip feed pagination, query checkpoints/retries, ingestion failure, invalid dates, order changes, and limited-source results without retry loops. Existing date, auth/isolation and frontend tests remain.

Bounded actual-source checks: OnlineJobs developer search advanced through30/30/30 raw pages and stopped at old dates; Freelancer advanced25/22 and exhausted; Jobicy advanced through three50-row pages; Himalayas advanced through three20-row cursor pages. These did not ingest production jobs and do not establish a completed real19-source cycle. See the workspace output/source-completion-live-2026-10-30.json.

References: [Jobicy official API](https://github.com/Jobicy/remote-jobs-api), [Himalayas OpenAPI](https://himalayas.app/docs/openapi.json), [JobSpy](https://github.com/speedyapply/jobspy), [Freelancer official SDK filters](https://github.com/freelancer/freelancer-sdk-python/blob/master/freelancersdk/resources/projects/helpers.py), [Remotive API](https://github.com/remotive-com/remote-jobs-api). See [specific remaining-source proposals](source-coverage-proposals.md).
