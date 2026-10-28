import logging
import io
import math
import re
import time
import urllib.request
from email.utils import parsedate_to_datetime
from abc import ABC, abstractmethod
from typing import List
from src.models import Job

logger = logging.getLogger("connectors")

class BaseConnector(ABC):
    platform: str = "Unknown"
    tier: int = 1
    db_path = None
    query_group_size = 1

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
            if any(real in content for real in ("__NEXT_DATA__", "jobpost-cat-box", "itemListElement")) and "<title>just a moment" not in content.lower():
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
                if proxy and (status == 402 or "402 payment required" in str(exc).lower() or "response 402" in str(exc).lower()):
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
            try:
                if proxy:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
                    response = opener.open(request, timeout=timeout)
                else:
                    response = urllib.request.urlopen(request, timeout=timeout)
                with response as opened:
                    body = opened.read()
                    self.check_challenge(body)
                    return body
            except Exception as exc:
                err_body = exc.read() if hasattr(exc, "read") else b""
                if "cloudflare challenge" not in str(exc).lower() and not any(
                    m in err_body for m in (b"/cdn-cgi/challenge-platform", b"cf-chl-")
                ):
                    raise
                url = request.full_url if hasattr(request, "full_url") else str(request)
                from curl_cffi import requests as cffi_requests
                with cffi_requests.Session(trust_env=False) as session:
                    resp = session.get(url, proxy=proxy or "", impersonate="chrome120", timeout=timeout)
                resp.raise_for_status()
                self.check_challenge(resp.text)
                return resp.content
        return io.BytesIO(self.request_with_fallback(send))

    def get_url(self, url, **kwargs):
        from curl_cffi import requests
        def send(proxy):
            with requests.Session(trust_env=False) as session:
                response = session.get(url, proxy=proxy or "", **kwargs)
            response.raise_for_status()
            self.check_challenge(response.text)
            return response
        return self.request_with_fallback(send)

    @abstractmethod
    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        pass
