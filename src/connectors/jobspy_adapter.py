import time
import json
import logging
import random
from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job
from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity, is_work_authorized_location

class _JobSpyErrors(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class JobSpyAdapter(BaseConnector):
    revision = 6
    supports_group_steps = True
    checkpointed_query = True
    MAX_DIRECT_LINKEDIN_OFFSET = 30

    def __init__(self, platform_name: str, site_name: str, tier: int):
        self.platform = platform_name
        self.site_name = site_name
        self.tier = tier
        self.is_feed = (site_name == "zip_recruiter")
        self.checkpointed_feed = self.is_feed
        self.checkpointed_query = not self.is_feed
        self.query_group_size = 5 if site_name in ("linkedin", "indeed") else 1
        self.max_queries = None
        self.tail_group_size = 5 if site_name in ("linkedin", "glassdoor") else 1
        self.query_delay_seconds = (9.0, 13.0) if site_name == "linkedin" else ((5.0, 8.0) if site_name == "glassdoor" else None)
        self._linkedin_prefer_cffi = False
        self.last_error = ""

    def fetch_tail_group(self, queries: List[str]) -> List[Job]:
        """Fetch a single newest page for a tail boolean OR query batch."""
        expression = " OR ".join(f"({query})" for query in queries)
        self.query_state = {}
        jobs = self.fetch(query=expression, group_size=1)
        self.has_more = False
        self.last_group_incomplete = False
        self.last_fetch_mode = f"tail OR group ({len(queries)})"
        return jobs

    def _fetch_linkedin_guest_fallback(self, query: str, location: str, offset: int, wanted: int, state: dict):
        from bs4 import BeautifulSoup
        from urllib.parse import urlencode
        from src.models import normalize_date
        self.last_route = "DIRECT"
        time.sleep(random.uniform(1.5, 2.5))
        url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" + urlencode({
            "keywords": query,
            "location": location,
            "distance": 50,
            "f_TPR": f"r{int(self.request_hours()) * 3600}",
            "start": offset,
        })
        resp = self.get_url(url, impersonate="chrome120", timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"LinkedIn response status code {resp.status_code}")
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all(class_="base-search-card")
        raw_urls = []
        raw_dates = []
        jobs: List[Job] = []
        for card in cards:
            urn = str(card.get("data-entity-urn") or "").strip()
            job_id = urn.split(":")[-1].strip() if ":" in urn else ""
            link_el = card.find("a", class_="base-card__full-link", href=True) or card.find("a", href=True)
            job_url = f"https://www.linkedin.com/jobs/view/{job_id}" if job_id else (str(link_el["href"]).split("?")[0].strip() if link_el else "")
            title_el = card.find("h3", class_="base-search-card__title")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or not job_url:
                continue
            comp_el = card.find("h4", class_="base-search-card__subtitle")
            company = (comp_el.get_text(strip=True) if comp_el else "") or "Direct Employer"
            loc_el = card.find("span", class_="job-search-card__location")
            loc = (loc_el.get_text(strip=True) if loc_el else "") or location
            time_el = card.find("time")
            date_str = ((time_el.get("datetime") or time_el.get_text(strip=True) or "").strip() if time_el else "")
            raw_urls.append(job_url)
            raw_dates.append(date_str)
            if not is_work_authorized_location(loc, title, self.platform, ""):
                continue
            if not self.accepts_opportunity(title, "", allow_va_training=True, location=loc, platform=self.platform):
                continue
            if not self.accepts_date(date_str):
                continue
            jobs.append(Job(
                title=title,
                company=company,
                location=loc,
                platform=self.platform,
                tier=self.tier,
                job_url=job_url,
                salary="",
                role_category=self.job_role(title),
                experience_level=classify_experience_level(title, ""),
                date_posted=date_str,
                description="",
            ))
        norm_dates = [normalize_date(d) for d in raw_dates]
        all_old = bool(raw_dates) and all(d and d < state["window_start"] for d in norm_dates)
        empty_streak = (state.get("empty_streak", 0) + 1) if not jobs else 0
        self.last_raw_count = len(raw_urls)
        self.last_search_complete = len(raw_urls) < wanted
        more = len(raw_urls) >= wanted
        if self.db_path and (offset + len(raw_urls) >= self.MAX_DIRECT_LINKEDIN_OFFSET or empty_streak >= 2 or all_old):
            more = False
        if offset + len(raw_urls) >= 1000:
            more = False
            self.coverage_warning = "Coverage limited: search reached the 1000-result paging boundary"
        self.finish_page(state, raw_urls, raw_dates, more)
        state["offset"] = offset + wanted if self.has_more else 0
        state["empty_streak"] = empty_streak if self.has_more else 0
        return jobs, True

    def fetch(self, query: str = "software engineer", location: str = "Philippines", *, group_size=1) -> List[Job]:
        self.last_error = ""
        self.last_search_complete = False
        self.last_raw_count = 0
        jobs: List[Job] = []
        query = query.strip() or "software developer"
        state = self.page_state(query)
        offset = state.get("offset", 0)
        try:
            import importlib
            jobspy = importlib.import_module("jobspy")
            scrape_jobs = getattr(jobspy, "scrape_jobs")
            query = query.strip() or "software developer"
            search_loc = "Remote" if self.site_name == "glassdoor" and location.lower() == "philippines" else location
            country = "philippines" if self.site_name == "indeed" else ("usa" if self.site_name == "glassdoor" else None)
            wanted = 10 if self.site_name == "linkedin" else 35
            if group_size > 1:
                wanted = wanted + 1 if getattr(self, "bounded_group_probe", False) else wanted * group_size + 1
            if self.site_name == "linkedin" and self._linkedin_prefer_cffi and self.db_path and getattr(jobspy, "__file__", None):
                from src.proxy_manager import request_routes
                if request_routes(self.db_path, platform=self.platform) == [None]:
                    fallback_jobs, ok = self._fetch_linkedin_guest_fallback(query, search_loc, offset, wanted, state)
                    if ok:
                        self.last_error = ""
                        return fallback_jobs
            def send(proxy):
                errors_log = _JobSpyErrors()
                legacy_name = {"linkedin": "LinkedIn", "indeed": "Indeed", "glassdoor": "Glassdoor"}[self.site_name]
                scraper_loggers = [logging.getLogger("JobSpy:" + legacy_name),
                                   logging.getLogger("jobspy." + self.site_name.replace("_", ""))]
                for scraper_logger in scraper_loggers:
                    scraper_logger.addHandler(errors_log)
                real_jobspy = bool(getattr(jobspy, "__file__", None))
                if real_jobspy and self.site_name in ("linkedin", "glassdoor") and not proxy:
                    time.sleep(random.uniform(1.5, 2.5))
                elif real_jobspy and self.site_name == "indeed" and not proxy:
                    time.sleep(random.uniform(0.8, 1.5))
                try:
                    for attempt in range(2 if real_jobspy else 1):
                        errors_log.messages.clear()
                        frame = scrape_jobs(
                            site_name=[self.site_name],
                            search_term=query,
                            location=search_loc,
                            results_wanted=wanted,
                            offset=offset,
                            country_indeed=country,
                            hours_old=self.request_hours(),
                            proxies=[proxy] if proxy else None
                        )
                        if not (frame.empty and errors_log.messages and "eof occurred in violation of protocol" in "; ".join(errors_log.messages).lower()):
                            break
                        if attempt == 0:
                            time.sleep(1.5)
                finally:
                    for scraper_logger in scraper_loggers:
                        scraper_logger.removeHandler(errors_log)
                if errors_log.messages:
                    frame.attrs["errors"] = {self.site_name: "; ".join(errors_log.messages[-5:])}
                from src.proxy_manager import is_connection_error
                errors = getattr(frame, "attrs", {}).get("errors")
                if errors and frame.empty and (is_connection_error(errors) or "402" in str(errors) or "407" in str(errors)):
                    raise RuntimeError(str(errors))
                return frame
            df = self.request_with_fallback(send)
            errors = getattr(df, "attrs", {}).get("errors")
            self.last_raw_count = len(df)
            self.last_search_complete = not errors and len(df) < wanted
            if errors:
                from src.proxy_manager import redact_proxy_error
                self.last_error = redact_proxy_error(errors, self.db_path)
            if df.empty and self.site_name == "linkedin" and self.last_error and getattr(jobspy, "__file__", None):
                try:
                    fallback_jobs, ok = self._fetch_linkedin_guest_fallback(query, search_loc, offset, wanted, state)
                    if ok:
                        self._linkedin_prefer_cffi = True
                        self.last_error = ""
                        return fallback_jobs
                except Exception as li_exc:
                    self.last_error = str(li_exc) or self.last_error
            import pandas as pd
            rows = df.to_dict("records")
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
                if not self.accepts_opportunity(title, description, allow_va_training=True, location=loc, platform=self.platform):
                    continue
                if company.lower() in ("nan", "none", "null", ""):
                    company = "Direct Employer"
                raw_sal = row.get("min_amount")
                salary = "" if pd.isna(raw_sal) or str(raw_sal).lower() in ("nan", "none", "") else str(raw_sal).strip()
                raw_date = row.get("date_posted")
                date_str = "" if pd.isna(raw_date) or str(raw_date).lower() in ("nan", "none", "") else str(raw_date).strip()
                if not self.accepts_date(date_str):
                    continue
                jobs.append(Job(
                    title=title,
                    company=company,
                    location=loc,
                    platform=self.platform,
                    tier=self.tier,
                    job_url=url,
                    salary=salary,
                    role_category=self.job_role(title),
                    experience_level=classify_experience_level(title, description),
                    date_posted=date_str,
                    description=description
                ))
            empty_streak = (state.get("empty_streak", 0) + 1) if not jobs else 0
            more = not errors and len(df) >= wanted
            if self.db_path and self.site_name == "linkedin" and getattr(self, "last_route", "DIRECT") == "DIRECT":
                if offset + len(df) >= self.MAX_DIRECT_LINKEDIN_OFFSET or empty_streak >= 2:
                    more = False
            if offset + len(df) >= 1000:
                more = False
                self.coverage_warning = "Coverage limited: search reached the 1000-result paging boundary"
            self.finish_page(state, [str(row.get("job_url") or "") for row in rows],
                             [row.get("date_posted") for row in rows], more)
            state["offset"] = offset + wanted if self.has_more else 0
            state["empty_streak"] = empty_streak if self.has_more else 0
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs
