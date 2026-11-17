import hashlib
import math
import urllib.parse
import re
import email.utils
from datetime import date, datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

MANILA = timezone(timedelta(hours=8))
DEFAULT_SCRAPE_WINDOW_DAYS = 1
MAX_SCRAPE_WINDOW_DAYS = 15
_VAGUE_DATE_TOKENS = ("recently", "recent", "posted recently", "posted recent", "new", "active today")


def coerce_manila_datetime(value: Any, ref_date: Optional[Any] = None) -> Optional[datetime]:
    """Convert a datetime, date, epoch timestamp, or date string into an aware Manila datetime."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.astimezone(MANILA) if value.tzinfo else value.replace(tzinfo=MANILA)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=MANILA)
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        val = value / 1000.0 if abs(value) >= 1e11 else float(value)
        try:
            return datetime.fromtimestamp(val, tz=MANILA)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        val = float(s)
        if len(s.split(".", 1)[0]) >= 12:
            val /= 1000.0
        try:
            return datetime.fromtimestamp(val, tz=MANILA)
        except (OverflowError, OSError, ValueError):
            return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return datetime.combine(date.fromisoformat(s), datetime.min.time(), tzinfo=MANILA)
        except ValueError:
            return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return parsed.astimezone(MANILA) if parsed.tzinfo else parsed.replace(tzinfo=MANILA)
        except ValueError:
            return None
    try:
        parsed_dt = email.utils.parsedate_to_datetime(s)
        if parsed_dt is not None:
            return parsed_dt.astimezone(MANILA) if parsed_dt.tzinfo else parsed_dt.replace(tzinfo=MANILA)
    except Exception:
        pass
    norm = normalize_date(s, ref_date=ref_date)
    if norm:
        try:
            return datetime.combine(date.fromisoformat(norm), datetime.min.time(), tzinfo=MANILA)
        except ValueError:
            return None
    return None


def parse_precise_scrape_instant(raw: Any, ref_date: Optional[Any] = None) -> Optional[datetime]:
    """Parse raw inputs that carry verified sub-day time precision into a Manila datetime."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is not None:
            return raw.astimezone(MANILA)
        return None
    if isinstance(raw, date):
        return None
    if isinstance(raw, (int, float)):
        if not math.isfinite(raw):
            return None
        val = raw / 1000.0 if abs(raw) >= 1e11 else float(raw)
        try:
            return datetime.fromtimestamp(val, tz=MANILA)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    now = coerce_manila_datetime(ref_date) if ref_date is not None else None
    if now is None:
        now = datetime.now(MANILA)
    s_lower = s.lower()
    if s_lower in ("just now", "moments ago", "just posted"):
        return now
    relative_time = re.fullmatch(r"(?:posted\s+)?(\d+)\s*(hours?|hrs?|h|minutes?|mins?)(?:\s+ago)?", s_lower)
    if relative_time:
        amount = int(relative_time.group(1))
        unit = relative_time.group(2)
        try:
            delta = timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount)
            return now - delta
        except OverflowError:
            return None
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        val = float(s)
        if len(s.split(".", 1)[0]) >= 12:
            val /= 1000.0
        try:
            return datetime.fromtimestamp(val, tz=MANILA)
        except (OverflowError, OSError, ValueError):
            return None
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", s):
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(MANILA)
        except ValueError:
            return None
    if ":" in s:
        try:
            parsed_dt = email.utils.parsedate_to_datetime(s)
            if parsed_dt is not None and parsed_dt.tzinfo is not None:
                return parsed_dt.astimezone(MANILA)
        except Exception:
            pass
    return None


def scrape_date_window(now: Optional[datetime] = None, days: Optional[int] = None, since: Optional[Any] = None):
    """Philippine publication window, with an exclusive upper bound."""
    now = now or datetime.now(MANILA)
    now = now.astimezone(MANILA) if now.tzinfo else now.replace(tzinfo=MANILA)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = midnight + timedelta(days=1)
    earliest = midnight - timedelta(days=MAX_SCRAPE_WINDOW_DAYS - 1)
    if since is not None:
        since_dt = coerce_manila_datetime(since, ref_date=now)
        if since_dt is not None:
            start = max(earliest, min(since_dt, now))
            return start, end
    effective_days = DEFAULT_SCRAPE_WINDOW_DAYS if days is None else max(1, min(int(days), MAX_SCRAPE_WINDOW_DAYS))
    return midnight - timedelta(days=effective_days - 1), end


def scrape_window_days(now: Optional[datetime] = None, days: Optional[int] = None, since: Optional[Any] = None) -> int:
    """Number of Manila calendar days spanned by the active scrape window."""
    now_dt = now or datetime.now(MANILA)
    now_dt = now_dt.astimezone(MANILA) if now_dt.tzinfo else now_dt.replace(tzinfo=MANILA)
    start, _ = scrape_date_window(now_dt, days=days, since=since)
    return max(1, min((now_dt.date() - start.date()).days + 1, MAX_SCRAPE_WINDOW_DAYS))


def scrape_request_hours(now: Optional[datetime] = None, days: Optional[int] = None, since: Optional[Any] = None) -> int:
    now_dt = now or datetime.now(MANILA)
    now_dt = now_dt.astimezone(MANILA) if now_dt.tzinfo else now_dt.replace(tzinfo=MANILA)
    start, _ = scrape_date_window(now_dt, days=days, since=since)
    raw_hours = math.ceil((now_dt - start).total_seconds() / 3600)
    if since is not None and coerce_manila_datetime(since, ref_date=now_dt) is not None:
        return max(1, min(raw_hours, MAX_SCRAPE_WINDOW_DAYS * 24))
    effective_days = DEFAULT_SCRAPE_WINDOW_DAYS if days is None else max(1, min(int(days), MAX_SCRAPE_WINDOW_DAYS))
    floor = 24 if effective_days >= 2 else 1
    return max(floor, min(raw_hours, MAX_SCRAPE_WINDOW_DAYS * 24))


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
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if parsed.tzinfo:
                return parsed.astimezone(MANILA).date().isoformat()
        except ValueError:
            return ""
        return s[:10]

    # Check relative dates ('3d ago', 'yesterday', 'today', '2w ago', 'recently', 'just posted', etc.)
    s_lower = s.lower()
    if isinstance(ref_date, datetime):
        now_utc = ref_date.astimezone(MANILA) if ref_date.tzinfo else ref_date.replace(tzinfo=MANILA)
    elif ref_date is not None:
        try:
            now_utc = datetime.combine(ref_date, datetime.min.time(), tzinfo=MANILA)
        except Exception:
            now_utc = datetime.now(MANILA)
    else:
        now_utc = datetime.now(MANILA)

    relative_time = re.fullmatch(r"(?:posted\s+)?(\d+)\s*(hours?|hrs?|h|minutes?|mins?)(?:\s+ago)?", s_lower)
    if relative_time:
        amount = int(relative_time.group(1))
        unit = relative_time.group(2)
        try:
            delta = timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount)
            return (now_utc - delta).strftime("%Y-%m-%d")
        except OverflowError:
            return ""
    if s_lower in ("today", "just now", "moments ago", "just posted", "posted today"):
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
            return datetime.fromtimestamp(val, tz=MANILA).strftime("%Y-%m-%d")
        except Exception:
            pass

    # Try RFC 2822
    try:
        parsed_dt = email.utils.parsedate_to_datetime(s)
        if parsed_dt:
            return (parsed_dt.astimezone(MANILA) if parsed_dt.tzinfo else parsed_dt).strftime("%Y-%m-%d")
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

def is_within_scrape_window(raw: Any, ref_date: Optional[Any] = None, *, days: Optional[int] = None, since: Optional[Any] = None) -> bool:
    """Return True if raw falls within the dynamic Philippine scrape window."""
    if raw is None or isinstance(raw, bool):
        return False
    if str(raw).strip().lower() in _VAGUE_DATE_TOKENS:
        return False
    now = coerce_manila_datetime(ref_date) if ref_date is not None else None
    if now is None:
        now = datetime.now(MANILA)
    start, end = scrape_date_window(now, days=days, since=since)
    instant = parse_precise_scrape_instant(raw, ref_date=now)
    if instant is not None:
        return start <= instant < end
    normalized = normalize_date(raw, ref_date=now)
    return bool(normalized) and start.date().isoformat() <= normalized < end.date().isoformat()


def is_today_or_yesterday(raw: Any, ref_date: Optional[Any] = None, *, days: Optional[int] = 2, since: Optional[Any] = None) -> bool:
    """Accept dates in the scrape window (defaults to today and yesterday for 2-day callers)."""
    return is_within_scrape_window(raw, ref_date=ref_date, days=days, since=since)


def resolve_scrape_since(db_path: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """Resolve the timestamp watermark from which the next scrape cycle should pull."""
    if not db_path:
        return None
    import json
    from src.database import get_user_setting
    now_ts = datetime.now(MANILA).timestamp() if now is None else float(now)
    now_dt = datetime.fromtimestamp(now_ts, MANILA)
    try:
        raw_last = get_user_setting(db_path, "last_completed_scrape_at", "")
    except Exception:
        return None
    if raw_last:
        try:
            ts = float(raw_last)
            if 0 < ts <= now_ts:
                return ts
        except (ValueError, TypeError):
            pass
    sync_ts = None
    try:
        raw_status = get_user_setting(db_path, "sync_status", "")
        if raw_status:
            status = json.loads(raw_status)
            if isinstance(status, dict):
                progress = status.get("progress")
                if not isinstance(progress, dict) or not progress:
                    last_res = status.get("last_result")
                    progress = last_res.get("progress") if isinstance(last_res, dict) else None
                has_more = progress.get("has_more") if isinstance(progress, dict) and progress else None
                raw_ts = status.get("last_successful_fetch") or status.get("last_sync_time") or 0
                if has_more is False and raw_ts:
                    cand = float(raw_ts)
                    if 0 < cand <= now_ts:
                        sync_ts = cand
    except Exception:
        sync_ts = None
    try:
        daily_day = (get_user_setting(db_path, "daily_scrape_day", "") or "").strip()
    except Exception:
        daily_day = ""
    if daily_day:
        try:
            daily_date = date.fromisoformat(daily_day)
            if sync_ts is not None and datetime.fromtimestamp(sync_ts, MANILA).date() == daily_date:
                return sync_ts
            if daily_date < now_dt.date():
                return datetime.combine(daily_date + timedelta(days=1), datetime.min.time(), tzinfo=MANILA).timestamp()
            if daily_date == now_dt.date():
                return sync_ts or datetime.combine(daily_date, datetime.min.time(), tzinfo=MANILA).timestamp()
        except ValueError:
            pass
    return sync_ts


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
        now_utc = datetime.now(MANILA).date()
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
        netloc = parsed.netloc.lower()
        query_params = urllib.parse.parse_qsl(parsed.query)

        # Indeed: isolate canonical jk query param
        if "indeed." in netloc and ("viewjob" in parsed.path or "rc/clk" in parsed.path):
            jk = next((v for k, v in query_params if k.lower() == "jk"), None)
            if jk:
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?jk={jk}"

        # LinkedIn: strip trailing tracking paths
        if "linkedin." in netloc and "/jobs/view/" in parsed.path:
            clean_path = parsed.path.rstrip("/")
            return f"{parsed.scheme}://{parsed.netloc}{clean_path}"

        # General tracking removal
        tracking_keys = {
            "ref", "source", "trk", "tracking", "fbclid", "gclid", "from",
            "refid", "trackingid", "vjs", "tk", "advn", "xkcb", "cmp", "spm"
        }
        filtered = [
            (k, v) for k, v in query_params
            if not k.lower().startswith("utm_") and k.lower() not in tracking_keys
        ]
        new_query = urllib.parse.urlencode(filtered)
        clean_path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, clean_path, parsed.params, new_query, ""))
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
        self.description = str(self.description or "").strip()
        if re.search(r"</?[a-zA-Z][^>]*>", self.description):
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.description, "html.parser")
            for element in soup(["script", "style"]):
                element.decompose()
            self.description = soup.get_text("\n", strip=True)
        self.title = str(self.title or "").strip()
        self.company = str(self.company or "").strip()
        self.location = str(self.location or "Philippines / Remote").strip()
        self.job_url = clean_url(str(self.job_url or "").strip())
        if not self.dedup_hash:
            self.dedup_hash = hash_job(self.platform, self.company, self.title, self.job_url)
        self._raw_date_posted = str(self.date_posted or "").strip() if self.date_posted is not None else ""
        if self.date_posted:
            self.date_posted = ("" if self._raw_date_posted.lower() in _VAGUE_DATE_TOKENS
                                else normalize_date(self.date_posted))
        self._normalized_date_posted = self.date_posted
