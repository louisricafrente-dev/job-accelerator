"""Bounded read-only smoke test: one page per video source, no database writes."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.connectors.video_editor import video_connectors
from src.video_editor import attention_check


def main():
    results = []
    for board in video_connectors():
        # Deliberately exclude production proxy/database/account configuration.
        board.source.request_with_fallback = lambda send: send(None)
        started = time.monotonic()
        try:
            rows = board.fetch()
            result = dict(source=board.source.platform, raw_count=board.last_raw_count,
                          accepted=len(rows), has_more=board.has_more, error=board.last_error,
                          warning=board.coverage_warning, rejected=board.last_filter_counts,
                          jobs=[dict(title=j.title, url=j.job_url, date=j.date_posted,
                                     attention_check=attention_check(j.description)) for j in rows])
        except Exception as exc:
            result = dict(source=board.source.platform, exception=str(exc))
        result['seconds'] = round(time.monotonic()-started, 2)
        results.append(result)
        print(json.dumps(result), flush=True)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(results, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
