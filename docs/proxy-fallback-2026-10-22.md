# Connection fallback and source isolation

All 19 connectors now use the same request routing rules and their aggregator's saved proxy settings. Requests no longer change process-wide proxy environment variables while concurrent connectors are running.

- Local hybrid requests start direct and have at most one proxy fallback for a connection failure, including a timeout while reading a response body.
- Cloud hybrid and always-proxy requests start with a healthy configured proxy and can try one alternate proxy after a connection failure. Failed proxy connections are skipped for five minutes within the process. Disabled mode never selects proxies.
- Explicit 403/404/410/429 responses and detected HTML challenge pages do not trigger IP cycling. Per-board cooldowns and saved retry checkpoints remain in place. Retry-After values can extend the normal board cooldown.
- The authenticated paired worker receives the dashboard's proxy settings through its private request endpoint and saves changes locally. Credentials do not enter worker status or telemetry. Transport exception text is redacted before being logged or published.
- JobSpy connection-error frames use the same limited fallback. Partial frames containing jobs are retained instead of discarded for a retry.
- Wellfound, Contra, and FlexJobs failed responses no longer become a fresh successful cache entry.
- Logs and board cards record DIRECT, WEBSHARE, PROXY, or CACHE with the connection retry count. Checkpoint telemetry retains this information during cooldown polls.

Validation: 196 Python tests passed, plus frontend, workflow, settings, JavaScript syntax, authentication/isolation and whitespace checks. Coverage includes proxy fallback after body timeout, disabled mode, unhealthy proxy exclusion, settings isolation across concurrent connectors, credential redaction, challenge handling, Retry-After persistence, private worker configuration, and successful board progress while another board is blocked.

Two limited live checks used the existing configured pool: an outbound IP-check request succeeded via Webshare after a controlled direct timeout; a Remotive feed request using the same controlled failure parsed 3 jobs through Webshare without an error. The direct failure was deliberately injected for these checks, so they prove the fallback path and real proxy connectivity, not spontaneous recovery from a production outage. No test listings were inserted into production.

This does not repair unavailable source endpoints or guarantee access through an explicit site block. The user's Webshare product type was not independently verified. The midnight and 9 AM Manila schedules remain configured.
