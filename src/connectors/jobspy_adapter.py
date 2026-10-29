import json
import logging
from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job, is_today_or_yesterday
from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity, is_work_authorized_location

class _JobSpyErrors(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class JobSpyAdapter(BaseConnector):
    revision = 4
    supports_group_steps = True

    def __init__(self, platform_name: str, site_name: str, tier: int):
        self.platform = platform_name
        self.site_name = site_name
        self.tier = tier
        self.is_feed = (site_name == "zip_recruiter")
        self.query_group_size = 5 if site_name in ("linkedin", "indeed") else 1
        self.last_error = ""

    def _fetch_ziprecruiter_ldjson(self) -> List[Job]:
        from bs4 import BeautifulSoup
        jobs: List[Job] = []
        seen = set()
        for url in (
            "https://www.ziprecruiter.com/Jobs/Remote-Software-Developer",
            "https://www.ziprecruiter.com/Jobs/Remote-Web-Developer",
        ):
            resp = self.get_url(url, impersonate="safari17_0", timeout=12)
            if resp.status_code == 200 and resp.text:
                soup = BeautifulSoup(resp.text, "html.parser")
                for sc in soup.find_all("script", {"type": "application/ld+json"}):
                    if not sc.string or "itemListElement" not in sc.string:
                        continue
                    data = json.loads(sc.string)
                    for item in data.get("itemListElement", []):
                        title = str(item.get("name") or "").strip()
                        job_url = str(item.get("url") or "").strip()
                        if not title or not job_url or job_url in seen or not is_relevant_opportunity(title, ""):
                            continue
                        seen.add(job_url)
                        comp = "Direct Employer"
                        if "/c/" in job_url and "/Job/" in job_url:
                            comp = job_url.split("/c/", 1)[1].split("/Job/", 1)[0].replace("-", " ").strip() or comp
                        jobs.append(Job(
                            title=title,
                            company=comp,
                            location=(item.get("jobLocation") if isinstance(item.get("jobLocation"), str) else "Remote (location unverified)"),
                            platform=self.platform,
                            tier=self.tier,
                            job_url=job_url,
                            salary="",
                            role_category=classify_role(title),
                            experience_level=classify_experience_level(title),
                            date_posted=item.get("datePosted", "")
                        ))
        return jobs

    def fetch(self, query: str = "software engineer", location: str = "Philippines", *, group_size=1) -> List[Job]:
        self.last_error = ""
        self.last_search_complete = False
        self.last_raw_count = 0
        jobs: List[Job] = []
        try:
            import importlib
            jobspy = importlib.import_module("jobspy")
            if self.site_name == "zip_recruiter" and getattr(jobspy, "__file__", None):
                return self._fetch_ziprecruiter_ldjson()
            scrape_jobs = getattr(jobspy, "scrape_jobs")
            search_loc = "Remote" if self.site_name == "glassdoor" and location.lower() == "philippines" else location
            country = "philippines" if self.site_name == "indeed" else ("usa" if self.site_name == "glassdoor" else None)
            wanted = 15 if self.site_name == "linkedin" else 35
            if group_size > 1:
                wanted = wanted + 1 if getattr(self, "bounded_group_probe", False) else wanted * group_size + 1
            def send(proxy):
                errors_log = _JobSpyErrors()
                scraper_logger = logging.getLogger("JobSpy:" + self.platform)
                scraper_logger.addHandler(errors_log)
                try:
                    frame = scrape_jobs(
                        site_name=[self.site_name],
                        search_term=query,
                        location=search_loc,
                        results_wanted=wanted,
                        country_indeed=country,
                        hours_old=48,
                        proxies=[proxy] if proxy else None
                    )
                finally:
                    scraper_logger.removeHandler(errors_log)
                if errors_log.messages:
                    frame.attrs["errors"] = {self.site_name: "; ".join(errors_log.messages[-5:])}
                from src.proxy_manager import is_connection_error
                errors = getattr(frame, "attrs", {}).get("errors")
                if errors and frame.empty and (is_connection_error(errors) or "402" in str(errors)):
                    raise RuntimeError(str(errors))
                return frame
            df = self.request_with_fallback(send)
            errors = getattr(df, "attrs", {}).get("errors")
            self.last_raw_count = len(df)
            self.last_search_complete = not errors and len(df) < wanted
            if errors and (df.empty or group_size > 1):
                from src.proxy_manager import redact_proxy_error
                self.last_error = redact_proxy_error(errors, self.db_path)
            if df.empty and self.site_name == "zip_recruiter" and getattr(jobspy, "__file__", None):
                try:
                    fallback_jobs = self._fetch_ziprecruiter_ldjson()
                    if fallback_jobs:
                        self.last_error = ""
                        return fallback_jobs
                except Exception as zr_exc:
                    self.last_error = str(zr_exc) or self.last_error
            import pandas as pd
            for _, row in df.iterrows():
                title = str(row.get("title", "")).strip()
                company = str(row.get("company", "")).strip()
                url = str(row.get("job_url", "")).strip()
                if not title or title.lower() in ("nan", "none", "null"):
                    continue
                if not url or url.lower() in ("nan", "none", "null"):
                    continue
                raw_description = row.get("description")
                description = "" if pd.isna(raw_description) else str(raw_description).strip()
                raw_loc = row.get("location")
                loc = search_loc if pd.isna(raw_loc) or str(raw_loc).lower() in ("nan", "none", "") else str(raw_loc).strip()
                if not is_work_authorized_location(loc, title, self.platform, description):
                    continue
                if not is_relevant_opportunity(title, description, allow_va_training=True, location=loc, platform=self.platform):
                    continue
                if company.lower() in ("nan", "none", "null", ""):
                    company = "Direct Employer"
                raw_sal = row.get("min_amount")
                salary = "" if pd.isna(raw_sal) or str(raw_sal).lower() in ("nan", "none", "") else str(raw_sal).strip()
                raw_date = row.get("date_posted")
                date_str = "" if pd.isna(raw_date) or str(raw_date).lower() in ("nan", "none", "") else str(raw_date).strip()
                if not is_today_or_yesterday(date_str):
                    continue
                jobs.append(Job(
                    title=title,
                    company=company,
                    location=loc,
                    platform=self.platform,
                    tier=self.tier,
                    job_url=url,
                    salary=salary,
                    role_category=classify_role(title),
                    experience_level=classify_experience_level(title, description),
                    date_posted=date_str,
                    description=description
                ))
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs
