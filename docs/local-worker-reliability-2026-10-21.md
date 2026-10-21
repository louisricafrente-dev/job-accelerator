# Local worker reliability fixes

- Windows Task Scheduler launches pythonw.exe directly. Python owns its log at `%LOCALAPPDATA%/JobAccelerator/worker.log`, so normal scraper stderr cannot terminate a PowerShell pipeline.
- A process lock prevents duplicate workers on the PC. Startup clears only the dead worker's private SQLite execution lease after acquiring that lock.
- Local requests claim the same Turso execution lease used by cloud sync. Heartbeats renew it every 15 seconds; ownership expires after 90 seconds. Upload and completion APIs reject expired or replaced owners.
- Local harvesting reuses the existing durable batch checkpoints, saves every batch, and uploads changed listings before continuing. A restarted process resumes the saved search cycle. A 24-hour run ends partial with unfinished searches preserved.
- Upload acknowledgments track a content fingerprint per job. Salary, description, date, and source changes can be uploaded even when the local ID stays the same. Upload retries retain pending data and acknowledged counts.
- Offline requests display interrupted. Idle or completed local runs cannot override newer cloud results. Legitimate cloud queues remain active until completed or reported stalled.
- Cron requests require an admin session or CRON_SECRET; a caller-supplied x-vercel-cron header is insufficient.

Validation: 160 Python regression tests plus frontend, workflow, and settings checks passed. A real HTTP integration check using Remote OK and Remotive fetched 6 listings, uploaded 5 local records, merged them into 4 destination records, completed the request, released the shared lease, and left zero pending uploads. A hidden Python launch survived normal stderr and exited 0.

The live integration check used isolated databases. Production monitoring after deployment is separately required; passing the check does not mean every external job board is available or the user's full keyword matrix has already completed.
