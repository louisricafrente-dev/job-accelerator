# Video Editor discovery

Video jobs use only OnlineJobs.ph, Freelancer, Indeed and JobStreet. Four dedicated checkpointed discovery streams reuse the existing source transports; stored jobs retain their original platform, so site filters and deduplication continue to work. Existing source queries, schedules, application states and non-video date rules are retained.

The video publication window is today plus the previous six Philippine calendar dates, excluding tomorrow and unknown dates. Other jobs retain today/yesterday. Freelancer receives exact from/to bounds and full_description=true; Indeed receives rounded source hours with a strict final calendar guard; JobStreet receives keyword searches with daterange=7; OLJ follows actual offset links until the verified date boundary. Source dates may represent updated/indexed dates rather than an employer's first publication.

Search terms: CapCut, short form video editor, gaming video editor, reels editor. Source-page cursors and the active video term are saved independently of the existing technology queries. Manual Sync, scheduled sync, local and cloud execution use the same factory and ingestion guard. Errors retain the committed cursor; blocked sources keep existing retry behavior. No extra recurring task is installed.

Only primary video-editor titles with a full accessible description, explicit CapCut/tool-choice compatibility, short-form/tutorial scope and basic editing signals can be stored. Advanced VFX/motion graphics, 3D, mandatory unsupported software, confirmed extra language/design/admin duties and explicit unverified required tenure are excluded. Optional tools and simple no-VFX briefs are supported. OLJ loads the job-description element; JobStreet reads public JobPosting structured data; Indeed and Freelancer provide full descriptions. Missing details are skipped with an explicit limited-coverage warning. This conservative rule set can miss suitable jobs and cannot guarantee subjective reference-style, workload or turnaround suitability; users must review those before applying.

Attention-check signals are logged and appended as a review notice on accepted descriptions. External instructions are never executed; applications and messages are outside discovery. The category helper reminds users to review workload and samples.

Video Editor is an exact stored category shared by feeds/counts/exports and excluded from the existing family predicates, including AI/data. No inventory migration or history deletion is necessary. Previously misclassified stored jobs are not automatically relabeled.

Validation: tests/test_video_editor.py covers window bounds, source allowlist, strict fit, optional software, source request parameters, details, pagination, both ingestion paths and Saved history. scripts/check_video_sources.py performs a bounded public direct-route check without production database/proxy configuration; it does not establish exhaustive site coverage.

UI choice: reuse the existing filter chip, specialty select and telemetry cards for continuity and keyboard behavior. No additional palette, font, layout framework or decorative elements were introduced.
