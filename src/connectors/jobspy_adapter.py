import time
import json
import logging
import random
import re
from typing import List, Tuple
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
    revision = 7
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

    def _fetch_linkedin_job_detail(self, job_id: str) -> Tuple[str, str]:
        """Fetch full JD and native Seniority level from LinkedIn's guest jobPosting endpoint."""
        if not job_id or not self.db_path or hasattr(self.get_url, "_mock_name") or hasattr(type(self).get_url, "_mock_name"):
            return "", ""
        try:
            from bs4 import BeautifulSoup
            resp = self.get_url(
                f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}",
                impersonate="chrome120",
                timeout=8,
            )
            if resp.status_code != 200 or not resp.text:
                return "", ""
            soup = BeautifulSoup(resp.text, "html.parser")
            desc_el = soup.select_one(".show-more-less-html__markup, .description__text")
            desc = desc_el.get_text("\n", strip=True) if desc_el else ""
            raw_level = ""
            for item in soup.select(".description__job-criteria-item"):
                header = item.select_one(".description__job-criteria-subheader")
                val = item.select_one(".description__job-criteria-text")
                if header and val and "seniority" in header.get_text(strip=True).lower():
                    raw_level = val.get_text(" ", strip=True)
                    break
            return desc, raw_level
        except Exception:
            return "", ""

    def _enrich_glassdoor_descriptions(self, records: List[dict]) -> None:
        """Batch-fetch Glassdoor JobDetails via curl_cffi GraphQL when JobSpy returns blank JDs."""
        if not self.db_path or self.site_name != "glassdoor" or hasattr(self.get_url, "_mock_name") or hasattr(type(self).get_url, "_mock_name"):
            return
        targets = []
        for rec in records:
            raw_desc = rec.get("description")
            has_desc = raw_desc is not None and str(raw_desc).strip().lower() not in ("", "nan", "none", "null")
            if has_desc:
                continue
            m = re.search(r"[?&]jl=(\d+)", str(rec.get("job_url") or ""))
            if m:
                targets.append((m.group(1), rec))
        if not targets:
            return
        try:
            from bs4 import BeautifulSoup
            from curl_cffi import requests as cffi_requests
            sess = cffi_requests.Session(impersonate="chrome120")
            req_headers = {
                "origin": "https://www.glassdoor.com",
                "referer": "https://www.glassdoor.com/",
                "content-type": "application/json",
                "gd-csrf-token": "Ft6oHEWlRZrxDww95Cpazw:0pGUrkb2y3TyOpAIqF2vbPmUXoXVkD3oEGDVkvfeCerceQ5-n8mBg3BovySUIjmCPHCaW0H2nQVdqzbtsYqf4Q:wcqRqeegRUa9MVLJGyujVXB7vWFPjdaS1CtrrzJq-ok",
            }
            try:
                r0 = sess.get("https://www.glassdoor.com/Job/index.htm", timeout=8)
                m_tok = re.search(r'"token"\s*:\s*"([^"]+)"', r0.text or "")
                if m_tok:
                    req_headers["gd-csrf-token"] = m_tok.group(1)
            except Exception:
                pass
            details_tpl = (
                ' j%s: jobView(listingId: %s, contextHolder: {queryString: "q", pageTypeEnum: SERP})'
                ' { job { description } }'
            )
            for start in range(0, len(targets), 25):
                batch = targets[start:start + 25]
                aliases = "".join(details_tpl % (jid, jid) for jid, _ in batch)
                resp = sess.post(
                    "https://www.glassdoor.com/graph",
                    headers=req_headers,
                    json=[{"operationName": "JobDetails", "variables": {}, "query": f"query JobDetails {{{aliases}}}"}],
                    timeout=12,
                )
                if resp.status_code != 200:
                    continue
                payload = resp.json()
                data = (payload[0].get("data") if isinstance(payload, list) and payload else None) or {}
                by_id = dict(batch)
                for alias, view in data.items():
                    if not isinstance(view, dict):
                        continue
                    raw_html = ((view.get("job") or {}).get("description") or "").strip()
                    if not raw_html:
                        continue
                    clean_text = BeautifulSoup(raw_html, "html.parser").get_text("\n", strip=True)
                    jid = alias[1:] if alias.startswith("j") else alias
                    if jid in by_id and clean_text:
                        by_id[jid]["description"] = clean_text
        except Exception:
            pass

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
            detail_id = job_id
            if not detail_id:
                m_li = re.search(r"/(\d+)(?:\?|$)", job_url)
                detail_id = m_li.group(1) if m_li else ""
            li_desc, li_raw_level = self._fetch_linkedin_job_detail(detail_id)
            if li_desc:
                if not is_work_authorized_location(loc, title, self.platform, li_desc):
                    continue
                if not self.accepts_opportunity(title, li_desc, allow_va_training=True, location=loc, platform=self.platform):
                    continue
            jobs.append(Job(
                title=title,
                company=company,
                location=loc,
                platform=self.platform,
                tier=self.tier,
                job_url=job_url,
                salary="",
                role_category=self.job_role(title, li_desc),
                experience_level=classify_experience_level(title, li_desc, raw_level=li_raw_level, platform=self.platform),
                date_posted=date_str,
                description=li_desc,
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
            search_loc = location
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
            is_live_jobspy = bool(getattr(jobspy, "__file__", None)) and not hasattr(scrape_jobs, "_mock_name")
            if is_live_jobspy and self.site_name == "glassdoor":
                self._enrich_glassdoor_descriptions(rows)
            for row in rows:
                title = str(row.get("title", "")).strip()
                company = str(row.get("company", "")).strip()
                url = str(row.get("job_url", "")).strip()
                if not title or title.lower() in ("nan", "none", "null"):
                    continue
                if not url or url.lower() in ("nan", "none", "null"):
                    continue
                raw_description = row.get("description")
                description = "" if pd.isna(raw_description) else str(raw_description).strip()
                raw_lvl = row.get("job_level")
                raw_level = "" if pd.isna(raw_lvl) or str(raw_lvl).lower() in ("nan", "none", "") else str(raw_lvl).strip()
                if is_live_jobspy and self.site_name == "linkedin" and not description:
                    m_li = re.search(r"/(\d+)(?:\?|$)", url)
                    if m_li:
                        li_desc, li_raw = self._fetch_linkedin_job_detail(m_li.group(1))
                        if li_desc:
                            description = li_desc
                        if li_raw and not raw_level:
                            raw_level = li_raw
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
                raw_curr = row.get("currency")
                curr = "" if pd.isna(raw_curr) or str(raw_curr).lower() in ("nan", "none", "") else str(raw_curr).strip()
                raw_int = row.get("interval")
                interval = "" if pd.isna(raw_int) or str(raw_int).lower() in ("nan", "none", "") else str(raw_int).strip()
                sal_hint = f"{curr} {salary}/{interval}".strip(" /") if (salary and (curr or interval)) else salary
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
                    role_category=self.job_role(title, description),
                    experience_level=classify_experience_level(title, description, salary=sal_hint, raw_level=raw_level, platform=self.platform),
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
