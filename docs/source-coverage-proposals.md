# Proposals for sources whose full two-day window is not available

The implemented collectors preserve today/yesterday publication dates. The following alternatives are concrete next steps, not already enabled features. No new schedule, paid plan, account export, email alert or publication-date exception is activated by this change.

## Recommended first step: native alerts plus a dedicated alert importer

For Bossjob and Wellfound, native saved searches/job alerts are documented. Configure target searches in the user's own account and deliver alerts to the existing application Gmail. Add a dedicated discovery-alert importer to extract canonical job links and original publication dates, deduplicate into Job Accelerator, and reject unknown/old dates. Existing Gmail Hub stores messages and updates confidently matched applications; it does not already create job discoveries from these alerts. The importer is new work. This avoids downloading whole historical catalogues and can run alongside the already scheduled mailbox scan. Alert delivery is provider-controlled and is not an exhaustive-recall or instant-delivery guarantee.

- [Bossjob job-alert FAQ](https://bossjob.com/blog/faq/2315/talents-faq/)
- [Wellfound saved searches and email alerts](https://help.wellfound.com/article/782-saved-searches)

For other sources, first confirm that the user's account offers a usable alert containing original dates; do not assume every newsletter supplies them.

## Per-source choices

| Source/blocker | Proposed solution preserving posted today/yesterday | Tradeoff/choice needed |
| --- | --- | --- |
| Bossjob latest ranking is not original publication order; refreshed_at missing in bounded probes | Native job alert importer, or authorized account search exposing original-post date filters. Keep small sample marked partial until that route is verified. | Do not silently reinterpret a refresh as a new publication. A changed updated-date policy needs the user's explicit choice and a real available timestamp. |
| Remotive public API delayed24h, no documented date-range/cursor | Prefer native alert/authorized search with original publication timestamps, if available, through the dedicated importer/local account route. | Alternative is an explicitly broader delayed-source publication window, with original dates kept visible. That changes the user's date policy and is not enabled. No promise that a broader window fixes a stale provider feed. |
| Remote OK and WWR public feed snapshots | Keep existing public-feed ingestion, dedup and strict dates; supplement using verified native dated alerts or an official feed/API whose full-window guarantee can be checked. | If no such interface exists, retain feed-only Partial coverage. Unadvertised date URL parameters or a larger feed count cannot prove full-site coverage. |
| Arc initial landing page lacks verified date-ordered continuation | Local browser/account search connector using the site's visible search/filter and actual next controls, after a working route is verified; dated alert importer if supported. | Local PC/browser availability; do not ship an invented private API or claim a60-row page exhausts the window. |
| Wellfound landing pages/ranking and access gates | Native saved-search email alerts first; optionally a local authenticated Jobs search connector for on-demand full visible pages. | User's existing login/human verification may be required. No cookies/passwords copied to Vercel or GitHub. |
| Contra anonymous page has no opportunity feed | Use the actual account Job feed with a local browser connector once the user has logged in and the dated search/pagination is verified. | [Contra's Job-feed instructions](https://help.contra.com/en/articles/9322973-applying-to-jobs-on-contra) describe the real destination. Public marketing HTML is not the job feed. Existing account capabilities must be checked before promising automation. |
| FlexJobs public search403 | Verify an existing authorized account/custom feed and its posted-date filter, then implement that account route locally. | Human verification/access required. No subscription purchase or access-control bypass. If dates/pagination remain unavailable, leave limited and use source account alerts where available. |
| Upwork/flconsole max30-minute recent window, currently once/day | Keep current deliberate limited source; alternatively enable a saved provider feed or supported native notifications/alert importer that captures new jobs continuously. | Continuous capture changes the selected once/day policy and may involve provider quota/plan limits. Must be chosen separately. Increasing lookback_minutes beyond provider support cannot create historical backfill. Never split broad searches to evade provider quotas. |
| LinkedIn/Indeed/Glassdoor/Zip search reaches provider ceiling | Use existing configured narrower title/location searches or add a user-approved, non-overlapping search partition using documented filters, and retain cap warnings. | More requests; blocks and provider access limits remain. No guarantee that a result ceiling means there are zero further matches. |

## Proposed selection

Start with native Bossjob/Wellfound alerts and a dedicated discovery-alert importer. Keep existing strict date policy and other limited public feeds. For Contra/FlexJobs/Arc, validate an existing account route before implementing a local browser connector. Keep Upwork's current daily policy unless the user explicitly prefers continuous capture. The user can choose these independently; unavailable account access or alert contents should be reported with concrete evidence, not filled with assumptions.

This proposal has no paid-provider price estimates: no plan or purchase has been researched or selected. Existing Pipeline, saved jobs, schedules and credentials remain outside these proposed changes.
