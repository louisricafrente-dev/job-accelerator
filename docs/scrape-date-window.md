# Scrape publication-date window

Automatic, manual, local and cloud scraping accept only today and yesterday in Asia/Manila. This is a calendar-date rule, not a rolling 48-hour retention rule. Existing stored jobs and Pipeline history are preserved.

Source requests narrow collection before ingestion wherever a verified provider filter exists. Sources without a verified date filter remain enabled using small recent feeds/pages, as selected by the user on October 30. Stale, future and unknown dates are still rejected before ingestion. Vague labels such as "recently" do not establish a publication date. Provider-relative hours/days can overfetch at the calendar boundary; they are not an exact Philippine calendar-date API.

| Source | Raw retrieval policy |
| --- | --- |
| JobSpy (LinkedIn, Indeed, Glassdoor, ZipRecruiter) | Request the rounded-up hours since yesterday's Manila midnight (24-48), rather than a fixed 48 hours. Providers rounding to days still request two days. ZipRecruiter no longer bypasses this request; its HTML fallback uses the same provider-supported `days` search filter. |
| JobStreet | `daterange=2`, `sortmode=ListedDate`; both search and catalogue paths. Reset resumed catalogue page when the Manila window changes. No weekly 14-day refresh. |
| Freelancer | `from_time` = yesterday 00:00 Manila, `to_time` = tomorrow 00:00 minus one second, on the actual search request. Retain existing 25-result request. |
| Kalibrr | Verified site Freshness parameters `sort_field=activation_date&sort_direction=desc`, 50 jobs/page. Stop after an entirely dated page is older than yesterday, regardless of catalogue total. Mixed/undated pages cannot establish the stopping boundary. Reset legacy/previous-day offsets; retain same-window progress. |
| Remotive | Public API documents publication-date sorting but no date parameter. Request `limit=100`, instead of the entire catalogue. |
| Himalayas | Switch to documented search endpoint, `sort=recent&page=1`, instead of requesting an oversized general feed. Normalize epoch `pubDate`. |
| Bossjob | Website's latest sort `sort=1`, first page, 30 results. Latest ordering may reflect refreshed listings; do not infer publication ordering for early termination. |
| OnlineJobs | Existing first two keyword-result pages, stopping after an all-old page. No verified request-time date parameter in the public search form. |
| Remote OK / Jobicy / category RSS / Arc / Wellfound / Contra | Retain bounded provider feeds or initial listing pages; no invented date parameters or historical catalogue walks. Remote OK returned 100 entries including its legal notice in the bounded live audit; Jobicy already requests 50. These are provider feeds/pages, not guaranteed exact date-filtered network responses. |
| FlexJobs | Keep search/custom feed. Remove the blocked-page fallback that downloaded a full sitemap with no publication dates, whose jobs could never pass the date policy. Report the block instead. |

Small-feed fallbacks can miss fresh matches beyond their provider slice. This is the user-selected tradeoff for retaining these sources without broad downloads, not a claim of exhaustive collection.

ISO timestamps, RFC dates and epoch timestamps are converted to Philippine dates; date-only source values retain the date supplied by the jobsite. Both normal aggregation and checkpointed batch ingestion enforce the same policy. Deduplication remains enabled.

Validation: `tests/test_today_yesterday.py` covers Philippine midnight, UTC conversion, overfetch, both ingestion paths, and history preservation. `tests/test_raw_date_requests.py` verifies actual request arguments, Kalibrr stopping/continuation, checkpoint rollover and the ZipRecruiter primary/fallback paths. Full offline checks pass 307 Python tests, auth/isolation and four JS suites.

October 30 bounded live Kalibrr run fetched four 50-row pages and stopped (200 raw rows, five accepted matches), despite the provider reporting 2,731 catalogue entries. No production ingestion occurred. Bounded live Remotive/Himalayas/Freelancer connector requests also completed without errors. This sample is not a full-cycle speed or billing benchmark.

Provider references: [JobSpy](https://github.com/speedyapply/jobspy), [Freelancer official SDK search filters](https://github.com/freelancer/freelancer-sdk-python/blob/master/freelancersdk/resources/projects/helpers.py), [Remotive public API](https://github.com/remotive-com/remote-jobs-api), [Himalayas OpenAPI](https://himalayas.app/docs/openapi.json). Kalibrr and Bossjob sort names were checked against their live website JavaScript and bounded requests; an experimental Kalibrr `activation_date` query parameter was ignored and is deliberately not shipped.
