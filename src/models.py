import hashlib
import urllib.parse
import re
import email.utils
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

def normalize_date(raw: Any, ref_date: Optional[Any] = None) -> str:
    """Normalize raw date strings/timestamps into ISO 'YYYY-MM-DD'.
    Handles:
      - 'YYYY-MM-DD' and ISO 8601 strings
      - Relative date expressions ('today', 'yesterday', '4d ago', '2 weeks ago', '5 hours ago')
      - RFC 2822 (e.g. 'Mon, 28 Sep 2026', '28 Sep 2026 12:00:00 GMT')
      - Epoch timestamps in seconds or milliseconds
      - Common human date patterns ('Sep 28, 2026', '28 Sep 2026')
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""

    # Check if already ISO format (YYYY-MM-DD...)
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]

    # Check relative dates ('3d ago', 'yesterday', 'today', '2w ago', 'recently', 'just posted', etc.)
    s_lower = s.lower()
    if isinstance(ref_date, datetime):
        now_utc = ref_date.astimezone(timezone.utc) if ref_date.tzinfo else ref_date.replace(tzinfo=timezone.utc)
    elif ref_date is not None:
        try:
            now_utc = datetime.combine(ref_date, datetime.min.time(), tzinfo=timezone.utc)
        except Exception:
            now_utc = datetime.now(timezone.utc)
    else:
        now_utc = datetime.now(timezone.utc)

    # Detect terms containing 'recently', 'recent', 'just posted', 'today', etc.
    if any(k in s_lower for k in ("today", "just now", "moments ago", "recently", "recent", "just posted", "new", "posted today", "active today")) or "hour" in s_lower or "minute" in s_lower or re.match(r"^\d+\s*h(?:r|ours?)?(\s*ago)?$", s_lower):
        return now_utc.strftime("%Y-%m-%d")
    if "yesterday" in s_lower:
        return (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")
    m_days = re.search(r"(\d+)\s*(?:d|day|days)\b", s_lower)
    if m_days:
        return (now_utc - timedelta(days=int(m_days.group(1)))).strftime("%Y-%m-%d")
    m_weeks = re.search(r"(\d+)\s*(?:w|week|weeks)\b", s_lower)
    if m_weeks:
        return (now_utc - timedelta(days=int(m_weeks.group(1)) * 7)).strftime("%Y-%m-%d")
    m_months = re.search(r"(\d+)\s*(?:m|month|months)\b", s_lower)
    if m_months:
        return (now_utc - timedelta(days=int(m_months.group(1)) * 30)).strftime("%Y-%m-%d")

    # Check if numeric epoch timestamp
    if s.isdigit():
        val = int(s)
        if len(s) >= 12:
            val = val // 1000
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pass

    # Try RFC 2822
    try:
        parsed_dt = email.utils.parsedate_to_datetime(s)
        if parsed_dt:
            return parsed_dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Try common string formats
    for fmt in (
        "%a, %d %b %Y",
        "%d %b %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y.%m.%d",
    ):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue

    return ""

def is_within_15_days(raw_or_norm: Any, max_days: int = 15, ref_date: Optional[Any] = None) -> bool:
    """Returns True if raw_or_norm represents a date between (ref_date - max_days) and (ref_date + 1 day).
    Empty, missing, or unparseable dates return False.
    """
    if not raw_or_norm:
        return False
    norm = normalize_date(raw_or_norm, ref_date=ref_date)
    if not norm:
        return False
    try:
        target = datetime.strptime(norm, "%Y-%m-%d").date()
    except Exception:
        return False

    if ref_date is None:
        now_utc = datetime.now(timezone.utc).date()
    elif isinstance(ref_date, datetime):
        now_utc = ref_date.date()
    else:
        now_utc = ref_date

    cutoff = now_utc - timedelta(days=max_days)
    future_limit = now_utc + timedelta(days=1)
    return cutoff <= target <= future_limit

def is_within_14_days(raw_or_norm: Any, max_days: int = 14, ref_date: Optional[Any] = None) -> bool:
    """Legacy helper; delegates to is_within_15_days with specified max_days (defaults to 14)."""
    return is_within_15_days(raw_or_norm, max_days=max_days, ref_date=ref_date)

def clean_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(str(url).strip())
        query_params = urllib.parse.parse_qsl(parsed.query)
        filtered = [
            (k, v) for k, v in query_params
            if not k.lower().startswith("utm_") and k.lower() not in ("ref", "source", "trk", "tracking", "fbclid")
        ]
        new_query = urllib.parse.urlencode(filtered)
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))
    except Exception:
        return str(url).strip()

def hash_job(platform: str, company: str, title: str, url: str) -> str:
    p = (platform or "").strip().lower()
    c = (company or "").strip().lower()
    t = (title or "").strip().lower()
    cleaned = clean_url(url or "")
    key = f"{p}|{c}|{t}|{cleaned.lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

@dataclass
class Job:
    title: str
    company: str
    location: str
    platform: str
    tier: int
    job_url: str
    salary: str = ""
    role_category: str = "Web/Software Dev"
    experience_level: str = "Unspecified"
    date_posted: str = ""
    status: str = "new"
    notes: str = ""
    description: str = ""
    dedup_hash: Optional[str] = None
    sources: Optional[List[Dict[str, str]]] = None

    def __post_init__(self):
        self.title = str(self.title or "").strip()
        self.company = str(self.company or "").strip()
        self.location = str(self.location or "Philippines / Remote").strip()
        self.job_url = str(self.job_url or "").strip()
        if not self.dedup_hash:
            self.dedup_hash = hash_job(self.platform, self.company, self.title, self.job_url)
        if self.date_posted:
            self.date_posted = normalize_date(self.date_posted)
