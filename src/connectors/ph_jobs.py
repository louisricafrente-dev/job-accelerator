import json
import urllib.request
import urllib.parse
from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job, is_today_or_yesterday, normalize_date, scrape_date_window
from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity, is_work_authorized_location

import time
import random

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

class KalibrrConnector(BaseConnector):
    platform = "Kalibrr"
    tier = 1
    revision = 4
    is_feed = True
    checkpointed_feed = True
    PAGE_SIZE = 50

    def fetch(self, query="", location="Philippines"):
        from bs4 import BeautifulSoup
        self.last_error = ""
        self.last_fetch_mode = "newest-first date window"
        self.has_more = False
        self.coverage_warning = ""
        state = dict(getattr(self, "feed_state", {}))
        start, _ = scrape_date_window()
        window_start = start.date().isoformat()
        if state.get("window_start") != window_start:
            state = {"window_start": window_start}
        self.next_feed_state = state
        offset = state.get("offset", 0)
        try:
            params = urllib.parse.urlencode({"limit": self.PAGE_SIZE, "offset": offset,
                                             "sort_field": "activation_date", "sort_direction": "desc"})
            req = urllib.request.Request(f"https://www.kalibrr.com/api/job_board/search?{params}", headers=HEADERS)
            with self.open_url(req, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8"))
            items, total = data.get("jobs"), data.get("count")
            if not isinstance(items, list) or type(total) is not int or total < 0:
                raise RuntimeError("Invalid Kalibrr catalogue response")
            ids = [str(item.get("id") or item.get("code") or "") for item in items]
            fingerprint = ",".join(ids)
            if any(not ident for ident in ids):
                raise RuntimeError("Kalibrr returned a listing without a job ID")
            if offset and items and fingerprint == state.get("previous_page"):
                raise RuntimeError("Kalibrr repeated a catalogue page; progress retained")
            dates = [normalize_date(item.get("activation_date") or item.get("published") or item.get("created_at"))
                     for item in items]
            self.finish_page(state, ids, dates, offset + len(items) < total, ordered=True)
            if self.has_more and len(items) < self.PAGE_SIZE:
                raise RuntimeError("Kalibrr catalogue page is truncated; progress retained")
            jobs = []
            self.last_raw_count = len(items)
            for item, ident, date in zip(items, ids, dates):
                if not is_today_or_yesterday(date):
                    continue
                title = item.get("name", "")
                desc = BeautifulSoup(" ".join(filter(None, [item.get("description"), item.get("qualifications")])), "html.parser").get_text(" ", strip=True)
                address = (item.get("google_location") or {}).get("address_components") or {}
                loc = ", ".join(filter(None, [address.get("city"), address.get("country")])) or "Location unverified"
                if item.get("is_work_from_home"):
                    loc += " (Remote)"
                if not is_relevant_opportunity(title, desc, location=loc, platform=self.platform):
                    continue
                company = item.get("company_info") or item.get("company") or {}
                code = company.get("code") or item.get("company_code")
                if not code:
                    raise RuntimeError("Kalibrr returned a listing without a company code")
                salary = ""
                if item.get("salary_shown") and item.get("base_salary"):
                    salary = f"{item.get('salary_currency', '')} {item['base_salary']}"
                    if item.get("maximum_salary"):
                        salary += f" - {item['maximum_salary']}"
                    salary += f" / {item.get('salary_interval', '')}"
                jobs.append(Job(title=title, company=item.get("company_name") or company.get("name", ""),
                                location=loc, platform=self.platform, tier=self.tier,
                                job_url=f"https://www.kalibrr.com/c/{code}/jobs/{ident}", salary=salary,
                                role_category=classify_role(title, desc), experience_level=classify_experience_level(title, desc),
                                description=desc, date_posted=date))
            state.update(offset=offset + len(items) if self.has_more else 0,
                         previous_page=fingerprint if self.has_more else "", total=total,
                         pages_saved=offset // self.PAGE_SIZE + 1)
            if not self.has_more:
                state["last_completed"] = time.time()
            self.next_feed_state = state
            return jobs
        except Exception as exc:
            self.last_error = str(exc) or type(exc).__name__
            logger.error("[%s] fetch failed: %s", self.platform, self.last_error)
            return []

class BossjobConnector(BaseConnector):
    platform = "Bossjob"
    tier = 2
    revision = 4
    checkpointed_query = True

    def fetch(self, query: str = "developer", location: str = "Philippines") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        state = self.page_state(query)
        page = state.get("page", 1)
        try:
            params = urllib.parse.urlencode({"query": query, "size": 30, "country_id": 167,
                                             "sort": 1, "page": page, "source": "web"})
            url = f"https://bossjob.ph/bossjob-api-server/jobs/search?{params}"
            req = urllib.request.Request(url, headers={**HEADERS, "Accept": "application/json", "Role-Id": "1"})
            with self.open_url(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") != 0:
                    raise RuntimeError("Bossjob search failed: " + str(data.get("message", "Unknown error")))
                payload = data.get("data", {})
                items = payload.get("jobs", [])
                # Latest is ranked by refresh time, not original publication time.
                # Do not walk the historical catalogue or stop on an old page.
                more = page < 2 and payload.get("total_pages", page) > page
                self.finish_page(state, [str(item.get("id") or item.get("job_url") or "") for item in items],
                                 [item.get("published_at") for item in items], more)
                state["page"] = page + 1
                self.coverage_warning = "Coverage limited: Bossjob ranks refreshed posts; publication-date cutoff is unavailable (two recent pages per keyword)"
                for item in items:
                    title = item.get("job_title", "")
                    if not is_relevant_opportunity(title, ""):
                        continue
                    pub_date = (item.get("published_at") or "")[:10]
                    if not is_today_or_yesterday(pub_date):
                        continue
                    company = item.get("company_name", "")
                    link = urllib.parse.urljoin("https://bossjob.ph", ("/en" + item["job_url"]) if item.get("job_url", "").startswith("/job/") else item.get("job_url", ""))
                    if not item.get("job_url"):
                        continue
                    salary = "" if item.get("is_salary_hidden") else item.get("salary_range_value", "")
                    job_location = ", ".join(filter(None, [item.get("job_location"), item.get("job_country")]))
                    if item.get("is_remote_worldwide"):
                        job_location = "Remote Worldwide"
                    if not is_work_authorized_location(job_location, title, self.platform, ""):
                        continue
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=job_location,
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=pub_date
                    ))
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class JobStreetConnector(BaseConnector):
    platform = "JobStreet"
    tier = 1
    is_feed = False
    revision = 6
    query_group_size = 5
    MAX_PAGES = 3

    def _parse_items(self, items):
        jobs = []
        for item in items:
            job_id = str(item.get("id", "")).strip()
            if not job_id:
                continue
            href = f"https://ph.jobstreet.com/job/{job_id}"
            title = (item.get("title") or "").strip()
            bullets = item.get("bulletPoints") or []
            desc = " ".join(filter(None, [item.get("teaser", ""), " ".join(str(b) for b in bullets)]))
            if not title or not is_relevant_opportunity(title, desc):
                continue
            date_val = normalize_date(item.get("listingDate") or "")
            if not is_today_or_yesterday(date_val):
                continue
            comp = (item.get("advertiser") or {}).get("description") or "Company Confidential"
            locs = item.get("locations") or []
            loc = (locs[0].get("label") if locs and isinstance(locs[0], dict) else "") or "Philippines"
            arr = (item.get("workArrangements") or {}).get("displayText") or ""
            if arr and arr.lower() not in loc.lower():
                loc = f"{loc} ({arr})"
            sal = (item.get("salaryLabel") or "").strip()
            jobs.append(Job(
                title=title,
                company=comp,
                location=loc,
                platform=self.platform,
                tier=self.tier,
                job_url=href,
                salary=sal,
                role_category=classify_role(title, desc),
                experience_level=classify_experience_level(title, desc),
                description=desc,
                date_posted=date_val
            ))
        return jobs

    def fetch(self, query: str = "", location: str = "philippines", *, group_size=1) -> List[Job]:
        self.last_error = ""
        self.last_search_complete = False
        self.last_raw_count = 0
        jobs: List[Job] = []
        try:
            kw = query.strip() or "software developer"
            seen_urls = set()
            for page in range(1, self.MAX_PAGES + 1):
                params = urllib.parse.urlencode({
                    "siteKey": "PH-Main",
                    "keywords": kw,
                    "page": page,
                    "pageSize": 50,
                    "sortmode": "ListedDate",
                    "daterange": 2,
                })
                url = f"https://ph.jobstreet.com/api/jobsearch/v5/search?{params}"
                resp = self.get_url(url, impersonate="chrome120", timeout=12)
                if resp.status_code == 200:
                    payload = json.loads(resp.text)
                    if not isinstance(payload.get("data"), list):
                        raise RuntimeError("JobStreet returned an invalid search response")
                    items = payload.get("data", [])
                    self.last_raw_count += len(items)
                    page_urls = set()
                    for item in items:
                        job_id = str(item.get("id", "")).strip()
                        href = f"https://ph.jobstreet.com/job/{job_id}"
                        if not job_id or href in seen_urls:
                            continue
                        seen_urls.add(href)
                        page_urls.add(href)
                        jobs.extend(self._parse_items([item]))
                    total_count = payload.get("totalCount")
                    if len(items) < 50 or (isinstance(total_count, int) and len(seen_urls) >= total_count):
                        self.last_search_complete = True
                        break
                    if not page_urls:
                        break
                    if group_size > 1 and isinstance(total_count, int) and total_count > self.MAX_PAGES * 50:
                        break
                else:
                    raise RuntimeError(f"JobStreet HTTP {resp.status_code}")
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.error(f"[{self.platform}] fetch failed: {e}")
        if not self.last_error and not self.last_search_complete:
            self.coverage_warning = "Coverage limited: legacy JobStreet keyword search ended before provider exhaustion; use the paginated catalogue"
        return jobs


class JobStreetCatalogConnector(JobStreetConnector):
    is_feed = True
    revision = 8
    checkpointed_feed = True
    PAGE_SIZE = 100

    def fetch(self, query="", location="philippines"):
        self.last_fetch_mode = "catalogue"
        self.last_error = ""
        self.has_more = False
        state = dict(getattr(self, "feed_state", {}))
        self.next_feed_state = state
        page = state.get("page", 1)
        now = time.time()
        start, _ = scrape_date_window()
        window_start = start.date().isoformat()
        if state.get("days") != 2 or state.get("window_start") != window_start:
            page = 1
            state.update(page=1, previous_page="")
        state["days"] = 2
        state["window_start"] = window_start
        if page == 1:
            state.update(cycle_started=now, full=False)
        try:
            params = urllib.parse.urlencode({"siteKey": "PH-Main", "keywords": "", "page": page,
                                             "pageSize": self.PAGE_SIZE, "sortmode": "ListedDate", "daterange": state["days"]})
            response = self.get_url(f"https://ph.jobstreet.com/api/jobsearch/v5/search?{params}", impersonate="chrome120", timeout=12)
            if response.status_code != 200:
                raise RuntimeError(f"JobStreet HTTP {response.status_code}")
            payload = json.loads(response.text)
            items, total = payload.get("data"), payload.get("totalCount")
            if not isinstance(items, list) or type(total) is not int or total < 0:
                raise RuntimeError("Invalid JobStreet catalogue response")
            self.last_raw_count = len(items)
            ids = [str(item.get("id", "")) for item in items]
            fingerprint = ",".join(ids)
            if page > 1 and items and fingerprint == state.get("previous_page"):
                raise RuntimeError("JobStreet repeated a catalogue page; progress retained")
            self.has_more = page * self.PAGE_SIZE < total
            if self.has_more and len(items) < self.PAGE_SIZE:
                raise RuntimeError("JobStreet catalogue page is truncated; progress retained")
            jobs = self._parse_items(items)
            state.update(page=page + 1, previous_page=fingerprint, total=total, pages_saved=page)
            if not self.has_more:
                state.update(page=1, last_completed=state["cycle_started"], previous_page="")
                if state["full"]:
                    state["full_at"] = state["cycle_started"]
            self.next_feed_state = state
            return jobs
        except Exception as exc:
            self.last_error = str(exc) or type(exc).__name__
            return []


class OnlineJobsConnector(BaseConnector):
    platform = "OnlineJobs.ph"
    tier = 1
    revision = 2
    checkpointed_query = True

    def fetch(self, query: str = "developer", location: str = "philippines") -> List[Job]:
        from bs4 import BeautifulSoup
        self.last_error = ""
        jobs = []
        state = self.page_state(query)
        offset = state.get("offset", 0)
        try:
            params = urllib.parse.urlencode({"jobkeyword": query.strip(), "fullTime": "on",
                                             "partTime": "on", "freelance": "on"})
            path = f"/jobseekers/jobsearch/{offset}" if offset else "/jobseekers/jobsearch"
            with self.open_url(urllib.request.Request(f"https://www.onlinejobs.ph{path}?{params}", headers=HEADERS), timeout=12) as resp:
                soup = BeautifulSoup(resp.read().decode("utf-8"), "html.parser")
            cards = soup.select(".jobpost-cat-box")
            if not cards and not soup.select("form[action*='jobsearch'], input[name='jobkeyword']"):
                raise RuntimeError("OnlineJobs returned an unrecognized search page")
            links, dates = [], []
            for card in cards:
                a = card.find("a", href=lambda href: href and "/jobseekers/job/" in href)
                links.append(urllib.parse.urljoin("https://www.onlinejobs.ph", a["href"]) if a else "")
                date = card.select_one("p.fs-13")
                dates.append(date.get("data-temp") or date.get_text(strip=True).replace("Posted on ", "") if date else "")
            next_offset = offset + len(cards)
            has_next = any(f"/jobsearch/{next_offset}?" in a.get("href", "") or
                           a.get("href", "").rstrip("/").endswith(f"/jobsearch/{next_offset}")
                           for a in soup.select("a[href]"))
            self.finish_page(state, links, dates, has_next, ordered=True)
            state["offset"] = next_offset if self.has_more else 0
            for card, link, raw_date in zip(cards, links, dates):
                if not is_today_or_yesterday(raw_date):
                    continue
                h4 = card.select_one("h4")
                if not h4:
                    continue
                for badge in h4.select(".badge"):
                    badge.extract()
                title = h4.get_text(strip=True)
                desc = card.select_one(".desc")
                description = desc.get_text() if desc else ""
                if not title or not is_relevant_opportunity(title, description):
                    continue
                company = "Direct Client (OnlineJobs.ph)"
                for prefix in ("Company:", "About Us:", "Client:"):
                    if prefix in description:
                        value = description.split(prefix, 1)[1].strip().split("\n")[0].split(".")[0].strip()
                        if 2 < len(value) < 40:
                            company = value
                            break
                salary = card.select_one("dd.col")
                jobs.append(Job(title=title, company=company, location="Philippines (Remote / Direct Client)",
                                platform=self.platform, tier=self.tier, job_url=link,
                                salary=salary.get_text(strip=True) if salary else "",
                                role_category=classify_role(title), experience_level=classify_experience_level(title, description),
                                description=description, date_posted=raw_date))
        except Exception as exc:
            self.last_error = str(exc) or type(exc).__name__
            logger.error("[%s] fetch failed: %s", self.platform, self.last_error)
        return jobs
