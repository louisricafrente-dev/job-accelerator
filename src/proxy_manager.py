"""Proxy manager and hybrid router for Job Application Accelerator.

Supports rotating residential proxy pools, direct endpoints, and hybrid execution:
- Hybrid Mode (Default & Recommended):
  Uses direct requests with one proxy fallback for connection failures.
  LinkedIn uses its verified proxy route. Access blocks and rate limits are deferred.
- Always Active: Uses proxies on both cloud and local runs.
- Disabled: Direct connection everywhere.
"""
import os
import hashlib
import random
import time
from typing import List, Dict, Any, Optional
import urllib.request
import urllib.parse
import json
import logging
import re
import threading

logger = logging.getLogger("proxy_manager")

DEFAULT_PROXIES = []


def parse_proxy_line(line: str) -> Optional[str]:
    """Parse a single proxy line in either host:port:user:pass or URL format."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    
    if line.startswith("http://") or line.startswith("https://") or line.startswith("socks5://"):
        return line
    
    parts = line.split(":")
    if len(parts) == 4:
        # host:port:user:pass
        host, port, user, pwd = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    elif len(parts) == 2:
        # host:port (unauthenticated)
        return f"http://{parts[0]}:{parts[1]}"
    return None


def format_proxy_for_display(proxy_url: str) -> str:
    """Format proxy URL back into host:port:user:pass for easy editing."""
    proxy_url = proxy_url.strip()
    if "@" in proxy_url:
        scheme_rest = proxy_url.split("://", 1)[-1]
        user_pwd, host_port = scheme_rest.split("@", 1)
        if ":" in user_pwd and ":" in host_port:
            user, pwd = user_pwd.split(":", 1)
            host, port = host_port.split(":", 1)
            return f"{host}:{port}:{user}:{pwd}"
    return proxy_url


def parse_proxy_list(text: str) -> List[str]:
    """Parse multi-line proxy text into a list of normalized proxy URLs."""
    proxies = []
    for line in text.splitlines():
        parsed = parse_proxy_line(line)
        if parsed and parsed not in proxies:
            proxies.append(parsed)
    return proxies


def get_proxy_settings(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Read proxy list and mode from database settings, env vars, or defaults."""
    raw_list = ""
    mode = "hybrid"
    
    if db_path:
        try:
            from src.database import get_user_setting
            raw_list = get_user_setting(db_path, "proxy_list", "")
            mode = get_user_setting(db_path, "proxy_mode", "hybrid")
        except Exception:
            pass

    if not raw_list:
        env_proxy = os.environ.get("PROXY_URL") or os.environ.get("PROXY_LIST")
        if env_proxy:
            raw_list = env_proxy

    parsed = parse_proxy_list(raw_list) if raw_list else []
    if not parsed:
        parsed = list(DEFAULT_PROXIES)

    return {
        "proxies": parsed,
        "mode": mode.lower().strip() or "hybrid",
        "raw": raw_list or "\n".join(format_proxy_for_display(p) for p in DEFAULT_PROXIES)
    }


def is_proxy_active(db_path: Optional[str] = None) -> bool:
    """Determine whether proxies should be used for the current request context."""
    config = get_proxy_settings(db_path)
    mode = config.get("mode", "hybrid")
    proxies = config.get("proxies", [])
    
    if not proxies or mode == "disabled":
        return False
    
    if mode == "always":
        return True
    
    return bool(os.environ.get("FORCE_PROXY"))


_rr_index = 0
_proxy_lock = threading.Lock()
_unavailable_until = {}

def get_next_proxy(db_path: Optional[str] = None) -> Optional[str]:
    """Get the next proxy from the pool using round-robin rotation."""
    global _rr_index
    proxies = get_proxy_settings(db_path).get("proxies", [])
    if db_path:
        from src.database import get_user_setting
        key = "proxy_quota:" + hashlib.sha256("\n".join(proxies).encode()).hexdigest()
        if float(get_user_setting(db_path, key, "0")) > time.time():
            return None
    with _proxy_lock:
        for _ in proxies:
            proxy = proxies[_rr_index % len(proxies)]
            _rr_index += 1
            if _unavailable_until.get(proxy, 0) <= time.time():
                return proxy
    return None


def request_routes(db_path=None, platform=""):
    config = get_proxy_settings(db_path)
    if config["mode"] == "disabled":
        return [None]
    proxy_first = is_proxy_active(db_path) or platform == "LinkedIn"
    routes = [] if proxy_first else [None]
    for _ in range(2 if not routes else 1):
        proxy = get_next_proxy(db_path)
        if proxy and proxy not in routes:
            routes.append(proxy)
    if config["mode"] == "hybrid" and None not in routes:
        routes.append(None)
    return routes or ([None] if config["mode"] == "hybrid" else [])


def mark_proxy_quota_exhausted(db_path=None):
    proxies = get_proxy_settings(db_path)["proxies"]
    until = time.time() + 3600
    with _proxy_lock:
        for proxy in proxies:
            _unavailable_until[proxy] = until
    if db_path:
        from src.database import set_user_setting
        key = "proxy_quota:" + hashlib.sha256("\n".join(proxies).encode()).hexdigest()
        set_user_setting(db_path, key, str(until))


def mark_proxy_unavailable(proxy):
    with _proxy_lock:
        _unavailable_until[proxy] = time.time() + 300


def is_connection_error(error):
    message = str(error).lower()
    if any(term in message for term in ("403", "404", "407", "410", "429", "captcha", "cloudflare", "forbidden", "rate limit")):
        return False
    return isinstance(error, (TimeoutError, ConnectionError)) or any(term in message for term in (
        "timed out", "timeout", "connection reset", "connection refused", "connection aborted",
        "could not resolve", "name resolution", "getaddrinfo", "remote end closed", "failed to connect", "unexpected_eof_while_reading",
        "curl: (5)", "curl: (6)", "curl: (7)", "curl: (28)", "curl: (52)", "curl: (56)"))


def redact_proxy_error(error, db_path=None):
    message = str(error)
    for proxy in get_proxy_settings(db_path)["proxies"]:
        parsed = urllib.parse.urlsplit(proxy)
        message = message.replace(proxy, "[proxy]")
        for secret in (parsed.username, parsed.password):
            if secret:
                message = message.replace(secret, "[redacted]")
    return re.sub(r"https?://[^\s/]+@", "http://[redacted]@", message)


def get_proxy_pool(db_path: Optional[str] = None) -> List[str]:
    """Get all active proxies if proxying is enabled for this environment, else empty list."""
    if not is_proxy_active(db_path):
        return []
    config = get_proxy_settings(db_path)
    return config.get("proxies", [])


def apply_proxy_environment(db_path: Optional[str] = None) -> Optional[str]:
    """Apply the proxy configuration to environment variables for urllib/requests."""
    if is_proxy_active(db_path):
        proxy = get_next_proxy(db_path)
        if not proxy:
            for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                os.environ.pop(var, None)
            return None
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy
        return proxy
    else:
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(var, None)
        return None


def test_single_proxy(proxy_str: str, timeout: int = 5) -> Dict[str, Any]:
    """Test a single proxy line or URL and return its live latency, country, and status."""
    proxy_url = parse_proxy_line(proxy_str)
    if not proxy_url:
        return {"status": "error", "error": "Invalid proxy format"}
    
    start_time = time.monotonic()
    try:
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener = urllib.request.build_opener(handler)
        req = urllib.request.Request(
            "http://ip-api.com/json",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobAccelerator/1.0"}
        )
        with opener.open(req, timeout=timeout) as resp:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success":
                return {
                    "status": "ok",
                    "proxy": format_proxy_for_display(proxy_url),
                    "ip": data.get("query"),
                    "country": data.get("country"),
                    "country_code": data.get("countryCode"),
                    "city": data.get("city"),
                    "isp": data.get("isp"),
                    "latency_ms": elapsed_ms
                }
            return {
                "status": "error",
                "proxy": format_proxy_for_display(proxy_url),
                "error": data.get("message", "IP check failed"),
                "latency_ms": elapsed_ms
            }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return {
            "status": "error",
            "proxy": format_proxy_for_display(proxy_url),
            "error": str(exc) or type(exc).__name__,
            "latency_ms": elapsed_ms
        }
