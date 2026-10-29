# Scrape publication-date window

Automatic, manual, local and cloud scraping accept only today and yesterday in Asia/Manila. This is a calendar-date rule, not a rolling 48-hour retention rule. Existing stored jobs and Pipeline history are preserved.

JobSpy requests at most 48 hours and then applies the calendar-date filter; JobStreet requests two days on every run, including resumed catalogue pages. The previous weekly 14-day refresh is removed. Other feeds are filtered before ingestion even when their provider cannot restrict the request itself. Stale, future and unknown dates are excluded. Vague labels such as "recently" do not establish a publication date.

ISO timestamps, RFC dates and epoch timestamps are converted to Philippine dates; date-only source values retain the date supplied by the jobsite. Both normal aggregation and checkpointed batch ingestion enforce the same policy. Deduplication remains enabled.

Validation: tests/test_today_yesterday.py covers Philippine midnight, UTC conversion, 48-hour overfetch, both ingestion paths, history preservation, and resuming an old JobStreet window.
