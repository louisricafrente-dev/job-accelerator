from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from urllib.parse import urlencode, urlsplit

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

from src.classifier import classify_experience_level, is_work_authorized_location
from src.connectors.base import BaseConnector
from src.models import Job


# Public boards with Philippine postings verified through the Posting API.
COMPANIES = (
    "SGS", "Sutherland", "Canva", "IQEQ", "BoschGroup", "WesternDigital",
    "TurnerTownsend", "EgisGroup", "Continental", "NielsenIQ", "DeliveryHero",
)
POSTINGS = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
PAGE_SIZE = 100
DETAIL_LIMIT = 12


class SmartRecruitersConnector(BaseConnector):
    platform = "SmartRecruiters"
    tier = 1
    is_feed = True
    window_days = 7

    def fetch(self, query="", location=""):
        self.last_error = ""
        self.coverage_warning = ""
        self.last_route = "DIRECT"
        start, _ = self.date_window()
        params = urlencode({"country": "ph", "limit": PAGE_SIZE,
                            "releasedAfter": start.isoformat(timespec="milliseconds")})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(self._company_jobs, COMPANIES, repeat(params)))
        self.last_raw_count = sum(raw_count or 0 for _, raw_count, _ in results)
        warnings = [warning for _, _, warning in results if warning]
        if all(raw_count is None for _, raw_count, _ in results):
            self.last_error = "; ".join(warnings)
        elif warnings:
            self.coverage_warning = "Coverage limited: " + "; ".join(warnings)
        return [job for jobs, _, _ in results for job in jobs]

    def _read_json(self, session, url):
        response = self._bounded_get(session, url, timeout=6, allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f"HTTP {response.status_code}")
        return response.json()

    def _company_jobs(self, company, params):
        base = POSTINGS.format(company=company)
        jobs = []
        raw_count = None
        warnings = []
        try:
            with requests.Session(trust_env=False) as session:
                page = self._read_json(session, f"{base}?{params}")
                rows = page["content"]
                if not isinstance(rows, list):
                    raise ValueError("invalid postings list")
                raw_count = len(rows)
                if page.get("totalFound", raw_count) > raw_count:
                    warnings.append("listing cap reached")
                matches = [
                    row for row in rows
                    if isinstance(row, dict) and self.accepts_date(row.get("releasedDate"))
                    and self.accepts_opportunity(row.get("name") or "", allow_va_training=False)
                ]
                if len(matches) > DETAIL_LIMIT:
                    warnings.append("detail cap reached")
                for row in matches[:DETAIL_LIMIT]:
                    try:
                        ident = str(row.get("id", ""))
                        if not ident.isascii() or not ident.isdecimal():
                            raise ValueError("invalid posting ID")
                        detail = self._read_json(session, f"{base}/{ident}")
                        job = self._job(detail)
                        if job:
                            jobs.append(job)
                    except (RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
                        warning = f"detail fetch failed ({error})"
                        if warning not in warnings:
                            warnings.append(warning)
        except (RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
            warnings.append(f"listing fetch failed ({error})")
        warning = f"{company}: " + ", ".join(warnings) if warnings else ""
        return jobs, raw_count, warning

    def _job(self, detail):
        title = detail.get("name") or ""
        published = detail.get("releasedDate")
        location = detail.get("location") or {}
        url = detail.get("postingUrl") or ""
        host = urlsplit(url)
        company = (detail.get("company") or {}).get("name")
        if (not title or not company or location.get("country", "").lower() != "ph"
                or not self.accepts_date(published)
                or host.scheme != "https" or host.netloc.lower() != "jobs.smartrecruiters.com"):
            return None
        place = location.get("fullLocation") or "Philippines"
        if location.get("remote"):
            place = f"{place} (Remote)"
        sections = (detail.get("jobAd") or {}).get("sections") or {}
        description = "\n".join(
            (sections.get(key) or {}).get("text") or ""
            for key in ("jobDescription", "qualifications", "additionalInformation")
        )
        job = Job(title, company, place, self.platform, self.tier, url,
                  date_posted=published, description=description)
        if (not is_work_authorized_location(job.location, job.title, job.platform, job.description)
                or not self.accepts_opportunity(job.title, job.description, allow_va_training=False)):
            return None
        job.role_category = self.job_role(job.title, job.description)
        job.experience_level = classify_experience_level(job.title, job.description)
        return job
