import logging
import io
import math
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

    def check_challenge(self, content):
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        if isinstance(content, str) and ("<html" in content.lower() or "<title" in content.lower()) and any(
            marker in content for marker in ("/cdn-cgi/challenge-platform", "cf-chl-")):
            raise RuntimeError("Cloudflare challenge; source requires verification")

    def request_with_fallback(self, send):
        from src.proxy_manager import request_routes, is_connection_error, mark_proxy_unavailable, redact_proxy_error, DEFAULT_PROXIES
        routes = request_routes(self.db_path)
        if not routes:
            raise RuntimeError("No healthy proxy available; waiting for proxy cooldown")
        for index, proxy in enumerate(routes):
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
                connection_failed = is_connection_error(exc)
                if proxy and connection_failed:
                    mark_proxy_unavailable(proxy)
                if not connection_failed or index == len(routes) - 1:
                    raise RuntimeError(redact_proxy_error(exc, self.db_path)) from None
                self.connection_retries = getattr(self, "connection_retries", 0) + 1
                logger.info("[%s] %s connection failed; using proxy fallback", self.platform, route)

    def open_url(self, request, timeout=12):
        def send(proxy):
            if proxy:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
                response = opener.open(request, timeout=timeout)
            else:
                response = urllib.request.urlopen(request, timeout=timeout)
            with response as opened:
                body = opened.read()
                self.check_challenge(body)
                return body
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
