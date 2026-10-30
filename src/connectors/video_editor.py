"""Four checkpointed video searches using the existing source transports."""
import json
import urllib.request
from urllib.parse import urlsplit
from collections import Counter

from src.connectors.base import BaseConnector, logger
from src.video_editor import VIDEO_QUERIES, VIDEO_SOURCES, attention_check, collectable_job


class VideoEditorConnector(BaseConnector):
    is_feed = True
    checkpointed_feed = True
    revision = 1
    window_days = 7

    def __init__(self, source):
        if source.platform not in VIDEO_SOURCES:
            raise ValueError("Unsupported video source")
        self.source = source
        self.platform = source.platform + " (Video Editor)"
        self.tier = source.tier
        source.video_editor_mode = True
        source.window_days = 7

    def _description(self, job):
        from bs4 import BeautifulSoup
        if job.platform in ("Indeed", "Freelancer"):
            return job.description
        target = urlsplit(job.job_url)
        allowed_hosts = {"OnlineJobs.ph": {"www.onlinejobs.ph", "onlinejobs.ph"}, "JobStreet": {"ph.jobstreet.com"}}
        if target.scheme != "https" or target.hostname not in allowed_hosts.get(job.platform, set()):
            return ""
        with self.source.open_url(urllib.request.Request(job.job_url, headers={"User-Agent": "Mozilla/5.0"}), timeout=12) as response:
            soup = BeautifulSoup(response.read().decode("utf-8", errors="replace"), "html.parser")
        if job.platform == "OnlineJobs.ph":
            element = soup.select_one("#job-description")
            return element.get_text("\n", strip=True) if element else ""
        def find_posting(value):
            if isinstance(value, list):
                return next((found for item in value if (found := find_posting(item))), "")
            if isinstance(value, dict):
                if value.get("@type") == "JobPosting":
                    return value.get("description", "")
                return find_posting(value.get("@graph", []))
            return ""
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                found = find_posting(json.loads(script.string or script.get_text()))
                if found:
                    return BeautifulSoup(found, "html.parser").get_text("\n", strip=True)
            except (ValueError, TypeError):
                continue
        return ""

    def fetch(self, query="", location="Philippines"):
        from src.classifier import classify_experience_level
        from src.video_editor import video_fit
        state = self.page_state()
        index = state.get("query_index", 0)
        if type(index) is not int or not 0 <= index < len(VIDEO_QUERIES):
            state = {"window_start": state["window_start"]}
            index = 0
        term = VIDEO_QUERIES[index]
        source = self.source
        source.db_path = self.db_path
        source.query_state = state.get("source_state", {})
        source.feed_state = state.get("source_state", {})
        if source.platform == "JobStreet":
            source.search_query = term
        self.last_error = ""
        self.last_fetch_mode = f"basic CapCut / 7 days / {term}"
        jobs = source.fetch(query=term, location=location)
        self.last_error = source.last_error
        self.last_raw_count = getattr(source, "last_raw_count", 0)
        self.last_route = getattr(source, "last_route", "")
        self.connection_retries = getattr(source, "connection_retries", 0)
        self.retry_after = getattr(source, "retry_after", 0)
        self.coverage_warning = source.coverage_warning
        accepted, rejected = [], Counter()
        for job in jobs:
            try:
                description = self._description(job)
            except Exception:
                description = ""
            if not description:
                rejected["full description unavailable"] += 1
                continue
            job.description = description
            flagged = attention_check(description)
            if flagged:
                logger.warning("[%s] Employer attention check/prompt-injection signal: %s", self.platform, job.job_url)
            reason = video_fit(job.title, description)
            if reason or not collectable_job(job):
                rejected[reason or "date/location not eligible"] += 1
                continue
            job.experience_level = classify_experience_level(job.title, description)
            if flagged:
                job.description += "\n\nDiscovery review: Employer attention check detected. Review the original instructions before applying."
            accepted.append(job)
        if rejected.get("full description unavailable"):
            self.coverage_warning = (self.coverage_warning + "; " if self.coverage_warning else "") + "Video matches without accessible full descriptions were skipped; fit coverage is limited"
        self.last_filter_counts = dict(rejected)
        self.has_more = True
        self.next_feed_state = dict(state)
        if self.last_error:
            return accepted
        more = getattr(source, "has_more", False)
        self.next_feed_state["source_state"] = getattr(source, "next_feed_state" if getattr(source, "is_feed", False) else "next_query_state", {}) if more else {}
        self.next_feed_state["query_index"] = index if more else index + 1
        self.next_feed_state["days"] = 7
        self.next_feed_state["pages_saved"] = state.get("pages_saved", 0) + 1
        self.has_more = more or index + 1 < len(VIDEO_QUERIES)
        if not self.has_more:
            self.next_feed_state["query_index"] = 0
        return accepted


def video_connectors():
    from src.connectors.ph_jobs import OnlineJobsConnector, JobStreetCatalogConnector
    from src.connectors.remote_feed import FreelancerConnector
    from src.connectors.jobspy_adapter import JobSpyAdapter
    return [VideoEditorConnector(source) for source in (
        OnlineJobsConnector(), FreelancerConnector(), JobSpyAdapter("Indeed", "indeed", 1), JobStreetCatalogConnector())]
