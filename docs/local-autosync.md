# Local auto-sync and Gmail alerts

The local dashboard starts a scraper in the background when the app launches. It runs one sync immediately, then repeats every six hours while the dashboard process stays open. Use the Auto sync checkbox in the header to pause or resume future cycles. Manual sync remains available.

When a cycle adds new jobs, the app sends a digest to `michael18ricafrente@gmail.com`. Gmail SMTP credentials are read from the project `.env` file (`SMTP_USER` and `SMTP_PASSWORD`, or `GMAIL_APP_PASSWORD`). Keep that file private. The email links back to `http://localhost:8000`, so open it on the same computer where the dashboard is running.

Start the app with `START_JOB_ACCELERATOR.bat`. Closing the dashboard process stops local scraping; the next launch starts a fresh cycle. This runs against `data/jobs.db` and does not depend on GitHub Actions or Vercel.
