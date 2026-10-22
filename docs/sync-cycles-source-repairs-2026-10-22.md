# Finite sync cycles and source repairs

Sync now and automatic schedules start a fresh search cycle. Repeated clicks during active work return the existing run. Resume unfinished is a separate action that retains completed search cursors and retries eligible sources after cooldown. Job rows, saved/applied statuses, notes and deduplication remain intact.

A source failure defers that source for the rest of the current cycle; other sources keep progressing. When no runnable searches remain, the local/cloud cycle ends Complete or Partial and releases its execution lease. No six-hour source cooldown keeps the cycle in Syncing. Requests have a one-hour cycle budget, assessed between batches. New cycles retain access-block cooldowns; successful feed refresh intervals remain respected. Legacy delayed cloud cycles are reported as Partial and replaced on the next fresh sync; their old queue deliveries cannot execute a newly identified run.

Concrete source repairs:

- Bossjob: replaced the retired `/api/job/search` URL with the public `/bossjob-api-server/jobs/search` endpoint used by Bossjob's own frontend. Parse original publication dates, actual canonical job paths, locations and salary fields. Its revised connector clears only stale 404 cooldowns once; it does not clear 403 access restrictions. Live validation returned 20 raw records and 3 relevant recent jobs.
- JobStreet: normalize slash-bearing keywords such as HTML / CSS to `/html-css-jobs` on the current `ph.jobstreet.com` host. This removes malformed nested paths. A live request through the configured Webshare pool still returned HTTP 403; access is not claimed repaired.
- curl_cffi: move `trust_env=False` to Session construction. The installed Session.request API does not support that argument. The previous mocked request tests missed this defect. Real transport now passes an outbound Webshare check and returns genuine upstream responses.
- Upwork: stop repeatedly requesting the retired public RSS endpoint. Without UPWORK_FEED_URL, show Setup required and make no upstream request. An authorized feed or separate approved API integration is required.

The UI distinguishes terminal Partial from active work, shows deferred-source reasons and eligibility times, keeps Sync now available after completion, and offers Resume unfinished separately. Cloud totals accumulate across batches.

Validation: 206 Python tests plus frontend/workflow/settings, syntax, auth/isolation and whitespace checks passed. Two complete isolated API/worker cycles fetched actual Bossjob data, each ended Partial with a controlled unavailable source, released the lease, used distinct run IDs, kept 3 destination rows without duplicates, and preserved Saved status. The controlled block is a fixture; JobStreet's actual 403 is separately recorded above. No integration test jobs were inserted into production.

Schedules remain midnight and 9 AM Asia/Manila. Explicit access challenges, missing source credentials, and genuinely unavailable endpoints remain limitations; this implementation does not guarantee universal access or solve CAPTCHAs.
