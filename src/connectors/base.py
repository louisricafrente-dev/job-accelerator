import logging
import io
import math
import re
import time
import urllib.request
import hashlib
import json
from email.utils import parsedate_to_datetime
from abc import ABC, abstractmethod
from typing import List
from datetime import date
from src.models import (
    DEFAULT_SCRAPE_WINDOW_DAYS,
    Job,
    is_within_scrape_window,
    normalize_date,
    scrape_date_window,
    scrape_request_hours,
    scrape_window_days,
)

logger = logging.getLogger("connectors")

# 7-day scrape window for newly integrated platforms until 2026-11-07 23:59:59 PHT (1 full week)
# After this cutoff timestamp, it automatically reverts to the dynamic daily window,
# matching the regular scraping cadence with zero manual intervention required.
NEW_PLATFORMS_7DAY_CUTOFF = 1794067199  # 2026-11-07 23:59:59+08:00


def default_new_platform_window(override_until: float = NEW_PLATFORMS_7DAY_CUTOFF) -> int:
    return 7 if time.time() <= override_until else DEFAULT_SCRAPE_WINDOW_DAYS


class NewPlatformConnectorMixin:
    """Mixin for newly added platforms running on a 7-day window for 1 week before reverting to dynamic."""
    _window_days_override = None
    _window_since = None

    @property
    def window_days(self) -> int:
        if self._window_days_override is not None:
            return self._window_days_override
        default_days = default_new_platform_window()
        if self._window_since is not None:
            return max(default_days, scrape_window_days(since=self._window_since))
        return default_days

    @window_days.setter
    def window_days(self, value: int):
        self._window_days_override = value


class BaseConnector(ABC):
    platform: str = "Unknown"
    tier: int = 1
    db_path = None
    query_group_size = 1
    coverage_warning = ""
    coverage_limit = ""
    MAX_RESPONSE_BYTES = 8 * 1024 * 1024
    _window_days_override = None
    _window_since = None
    min_window_days: int = DEFAULT_SCRAPE_WINDOW_DAYS
    video_editor_mode = False

    @property
    def window_days(self) -> int:
        if self._window_days_override is not None:
            return self._window_days_override
        floor = max(
            DEFAULT_SCRAPE_WINDOW_DAYS,
            int(getattr(self, "min_window_days", DEFAULT_SCRAPE_WINDOW_DAYS) or DEFAULT_SCRAPE_WINDOW_DAYS),
        )
        if self._window_since is not None:
            return max(floor, scrape_window_days(since=self._window_since))
        return floor

    @window_days.setter
    def window_days(self, value: int):
        self._window_days_override = value

    @property
    def window_since(self):
        return self._window_since

    @window_since.setter
    def window_since(self, value):
        self._window_since = value

    def _effective_since(self):
        if self._window_days_override is not None or not isinstance(getattr(type(self), "window_days", None), property):
            return None
        if isinstance(self, NewPlatformConnectorMixin):
            default_days = default_new_platform_window()
            if default_days > DEFAULT_SCRAPE_WINDOW_DAYS:
                if self._window_since is None or scrape_window_days(since=self._window_since) <= default_days:
                    return None
        floor = max(
            DEFAULT_SCRAPE_WINDOW_DAYS,
            int(getattr(self, "min_window_days", DEFAULT_SCRAPE_WINDOW_DAYS) or DEFAULT_SCRAPE_WINDOW_DAYS),
        )
        if floor > DEFAULT_SCRAPE_WINDOW_DAYS:
            if self._window_since is None or scrape_window_days(since=self._window_since) <= floor:
                return None
        return self._window_since

    def date_window(self, now=None):
        return scrape_date_window(now=now, days=self.window_days, since=self._effective_since())

    def request_hours(self, now=None) -> int:
        return scrape_request_hours(now=now, days=self.window_days, since=self._effective_since())

    def accepts_date(self, raw, ref_date=None):
        return is_within_scrape_window(raw, ref_date=ref_date, days=self.window_days, since=self._effective_since())

    def accepts_opportunity(self, title, description="", **kwargs):
        if self.video_editor_mode:
            from src.video_editor import is_video_candidate
            return is_video_candidate(title, description)
        from src.classifier import is_relevant_opportunity
        return is_relevant_opportunity(title, description, **kwargs)

    def job_role(self, title, description=""):
        if self.video_editor_mode:
            return "Video Editor"
        from src.classifier import classify_role
        return classify_role(title, description)

    def _bounded_get(self, session, url, **kwargs):
        body = bytearray()
        oversized = False

        def receive(chunk):
            nonlocal oversized
            if len(body) + len(chunk) > self.MAX_RESPONSE_BYTES:
                oversized = True
                raise ValueError("Source response exceeds safety size limit")
            body.extend(chunk)
            return len(chunk)

        try:
            response = session.get(url, content_callback=receive, **kwargs)
        finally:
            if oversized:
                raise ValueError("Source response exceeds safety size limit") from None
        response.content = bytes(body)
        return response

    def page_state(self, query=""):
        start, _ = self.date_window()
        window = start.date().isoformat()
        saved = getattr(self, "feed_state" if getattr(self, "is_feed", False) else "query_state", {})
        state = dict(saved) if isinstance(saved, dict) else {}
        if state.get("window_start") != window or state.get("query", "") != query:
            state = {"window_start": window, "query": query}
        self.has_more = False
        self.last_raw_count = 0
        self.coverage_warning = ""
        return state

    def finish_page(self, state, ids, dates, more, *, ordered=False):
        """Publish the next cursor only after validating this source page."""
        if any(not str(uid or "").strip() for uid in ids):
            raise ValueError("Source returned a row without an ID; progress retained")
        fingerprint = hashlib.sha256(json.dumps(ids, default=str).encode()).hexdigest()
        seen = list(state.get("seen_pages", []))
        if ids and fingerprint in seen:
            raise ValueError("Source repeated a page; progress retained")
        normalized = []
        for raw in dates:
            value = normalize_date(raw)
            try:
                date.fromisoformat(value)
            except ValueError:
                value = ""
            normalized.append(value)
        known = [date for date in normalized if date]
        if ordered and (known != sorted(known, reverse=True) or
                        (known and state.get("last_date") and known[0] > state["last_date"])):
            raise ValueError("Source publication order changed; date boundary cannot be verified")
        old = bool(normalized) and all(date and date < state["window_start"] for date in normalized)
        self.has_more = bool(more) and not (ordered and old)
        if self.has_more and not ids:
            raise ValueError("Source returned an empty continuation page; progress retained")
        if any(not date for date in normalized):
            self.coverage_warning = "Some source publication dates are missing; date coverage is unverified"
            if ordered and not known:
                self.has_more = False
        if ids:
            seen.append(fingerprint)
        state.update(seen_pages=seen, pages_saved=state.get("pages_saved", 0) + 1,
                     raw_seen=state.get("raw_seen", 0) + len(ids))
        if known:
            state["last_date"] = known[-1]
        self.last_raw_count = len(ids)
        setattr(self, "next_feed_state" if getattr(self, "is_feed", False) else "next_query_state", state)

    def fetch_group_step(self, queries):
        """Probe once; the scheduler saves results before scheduling individual coverage."""
        expression = " OR ".join(f"({query})" for query in queries)
        safe = len(expression) <= 250 and all(
            re.fullmatch(r"[\w .+#/-]+", query) and not re.search(r"\b(?:AND|OR|NOT)\b", query)
            for query in queries
        )
        self.last_group_incomplete = True
        self.last_fetch_mode = "individual searches queued"
        self.last_error = ""
        if not safe:
            return []
        self.bounded_group_probe = True
        try:
            jobs = self.fetch(query=expression, group_size=len(queries))
        finally:
            self.bounded_group_probe = False
        rejected = any(code in self.last_error.lower() for code in (
            "http 400", "http 414", "http 422", "invalid query", "unsupported boolean"))
        if rejected:
            self.last_error = ""
        elif self.last_error:
            self.last_group_incomplete = False
        elif getattr(self, "last_search_complete", False) and self.last_raw_count:
            self.last_group_incomplete = False
        self.last_fetch_mode = "group probe; individual searches queued" if self.last_group_incomplete else "grouped"
        return jobs

    def fetch_group(self, queries):
        expression = " OR ".join(f"({query})" for query in queries)
        safe = len(expression) <= 250 and all(
            re.fullmatch(r"[\w .+#/-]+", query) and not re.search(r"\b(?:AND|OR|NOT)\b", query)
            for query in queries
        )
        self.last_fetch_mode = "individual fallback"
        if safe:
            jobs = self.fetch(query=expression, group_size=len(queries))
            rejected = any(code in self.last_error.lower() for code in ("http 400", "http 414", "http 422", "invalid query", "unsupported boolean"))
            if (self.last_error and not rejected) or (not self.last_error and getattr(self, "last_search_complete", False) and self.last_raw_count):
                self.last_fetch_mode = "grouped"
                return jobs
        # A capped/empty OR search cannot establish coverage of every member.
        jobs = []
        for index, query in enumerate(queries):
            if index or safe:
                time.sleep(2)
            jobs.extend(self.fetch(query=query))
            if self.last_error:
                break
        return jobs

    def check_challenge(self, content):
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        if isinstance(content, str) and ("<html" in content.lower() or "<title" in content.lower()) and any(
            marker in content for marker in ("/cdn-cgi/challenge-platform", "cf-chl-")):
            if any(real in content for real in ("__NEXT_DATA__", "jobpost-cat-box", "itemListElement", "jobkeyword", "jobsearch")) and "<title>just a moment" not in content.lower():
                return
            raise RuntimeError("Cloudflare challenge; source requires verification")

    def request_with_fallback(self, send):
        from src.proxy_manager import request_routes, is_connection_error, mark_proxy_unavailable, redact_proxy_error, mark_proxy_quota_exhausted, DEFAULT_PROXIES
        routes = request_routes(self.db_path, platform=self.platform)
        if not routes:
            raise RuntimeError("No healthy proxy available; waiting for proxy cooldown")
        from src.proxy_manager import _unavailable_until
        for index, proxy in enumerate(routes):
            if proxy and _unavailable_until.get(proxy, 0) > time.time():
                continue
            route = ("WEBSHARE" if proxy in DEFAULT_PROXIES or (proxy and (urllib.parse.urlsplit(proxy).hostname or "").endswith("webshare.io")) else "PROXY") if proxy else "DIRECT"
            self.last_route = route
            try:
                return send(proxy)
            except Exception as exc:
                headers = getattr(exc, "headers", None) or getattr(getattr(exc, "response", None), "headers", {}) or {}
                retry_after = headers.get("Retry-After", "")
                try:
                    self.retry_after = max(0, float(retry_after))
                except (ValueError, TypeError):
                    try:
                        self.retry_after = max(0, parsedate_to_datetime(retry_after).timestamp() - time.time())
                    except (ValueError, TypeError, AttributeError, OverflowError):
                        pass
                if not math.isfinite(getattr(self, "retry_after", 0)):
                    self.retry_after = 0
                status = getattr(exc, "code", None) or getattr(getattr(exc, "response", None), "status_code", None)
                if proxy and (status in (402, 407) or any(m in str(exc).lower() for m in ("402 payment required", "response 402", "407 proxy authentication", "tunnel connection failed: 407", "response 407"))):
                    mark_proxy_quota_exhausted(self.db_path)
                    if None in routes[index + 1:]:
                        continue
                    self.retry_after = max(getattr(self, "retry_after", 0), 3600)
                    raise RuntimeError("Proxy quota exhausted (402); proxy pool paused for one hour") from None
                connection_failed = is_connection_error(exc)
                if proxy and connection_failed:
                    mark_proxy_unavailable(proxy)
                if not connection_failed or index == len(routes) - 1:
                    raise RuntimeError(redact_proxy_error(exc, self.db_path)) from None
                self.connection_retries = getattr(self, "connection_retries", 0) + 1
                logger.info("[%s] %s connection failed; using proxy fallback", self.platform, route)

    def open_url(self, request, timeout=12):
        def send(proxy):
            req_obj = request
            if hasattr(request, "full_url"):
                req_obj = urllib.request.Request(
                    request.full_url,
                    data=getattr(request, "data", None),
                    headers=dict(getattr(request, "headers", {})),
                    origin_req_host=getattr(request, "origin_req_host", None),
                    unverifiable=getattr(request, "unverifiable", False),
                    method=request.get_method() if hasattr(request, "get_method") else None
                )
            try:
                if proxy:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
                    response = opener.open(req_obj, timeout=timeout)
                else:
                    response = urllib.request.urlopen(req_obj, timeout=timeout)
                with response as opened:
                    body = opened.read(self.MAX_RESPONSE_BYTES + 1)
                    if len(body) > self.MAX_RESPONSE_BYTES:
                        raise ValueError("Source response exceeds safety size limit")
                    self.check_challenge(body)
                    return body
            except Exception as exc:
                err_body = exc.read(self.MAX_RESPONSE_BYTES + 1) if hasattr(exc, "read") else b""
                if "cloudflare challenge" not in str(exc).lower() and not any(
                    m in err_body for m in (b"/cdn-cgi/challenge-platform", b"cf-chl-")
                ):
                    raise
                url = request.full_url if hasattr(request, "full_url") else str(request)
                from curl_cffi import requests as cffi_requests
                with cffi_requests.Session(trust_env=False) as session:
                    resp = self._bounded_get(session, url, proxy=proxy or "", impersonate="chrome120", timeout=timeout)
                resp.raise_for_status()
                self.check_challenge(resp.text)
                return resp.content
        return io.BytesIO(self.request_with_fallback(send))

    def get_url(self, url, **kwargs):
        from curl_cffi import requests
        def send(proxy):
            with requests.Session(trust_env=False) as session:
                response = self._bounded_get(session, url, proxy=proxy or "", **kwargs)
            response.raise_for_status()
            self.check_challenge(response.text)
            return response
        return self.request_with_fallback(send)

    @abstractmethod
    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        pass
