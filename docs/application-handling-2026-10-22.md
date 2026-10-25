# Application handling (2026-10-22)

Saved jobs begin without an application label. Pipeline defaults to Applied by me / human, including existing Pipeline entries. Labels are separate from recruiter stages.

Authenticated POST /api/jobs/<id>/status accepts application_handling:
- needs_human: Needs human verification; keeps the current tab. Send notes with the specific blocker.
- applied_ai: Applied by AI; automatically changes status to applied and records applied_at. Use only after confirmed submission.
- applied_human: Applied by me / human; automatically changes status to applied.
- empty string: clears the explicit label. Pipeline still displays its human default.

Marking applied without an explicit label defaults to human (preserving an existing applied_ai attribution). Returning an applied job to Saved/Inbox clears its applied attribution. Sync preserves the field; pending browser saves replay it after connection recovery. Old applications are not retrospectively classified as AI submissions.

Validation: 25 database tests plus two API tests; frontend, workflow, and application handling Node regressions.
