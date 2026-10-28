import json
import urllib.request
import urllib.parse
from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job, is_within_15_days, is_within_14_days
from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity, is_work_authorized_location

import time
import random

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

class KalibrrConnector(BaseConnector):
    platform = "Kalibrr"
    tier = 1
    revision = 2
    is_feed = True
    checkpointed_feed = True
    PAGE_SIZE = 100

    def fetch(self, query="", location="Philippines"):
        from bs4 import BeautifulSoup
        self.last_error = ""
        self.last_fetch_mode = "catalogue"
        self.has_more = False
        state = dict(getattr(self, "feed_state", {}))
        self.next_feed_state = state
        offset = state.get("offset", 0)
        try:
            params = urllib.parse.urlencode({"limit": self.PAGE_SIZE, "offset": offset})
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
            self.has_more = offset + len(items) < total
            if self.has_more and len(items) < self.PAGE_SIZE:
                raise RuntimeError("Kalibrr catalogue page is truncated; progress retained")
            jobs = []
            for item, ident in zip(items, ids):
                title = item.get("name", "")
                desc = BeautifulSoup(" ".join(filter(None, [item.get("description"), item.get("qualifications")])), "html.parser").get_text(" ", strip=True)
                date = (item.get("published") or item.get("activation_date") or item.get("created_at") or "")[:10]
                address = (item.get("google_location") or {}).get("address_components") or {}
                loc = ", ".join(filter(None, [address.get("city"), address.get("country")])) or "Location unverified"
                if item.get("is_work_from_home"):
                    loc += " (Remote)"
                if not is_within_15_days(date) or not is_relevant_opportunity(title, desc, location=loc, platform=self.platform):
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
    revision = 2

    def fetch(self, query: str = "developer", location: str = "Philippines") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        try:
            params = urllib.parse.urlencode({"query": query, "size": 50, "country_id": 167})
            url = f"https://bossjob.ph/bossjob-api-server/jobs/search?{params}"
            req = urllib.request.Request(url, headers={**HEADERS, "Accept": "application/json", "Role-Id": "1"})
            with self.open_url(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") != 0:
                    raise RuntimeError("Bossjob search failed: " + str(data.get("message", "Unknown error")))
                for item in data.get("data", {}).get("jobs", []):
                    title = item.get("job_title", "")
                    if not is_relevant_opportunity(title, ""):
                        continue
                    pub_date = (item.get("published_at") or "")[:10]
                    if not is_within_15_days(pub_date):
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
    revision = 5
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
            date_val = (item.get("listingDate") or "")[:10]
            if not is_within_15_days(date_val):
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
                    "daterange": 14,
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
        return jobs


class JobStreetCatalogConnector(JobStreetConnector):
    is_feed = True
    revision = 6
    checkpointed_feed = True
    PAGE_SIZE = 100

    def fetch(self, query="", location="philippines"):
        import math
        self.last_fetch_mode = "catalogue"
        self.last_error = ""
        self.has_more = False
        state = dict(getattr(self, "feed_state", {}))
        self.next_feed_state = state
        page = state.get("page", 1)
        now = time.time()
        if page == 1:
            full = not state.get("full_at") or now - state["full_at"] >= 7 * 86400
            state.update(days=14 if full else min(14, max(1, math.ceil((max(0, now - state.get("last_completed", 0)) + 6 * 3600) / 86400))),
                         cycle_started=now, full=full)
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

    def fetch(self, query: str = "developer", location: str = "philippines") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        try:
            from bs4 import BeautifulSoup

            clean_q = urllib.parse.quote(query.strip())
            seen_urls = set()

            for page in range(1, 3):
                url = f"https://www.onlinejobs.ph/jobseekers/jobsearch?jobkeyword={clean_q}&fullTime=on&partTime=on&freelance=on&page={page}"
                req = urllib.request.Request(url, headers=HEADERS)
                try:
                    with self.open_url(req, timeout=12) as resp:
                        html = resp.read().decode("utf-8")
                        soup = BeautifulSoup(html, "html.parser")
                        cards = soup.select(".jobpost-cat-box")
                        if not cards:
                            break
                        page_valid_dates = 0
                        for c in cards:
                            h4 = c.select_one("h4")
                            if not h4:
                                continue
                            badge = h4.select_one(".badge")
                            if badge:
                                badge.extract()
                            title = h4.get_text(strip=True)
                            if not title:
                                continue

                            date_el = c.select_one("p.fs-13")
                            date_val = ""
                            if date_el:
                                date_val = date_el.get("data-temp", "")[:10]
                                if not date_val:
                                    raw_t = date_el.get_text(strip=True)
                                    if "Posted on " in raw_t:
                                        date_val = raw_t.replace("Posted on ", "")[:10]

                            if not is_within_15_days(date_val):
                                continue
                            page_valid_dates += 1

                            a = c.find("a", href=lambda h: h and "/jobseekers/job/" in h)
                            link = a["href"] if a else ""
                            if link and not link.startswith("http"):
                                link = "https://www.onlinejobs.ph" + link

                            if not link or link in seen_urls:
                                continue
                            seen_urls.add(link)

                            sal_el = c.select_one("dd.col")
                            salary = sal_el.get_text(strip=True) if sal_el else ""

                            company = "Direct Client (OnlineJobs.ph)"
                            desc_el = c.select_one(".desc")
                            desc_text = ""
                            if desc_el:
                                desc_text = desc_el.get_text()
                                for prefix in ("Company:", "About Us:", "Client:"):
                                    if prefix in desc_text:
                                        parts = desc_text.split(prefix)
                                        if len(parts) > 1:
                                            first_line = parts[1].strip().split("\n")[0].split(".")[0].strip()
                                            if 2 < len(first_line) < 40:
                                                company = first_line
                                                break

                            if not is_relevant_opportunity(title, desc_text):
                                continue

                            jobs.append(Job(
                                title=title,
                                company=company,
                                location="Philippines (Remote / Direct Client)",
                                platform=self.platform,
                                tier=self.tier,
                                job_url=link,
                                salary=salary,
                                role_category=classify_role(title, desc_text),
                                experience_level=classify_experience_level(title, desc_text),
                                description=desc_text,
                                date_posted=date_val
                            ))
                        if not page_valid_dates and cards:
                            # OnlineJobs listings are sorted newest first; if entire page is >14 days, stop paginating
                            break
                    # Polite anti-ban delay between pages
                    time.sleep(random.uniform(0.4, 0.7))
                except Exception as page_e:
                    self.last_error = str(page_e) or type(page_e).__name__
                    logger.warning(f"[{self.platform}] page {page} fetch notice: {page_e}")
                    break
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

