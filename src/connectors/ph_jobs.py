import re
import json
import urllib.request
import urllib.parse
from typing import List
from src.connectors.base import BaseConnector, NewPlatformConnectorMixin, logger
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
    revision = 5
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
                for item in items:
                    title = item.get("job_title", "")
                    if not is_relevant_opportunity(title, ""):
                        continue
                    pub_date = normalize_date(item.get("published_at"))
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
                seen = set(state.get("useful_urls", []))
                useful = {job.job_url for job in jobs} - seen
                state["useful_urls"] = sorted(seen | useful)
                state["empty_streak"] = 0 if useful else state.get("empty_streak", 0) + 1
                # Refreshed ranking mixes old and new publication dates.
                more = bool(items) and payload.get("total_pages", page) > page
                reason = "provider end"
                if state["empty_streak"] >= 3:
                    more, reason = False, "three consecutive pages without new eligible jobs"
                elif page >= 8:
                    more, reason = False, "eight-page safety budget per keyword"
                elif more:
                    reason = "continuing bounded sample"
                self.finish_page(state, [str(item.get("id") or item.get("job_url") or "") for item in items],
                                 [item.get("published_at") for item in items], more)
                state["page"] = page + 1
                self.coverage_warning = f"Coverage limited: Bossjob refreshed ranking has no publication cutoff; {reason}"
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
            if not title or not self.accepts_opportunity(title, desc):
                continue
            date_val = normalize_date(item.get("listingDate") or "")
            if not self.accepts_date(date_val):
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
                role_category=self.job_role(title, desc),
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
    search_query = ""

    def fetch(self, query="", location="philippines"):
        self.last_fetch_mode = "catalogue"
        self.last_error = ""
        self.has_more = False
        state = dict(getattr(self, "feed_state", {}))
        self.next_feed_state = state
        page = state.get("page", 1)
        now = time.time()
        start, _ = self.date_window()
        window_start = start.date().isoformat()
        if state.get("days") != self.window_days or state.get("window_start") != window_start or state.get("query", "") != self.search_query:
            page = 1
            state.update(page=1, previous_page="")
        state["days"] = self.window_days
        state["query"] = self.search_query
        state["window_start"] = window_start
        if page == 1:
            state.update(cycle_started=now, full=False)
        try:
            params = urllib.parse.urlencode({"siteKey": "PH-Main", "keywords": self.search_query, "page": page,
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
                if not self.accepts_date(raw_date):
                    continue
                h4 = card.select_one("h4")
                if not h4:
                    continue
                for badge in h4.select(".badge"):
                    badge.extract()
                title = h4.get_text(strip=True)
                desc = card.select_one(".desc")
                description = desc.get_text() if desc else ""
                if not title or not self.accepts_opportunity(title, description):
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
                                role_category=self.job_role(title), experience_level=classify_experience_level(title, description),
                                description=description, date_posted=raw_date))
        except Exception as exc:
            self.last_error = str(exc) or type(exc).__name__
            logger.error("[%s] fetch failed: %s", self.platform, self.last_error)
        return jobs


class FounditPHConnector(NewPlatformConnectorMixin, BaseConnector):
    platform = "Foundit.ph"
    tier = 1
    is_feed = False
    checkpointed_query = True
    query_group_size = 5
    revision = 1
    PAGE_SIZE = 30
    _session = None
    _session_primed = False

    @classmethod
    def _get_session(cls):
        from curl_cffi import requests as cffi_requests
        if cls._session is None:
            cls._session = cffi_requests.Session(impersonate="chrome120")
        if not cls._session_primed:
            try:
                cls._session.get("https://www.foundit.com.ph/srp/results?query=developer", timeout=12)
                cls._session_primed = True
            except Exception:
                pass
        return cls._session

    def fetch(self, query: str = "software developer", location: str = "Philippines") -> List[Job]:
        self.last_error = ""
        self.coverage_warning = ""
        jobs: List[Job] = []
        state = self.page_state(query)
        start = int(state.get("start", 0) or 0)
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.foundit.com.ph/middleware/jobsearch?sort=1&limit={self.PAGE_SIZE}&start={start}&query={encoded_query}"
        referer = f"https://www.foundit.com.ph/srp/results?query={encoded_query}"
        try:
            sess = self._get_session()
            resp = sess.get(
                url,
                headers={"Accept": "application/json, text/plain, */*", "Referer": referer},
                timeout=15,
            )
            if resp.status_code != 200:
                self._session_primed = False
                sess = self._get_session()
                resp = sess.get(
                    url,
                    headers={"Accept": "application/json, text/plain, */*", "Referer": referer},
                    timeout=15,
                )
            if resp.status_code != 200:
                self.last_error = f"Foundit.ph HTTP {resp.status_code}"
                return jobs
            payload = resp.json()
            items = payload.get("jobSearchResponse", {}).get("data", []) or []
            raw_ids: List[str] = []
            raw_dates: List[str] = []
            parsed_rows = []
            for item in items:
                if not isinstance(item, dict) or ("title" not in item and "jobId" not in item):
                    continue
                jid = str(item.get("jobId") or item.get("id") or "")
                ts = item.get("createdAt") or item.get("freshness") or item.get("postedAt")
                pub_date = ""
                if ts is not None:
                    try:
                        ts_int = int(ts)
                        if ts_int > 10_000_000_000:
                            ts_int = ts_int // 1000
                        pub_date = normalize_date(ts_int)
                    except (ValueError, TypeError):
                        pub_date = normalize_date(str(ts))
                raw_ids.append(jid or str(len(raw_ids)))
                raw_dates.append(pub_date)
                parsed_rows.append((item, jid, pub_date))

            has_in_window = any(self.accepts_date(d) for d in raw_dates if d)
            max_start = 240 if self.window_days > 2 else 120
            more_available = has_in_window and len(parsed_rows) >= self.PAGE_SIZE - 5 and start + self.PAGE_SIZE <= max_start
            self.finish_page(state, raw_ids, raw_dates, more_available, ordered=False)
            state["start"] = start + self.PAGE_SIZE if self.has_more else 0

            for item, jid, pub_date in parsed_rows:
                if not self.accepts_date(pub_date):
                    continue
                title = str(item.get("title") or "").strip()
                exp_str = str(item.get("exp") or "").strip()
                min_exp = (item.get("minimumExperience") or {}).get("years") if isinstance(item.get("minimumExperience"), dict) else None
                exp_tag = ""
                if exp_str:
                    exp_tag = f"{exp_str} experience"
                elif min_exp is not None and isinstance(min_exp, int) and 0 <= min_exp <= 2:
                    exp_tag = f"0-{max(1, min_exp)} years experience"
                raw_desc = str(item.get("description") or item.get("skills") or "")
                desc = f"{exp_tag} | {raw_desc}".strip(" |") if exp_tag else raw_desc
                if not title or not self.accepts_opportunity(title, desc):
                    continue
                comp = str(item.get("companyName") or "Foundit PH Employer").strip()
                locs = item.get("locations") or "Philippines"
                loc_str = ", ".join(locs) if isinstance(locs, list) else str(locs)
                if "philippines" not in loc_str.lower():
                    loc_str = f"{loc_str}, Philippines" if loc_str else "Philippines"
                if not is_work_authorized_location(loc_str, title, self.platform, desc):
                    continue
                jd_url = str(item.get("seoJdUrl") or item.get("jdUrl") or "")
                if jd_url and not jd_url.startswith("http"):
                    link = f"https://www.foundit.com.ph{jd_url if jd_url.startswith('/') else '/' + jd_url}"
                elif jid:
                    link = f"https://www.foundit.com.ph/job/{jid}"
                else:
                    continue
                jobs.append(Job(
                    title=title,
                    company=comp,
                    location=loc_str,
                    platform=self.platform,
                    tier=self.tier,
                    job_url=link,
                    salary="",
                    role_category=self.job_role(title, desc),
                    experience_level=classify_experience_level(title, desc),
                    description=desc,
                    date_posted=pub_date,
                ))
        except Exception as exc:
            self.last_error = str(exc) or type(exc).__name__
            logger.warning("[%s] fetch notice: %s", self.platform, self.last_error)
        return jobs


class VirtualStaffPHConnector(NewPlatformConnectorMixin, BaseConnector):
    platform = "VirtualStaff.ph"
    tier = 1
    is_feed = True
    revision = 2
    PAGE_SIZE = 60
    _cached_jobs = None
    _last_fetch = 0
    _cached_window = 2

    def fetch(self, query: str = "", location: str = "Philippines") -> List[Job]:
        self.last_error = ""
        self.coverage_warning = ""
        import time

        now = time.time()
        if (
            VirtualStaffPHConnector._cached_jobs is None
            or (now - VirtualStaffPHConnector._last_fetch > 180)
            or VirtualStaffPHConnector._cached_window != self.window_days
        ):
            jobs: List[Job] = []
            try:
                from curl_cffi import requests as cffi_requests
                resp = cffi_requests.post(
                    "https://www.virtualstaff.ph/api/external/job-list",
                    json={"limit": self.PAGE_SIZE, "skip": 0, "query": {}},
                    headers={
                        "Content-Type": "application/json",
                        "Referer": "https://www.virtualstaff.ph/jobs",
                        "Origin": "https://www.virtualstaff.ph",
                    },
                    impersonate="chrome120",
                    timeout=15,
                )
                if resp.status_code != 200:
                    self.last_error = f"VirtualStaff.ph HTTP {resp.status_code}"
                    return []
                payload = resp.json()
                result = payload.get("result", {}) if isinstance(payload, dict) else {}
                items = result.get("data", []) or []

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    jid = str(item.get("_id") or "")
                    raw_dt = str(item.get("created_time") or item.get("updated_time") or "")
                    pub_date = normalize_date(raw_dt)
                    if not jid or not self.accepts_date(pub_date):
                        continue
                    title = str(item.get("job_title") or item.get("job_name") or "").strip()
                    exp_raw = str(item.get("experience") or "").strip().lower()
                    exp_tag = "entry level" if exp_raw == "entry" else (f"{exp_raw} level" if exp_raw else "")
                    q_parts = []
                    for q_obj in (item.get("questionnaire") or []):
                        if isinstance(q_obj, dict):
                            ans = q_obj.get("answer")
                            if isinstance(ans, list):
                                q_parts.extend(str(a) for a in ans)
                            elif ans:
                                q_parts.append(str(ans))
                    skills = [
                        str(s.get("skill") if isinstance(s, dict) else s)
                        for s in (item.get("skills") or item.get("experience_level") or [])
                    ]
                    desc = " | ".join(filter(None, [
                        exp_tag,
                        str(item.get("job_desc_short") or item.get("job_desc") or ""),
                        ", ".join(skills),
                        " ; ".join(q_parts),
                    ]))
                    if not title or not self.accepts_opportunity(title, desc):
                        continue
                    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
                    link = f"https://www.virtualstaff.ph/jobs-in-philippines/{jid}/{slug}" if slug else f"https://www.virtualstaff.ph/jobs-in-philippines/{jid}"
                    php_sal = item.get("monthly_salary_php")
                    usd_sal = item.get("monthly_salary_usd")
                    sal_amt = item.get("salary_amount")
                    sal_per = item.get("salary_period") or "hr"
                    salary = ""
                    if php_sal and usd_sal:
                        salary = f"PHP {int(float(php_sal)):,}/mo (${int(float(usd_sal)):,}/mo)"
                    elif sal_amt:
                        salary = f"${sal_amt}/{sal_per}"
                    jobs.append(Job(
                        title=title,
                        company="Direct Client (VirtualStaff.ph)",
                        location="Philippines (Remote)",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=self.job_role(title, desc),
                        experience_level=classify_experience_level(title, desc),
                        description=desc,
                        date_posted=pub_date,
                    ))
                VirtualStaffPHConnector._cached_jobs = jobs
                VirtualStaffPHConnector._last_fetch = now
                VirtualStaffPHConnector._cached_window = self.window_days
            except Exception as exc:
                self.last_error = str(exc) or type(exc).__name__
                logger.warning("[%s] fetch notice: %s", self.platform, self.last_error)

        cached = VirtualStaffPHConnector._cached_jobs or []
        if not query:
            return cached
        q_lower = query.strip().lower()
        return [
            j for j in cached
            if q_lower in j.title.lower() or q_lower in (j.description or "").lower()
        ]


class PhilJobNetConnector(NewPlatformConnectorMixin, BaseConnector):
    platform = "PhilJobNet"
    tier = 2
    is_feed = True
    revision = 1
    SEARCH_TERMS = ["developer", "software", "programmer", "quality assurance", "virtual assistant", "information technology", "web", "system", "network", "data", "technical support", "computer"]
    _cached_jobs = None
    _last_fetch = 0
    _cached_window = 2

    def fetch(self, query: str = "", location: str = "Philippines") -> List[Job]:
        self.last_error = ""
        import time
        from datetime import datetime
        from bs4 import BeautifulSoup
        from curl_cffi import requests as cffi_requests

        now = time.time()
        if (
            PhilJobNetConnector._cached_jobs is None
            or (now - PhilJobNetConnector._last_fetch > 180)
            or PhilJobNetConnector._cached_window != self.window_days
        ):
            all_jobs: List[Job] = []
            seen_urls = set()
            try:
                sess = cffi_requests.Session(impersonate="chrome120")
                base_url = "https://philjobnet.gov.ph/job-vacancies/"
                r0 = sess.get(base_url, timeout=15)
                pages_html = [r0.text] if r0.status_code == 200 else []
                if r0.status_code == 200:
                    soup0 = BeautifulSoup(r0.text, "html.parser")
                    hidden = {
                        inp["name"]: inp.get("value", "")
                        for inp in soup0.select("form input[type='hidden']")
                        if inp.get("name")
                    }
                    for term in self.SEARCH_TERMS:
                        form_data = dict(hidden)
                        form_data["ctl00$BodyContentPlaceHolder$searchterm"] = term
                        form_data["ctl00$BodyContentPlaceHolder$Button1"] = "Search Job"
                        try:
                            rs = sess.post(base_url, data=form_data, timeout=15)
                            if rs.status_code == 200:
                                pages_html.append(rs.text)
                        except Exception:
                            continue

                for html_doc in pages_html:
                    soup = BeautifulSoup(html_doc, "html.parser")
                    for card in soup.select(".jobcard"):
                        parent_a = card.find_parent("a", href=True)
                        href = parent_a["href"] if parent_a else ""
                        if not href:
                            continue
                        link = urllib.parse.urljoin("https://philjobnet.gov.ph", href)
                        if link in seen_urls:
                            continue
                        title_el = card.select_one(".jobtitle")
                        title = title_el.get_text(" ", strip=True) if title_el else ""
                        if not title:
                            continue
                        card_text = card.get_text(" ", strip=True)
                        m_date = re.search(r"Posted on\s+(\d{1,2}/\d{1,2}/\d{4})", card_text, re.I)
                        pub_date = ""
                        if m_date:
                            try:
                                pub_date = datetime.strptime(m_date.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
                            except ValueError:
                                pub_date = ""
                        if not self.accepts_date(pub_date):
                            continue
                        if not self.accepts_opportunity(title, card_text):
                            continue
                        comp_el = card.select_one(".companytitle")
                        comp = comp_el.get_text(" ", strip=True) if comp_el else "PhilJobNet Employer"
                        sal_el = card.select_one(".salary")
                        sal = sal_el.get_text(" ", strip=True).replace("₱", "PHP ") if sal_el else ""
                        loc_icon = card.select_one(".bi-geo-alt")
                        loc_str = loc_icon.parent.get_text(" ", strip=True) if (loc_icon and loc_icon.parent) else "Philippines"
                        if "philippines" not in loc_str.lower():
                            loc_str = f"{loc_str}, Philippines"
                        seen_urls.add(link)
                        all_jobs.append(Job(
                            title=title,
                            company=comp,
                            location=loc_str,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary=sal,
                            role_category=self.job_role(title, card_text),
                            experience_level=classify_experience_level(title, card_text),
                            description=card_text,
                            date_posted=pub_date,
                        ))
                PhilJobNetConnector._cached_jobs = all_jobs
                PhilJobNetConnector._last_fetch = now
                PhilJobNetConnector._cached_window = self.window_days
            except Exception as exc:
                self.last_error = str(exc) or type(exc).__name__
                logger.warning("[%s] fetch notice: %s", self.platform, self.last_error)

        cached = PhilJobNetConnector._cached_jobs or []
        if not query:
            return cached
        q_lower = query.strip().lower()
        return [
            j for j in cached
            if q_lower in j.title.lower() or q_lower in (j.description or "").lower()
        ]


class JobgetherPHConnector(NewPlatformConnectorMixin, BaseConnector):
    platform = "Jobgether"
    tier = 1
    is_feed = True
    revision = 1
    URLS = [
        "https://jobgether.com/remote-jobs/philippines",
        "https://jobgether.com/remote-jobs/philippines?page=2",
        "https://jobgether.com/remote-jobs/philippines?page=3",
        "https://jobgether.com/remote-jobs/philippines?page=4",
        "https://jobgether.com/remote-jobs/philippines?page=5",
        "https://jobgether.com/search-offers?keyword=software%20developer",
        "https://jobgether.com/search-offers?keyword=web%20developer",
        "https://jobgether.com/search-offers?keyword=mobile%20developer",
        "https://jobgether.com/search-offers?keyword=qa%20engineer",
        "https://jobgether.com/search-offers?keyword=data%20analyst",
        "https://jobgether.com/search-offers?keyword=technical%20support",
        "https://jobgether.com/search-offers?keyword=virtual%20assistant",
    ]
    _cached_jobs = None
    _last_fetch = 0
    _cached_window = 2

    def fetch(self, query: str = "", location: str = "Philippines") -> List[Job]:
        self.last_error = ""
        import time
        from bs4 import BeautifulSoup

        now = time.time()
        if (
            JobgetherPHConnector._cached_jobs is None
            or (now - JobgetherPHConnector._last_fetch > 180)
            or JobgetherPHConnector._cached_window != self.window_days
        ):
            all_jobs: List[Job] = []
            seen_urls = set()
            for page_url in self.URLS:
                try:
                    resp = self.get_url(page_url, impersonate="chrome120", timeout=15)
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "html.parser")
                    is_ph_landing = "remote-jobs/philippines" in page_url
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/offer/" not in href:
                            continue
                        link = urllib.parse.urljoin("https://jobgether.com", href)
                        if link in seen_urls:
                            continue
                        title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
                        if not title or title.lower() == "apply":
                            continue
                        card = a.find_parent("div", class_=lambda c: c and ("shadow" in c or "group" in c)) or a.parent.parent
                        card_text = card.get_text(" | ", strip=True) if card else title

                        pub_date = ""
                        m_oid = re.search(r"/offer/([0-9a-f]{8})[0-9a-f]{16}-", href)
                        if m_oid:
                            try:
                                pub_date = normalize_date(int(m_oid.group(1), 16))
                            except ValueError:
                                pub_date = ""
                        if not pub_date and card:
                            for sp in card.find_all("span"):
                                st = sp.get_text(strip=True)
                                if st and (st.lower() in ("today", "yesterday") or "ago" in st.lower()):
                                    pub_date = normalize_date(st)
                                    if pub_date:
                                        break
                        if not self.accepts_date(pub_date):
                            continue
                        if not self.accepts_opportunity(title, card_text):
                            continue

                        comp = "Jobgether Partner"
                        if card:
                            img = card.find("img", alt=True)
                            if img and img.get("alt"):
                                comp = img["alt"].strip()

                        loc_str = "Philippines (Remote)" if is_ph_landing else "Remote (Worldwide)"
                        if not is_ph_landing and card:
                            m_loc = re.search(r"Remote from\s*\|\s*([^|]+)", card_text, re.I)
                            if m_loc:
                                loc_region = m_loc.group(1).strip()
                                loc_str = f"Remote ({loc_region})"
                        if not is_work_authorized_location(loc_str, title, self.platform, card_text):
                            continue

                        seen_urls.add(link)
                        all_jobs.append(Job(
                            title=title,
                            company=comp,
                            location=loc_str,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary="",
                            role_category=self.job_role(title, card_text),
                            experience_level=classify_experience_level(title, card_text),
                            description=card_text,
                            date_posted=pub_date,
                        ))
                except Exception as exc:
                    self.last_error = str(exc) or type(exc).__name__
                    logger.warning("[%s] fetch notice for %s: %s", self.platform, page_url, self.last_error)

            JobgetherPHConnector._cached_jobs = all_jobs
            JobgetherPHConnector._last_fetch = now if not self.last_error else 0
            JobgetherPHConnector._cached_window = self.window_days

        cached = JobgetherPHConnector._cached_jobs or []
        if not query:
            return cached
        q_lower = query.strip().lower()
        return [
            j for j in cached
            if q_lower in j.title.lower() or q_lower in (j.description or "").lower()
        ]
