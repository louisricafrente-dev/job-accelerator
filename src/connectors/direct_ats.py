from concurrent.futures import ThreadPoolExecutor
import html
import time
from urllib.parse import urlsplit

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

from src.classifier import classify_experience_level, is_work_authorized_location
from src.connectors.base import BaseConnector
from src.models import Job


class _DirectATSConnector(BaseConnector):
    """Shared concurrent JSON-feed helper for public company ATS boards."""

    tier = 1
    is_feed = True
    revision = 2
    min_window_days = 7
    COMPANIES = ()

    def _read_json(self, session, url):
        response = self._bounded_get(session, url, timeout=8, allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f"HTTP {response.status_code}")
        return response.json()

    def _company_jobs(self, company):
        raise NotImplementedError

    def _build_job(self, title, company, location, url, published, description, *, allow_va_training=False):
        job = Job(
            title=title,
            company=company,
            location=location,
            platform=self.platform,
            tier=self.tier,
            job_url=url,
            date_posted=published,
            description=description,
        )
        if (
            not is_work_authorized_location(job.location, job.title, self.platform, job.description)
            or not self.accepts_opportunity(job.title, job.description, allow_va_training=allow_va_training)
        ):
            return None
        job.role_category = self.job_role(job.title, job.description)
        job.experience_level = classify_experience_level(job.title, job.description)
        return job

    def _finalize_results(self, results):
        self.last_raw_count = sum(raw_count or 0 for _, raw_count, _ in results)
        warnings = [warning for _, _, warning in results if warning]
        if results and all(raw_count is None for _, raw_count, _ in results):
            self.last_error = "; ".join(warnings)
        elif warnings:
            self.coverage_warning = "Coverage limited: " + "; ".join(warnings)
        return [job for jobs, _, _ in results for job in jobs]

    def fetch(self, query="", location=""):
        self.last_error = ""
        self.coverage_warning = ""
        self.last_route = "DIRECT"
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(self._company_jobs, self.COMPANIES))
        return self._finalize_results(results)


class GreenhouseConnector(_DirectATSConnector):
    """Official Greenhouse public Job Board API for PH & worldwide-remote tech employers."""

    platform = "Greenhouse"
    COMPANIES = (
        "canonical", "binance", "okx", "bybit", "xendit", "coinbase", "agoda",
        "planetscale", "mozilla", "wikimedia", "netlify", "consensys", "gitlab", "invisible",
        "freshprints", "netskope", "rzr", "testlio", "cockroachlabs", "brave", "stripe", "cloudflare",
    )
    LIST_URL = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=false"
    DETAIL_URL = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"
    DETAIL_LIMIT = 12

    def _company_jobs(self, company):
        list_url = self.LIST_URL.format(company=company)
        jobs = []
        raw_count = None
        warnings = []
        try:
            with requests.Session(trust_env=False) as session:
                page = self._read_json(session, list_url)
                rows = page.get("jobs")
                if not isinstance(rows, list):
                    raise ValueError("invalid jobs list")
                raw_count = len(rows)
                matches = []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    published = str(row.get("first_published") or row.get("updated_at") or "").strip()
                    title = str(row.get("title") or "").strip()
                    loc = str(((row.get("location") or {}).get("name") or "")).strip()
                    if (
                        title
                        and self.accepts_date(published)
                        and is_work_authorized_location(loc, title, self.platform, "")
                        and self.accepts_opportunity(title, "", allow_va_training=False)
                    ):
                        matches.append((row, published, title, loc))
                if len(matches) > self.DETAIL_LIMIT:
                    warnings.append("detail cap reached")
                for row, published, title, loc in matches[:self.DETAIL_LIMIT]:
                    try:
                        ident = str(row.get("id", ""))
                        if not ident.isascii() or not ident.isdecimal():
                            raise ValueError("invalid posting ID")
                        detail = self._read_json(session, self.DETAIL_URL.format(company=company, job_id=ident))
                        url = str(detail.get("absolute_url") or row.get("absolute_url") or "").strip()
                        host = urlsplit(url)
                        if host.scheme != "https" or not host.netloc:
                            continue
                        comp = str(detail.get("company_name") or row.get("company_name") or company.title()).strip()
                        loc_final = str(((detail.get("location") or {}).get("name") or loc or "Remote")).strip()
                        det_title = str(detail.get("title") or title).strip()
                        det_pub = str(detail.get("first_published") or detail.get("updated_at") or published).strip()
                        desc = html.unescape(str(detail.get("content") or ""))
                        job = self._build_job(det_title, comp, loc_final, url, det_pub, desc)
                        if job:
                            jobs.append(job)
                    except (RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
                        msg = f"detail fetch failed ({error})"
                        if msg not in warnings:
                            warnings.append(msg)
        except (RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
            warnings.append(f"listing fetch failed ({error})")
        warning = f"{company}: " + ", ".join(warnings) if warnings else ""
        return jobs, raw_count, warning

class AshbyConnector(_DirectATSConnector):
    """Official Ashby public Job Board API for worldwide/APAC remote tech companies."""

    platform = "Ashby"
    COMPANIES = (
        "supabase", "elevenlabs", "phantom", "kit", "turnkey", "posthog", "oyster", "zapier",
        "multiplymii", "clickup", "railway", "baseten", "roboflow", "neon",
    )
    DISPLAY_NAMES = {
        "supabase": "Supabase",
        "elevenlabs": "ElevenLabs",
        "phantom": "Phantom",
        "kit": "Kit",
        "turnkey": "Turnkey",
        "posthog": "PostHog",
        "oyster": "Oyster",
        "zapier": "Zapier",
        "multiplymii": "MultiplyMii",
        "clickup": "ClickUp",
        "railway": "Railway",
        "baseten": "Baseten",
        "roboflow": "Roboflow",
        "neon": "Neon",
    }
    BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/{company}"

    def _company_jobs(self, company):
        board_url = self.BOARD_URL.format(company=company)
        jobs = []
        raw_count = None
        warnings = []
        try:
            with requests.Session(trust_env=False) as session:
                page = self._read_json(session, board_url)
                rows = page.get("jobs")
                if not isinstance(rows, list):
                    raise ValueError("invalid jobs list")
                raw_count = len(rows)
                comp = self.DISPLAY_NAMES.get(company, company.title())
                for row in rows:
                    if not isinstance(row, dict) or row.get("isListed") is False:
                        continue
                    title = str(row.get("title") or "").strip()
                    published = str(row.get("publishedAt") or "").strip()
                    url = str(row.get("jobUrl") or "").strip()
                    host = urlsplit(url)
                    if not title or not self.accepts_date(published) or host.scheme != "https" or not host.netloc:
                        continue
                    loc_parts = []
                    primary = str(row.get("location") or "").strip()
                    if primary:
                        loc_parts.append(primary)
                    for sec in (row.get("secondaryLocations") or []):
                        if isinstance(sec, dict):
                            sec_loc = str(sec.get("location") or "").strip()
                            if sec_loc and sec_loc not in loc_parts:
                                loc_parts.append(sec_loc)
                    loc = "; ".join(loc_parts)
                    is_remote = bool(row.get("isRemote")) or str(row.get("workplaceType") or "").lower() == "remote"
                    if is_remote and "remote" not in loc.lower():
                        loc = f"{loc} (Remote)" if loc else "Remote"
                    elif not loc:
                        loc = "Remote"
                    desc = str(row.get("descriptionPlain") or row.get("descriptionHtml") or "").strip()
                    job = self._build_job(title, comp, loc, url, published, desc)
                    if job:
                        jobs.append(job)
        except (RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
            warnings.append(f"listing fetch failed ({error})")
        warning = f"{company}: " + ", ".join(warnings) if warnings else ""
        return jobs, raw_count, warning

class WorkableConnector(_DirectATSConnector):
    """Official Workable public widget API for verified Philippine employers."""

    platform = "Workable"
    COMPANIES = ("isupport-worldwide", "angkas")
    DISPLAY_NAMES = {
        "isupport-worldwide": "iSupport Worldwide",
        "angkas": "Angkas",
    }
    WIDGET_URL = "https://apply.workable.com/api/v1/widget/accounts/{company}"

    def fetch(self, query="", location=""):
        self.last_error = ""
        self.coverage_warning = ""
        self.last_route = "DIRECT"
        results = []
        for idx, company in enumerate(self.COMPANIES):
            if idx and self.db_path:
                time.sleep(0.5)
            results.append(self._company_jobs(company))
        return self._finalize_results(results)

    def _company_jobs(self, company):
        widget_url = self.WIDGET_URL.format(company=company)
        jobs = []
        raw_count = None
        warnings = []
        try:
            with requests.Session(trust_env=False) as session:
                page = self._read_json(session, widget_url)
                rows = page.get("jobs")
                if not isinstance(rows, list):
                    raise ValueError("invalid jobs list")
                raw_count = len(rows)
                comp = self.DISPLAY_NAMES.get(company, company.title())
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    title = str(row.get("title") or "").strip()
                    published = str(row.get("published_on") or "").strip()
                    url = str(row.get("url") or row.get("shortlink") or "").strip()
                    host = urlsplit(url)
                    if not title or not self.accepts_date(published) or host.scheme != "https" or not host.netloc:
                        continue
                    loc_parts = [
                        str(part).strip()
                        for part in (row.get("city"), row.get("state"), row.get("country"))
                        if str(part or "").strip()
                    ]
                    loc = ", ".join(loc_parts) or "Philippines"
                    if row.get("telecommuting") and "remote" not in loc.lower():
                        loc = f"{loc} (Remote)"
                    desc = " | ".join(
                        str(part).strip()
                        for part in (row.get("department"), row.get("employment_type"), row.get("description"))
                        if str(part or "").strip()
                    )
                    job = self._build_job(title, comp, loc, url, published, desc, allow_va_training=False)
                    if job:
                        jobs.append(job)
        except (RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
            warnings.append(f"listing fetch failed ({error})")
        warning = f"{company}: " + ", ".join(warnings) if warnings else ""
        return jobs, raw_count, warning
