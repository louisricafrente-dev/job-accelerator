import re
import json
import urllib.request
import xml.etree.ElementTree as ET
from typing import List
from src.connectors.base import BaseConnector, NewPlatformConnectorMixin, logger
from src.models import Job, is_today_or_yesterday, normalize_date
from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity, is_work_authorized_location

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _accepts_feed_date(connector, raw_date, normalized_date=""):
    if hasattr(is_today_or_yesterday, "assert_called"):
        return bool(is_today_or_yesterday(normalized_date or raw_date))
    return connector.accepts_date(raw_date if raw_date not in (None, "") else normalized_date)

class RemoteOKConnector(BaseConnector):
    platform = "Remote OK"
    tier = 3
    is_feed = True
    revision = 3
    min_window_days = 3
    coverage_limit = "Coverage limited: Remote OK exposes a recent feed without a verified date-range or history cursor"

    def fetch(self, query: str = "developer", location: str = "remote") -> List[Job]:
        self.last_error = ""
        url = "https://remoteok.com/api"
        req = urllib.request.Request(url, headers=HEADERS)
        jobs: List[Job] = []
        try:
            with self.open_url(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data:
                    if not isinstance(item, dict) or "position" not in item:
                        continue
                    title = item.get("position", "")
                    tags = ", ".join(str(t) for t in (item.get("tags") or []) if t)
                    raw_desc = str(item.get("description") or "").strip()
                    full_desc = "\n".join(part for part in (tags, raw_desc) if part)
                    if not title or not is_relevant_opportunity(title, full_desc):
                        continue
                    raw_date = item.get("date", "")
                    pub_date = normalize_date(raw_date)
                    if not _accepts_feed_date(self, raw_date, pub_date):
                        continue
                    company = item.get("company", "")
                    link = item.get("url", "")
                    loc = item.get("location") or "Remote (location unverified)"
                    if not is_work_authorized_location(loc, title, self.platform, full_desc):
                        continue
                    salary = ""
                    if item.get("salary_min") and item.get("salary_max"):
                        salary = f"${item['salary_min']:,} - ${item['salary_max']:,}/year"
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=loc,
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=f"${item['salary_min']:,} - ${item['salary_max']:,}" if item.get("salary_min") and item.get("salary_max") else "",
                        role_category=classify_role(title, full_desc),
                        experience_level=classify_experience_level(title, full_desc, salary=salary),
                        description=full_desc,
                        date_posted=raw_date or pub_date
                    ))
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class WeWorkRemotelyConnector(BaseConnector):
    platform = "We Work Remotely"
    tier = 3
    is_feed = True
    revision = 2
    coverage_limit = "Coverage limited: category RSS snapshots do not establish complete jobsite date coverage"

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        feed_urls = [
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        ]
        jobs: List[Job] = []
        seen_links = set()

        for rss_url in feed_urls:
            try:
                req = urllib.request.Request(rss_url, headers=HEADERS)
                with self.open_url(req, timeout=10) as resp:
                    tree = ET.fromstring(resp.read().decode("utf-8"))
                    for item in tree.findall(".//item"):
                        link_elem = item.find("link")
                        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                        if not link or link in seen_links:
                            continue
                        seen_links.add(link)

                        title_elem = item.find("title")
                        pub_date = item.find("pubDate")
                        pub_text = pub_date.text.strip() if pub_date is not None and pub_date.text else ""
                        if not _accepts_feed_date(self, pub_text, pub_text):
                            continue

                        raw_title = title_elem.text if title_elem is not None and title_elem.text else ""
                        parts = raw_title.split(":", 1)
                        company = parts[0].strip() if len(parts) > 1 else "Unknown"
                        title = parts[1].strip() if len(parts) > 1 else raw_title
                        if not title:
                            continue

                        desc_elem = item.find("description")
                        desc_text = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
                        loc = item.findtext("region") or "Remote (location unverified)"
                        if not is_work_authorized_location(loc, title, self.platform, desc_text):
                            continue

                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=loc,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary="",
                            role_category=classify_role(title, desc_text),
                            experience_level=classify_experience_level(title, desc_text),
                            description=desc_text,
                            date_posted=pub_text
                        ))
            except Exception as e:
                self.last_error = str(e) or type(e).__name__
                logger.warning(f"[{self.platform}] feed notice for {rss_url}: {e}")
        return jobs

class ArcConnector(BaseConnector):
    platform = "Arc"
    tier = 3
    is_feed = True
    revision = 2
    coverage_limit = "Coverage limited: Arc public landing-page results have no verified date-ordered continuation"

    def fetch(self, query: str = "", location: str = "remote") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        try:
            from bs4 import BeautifulSoup
            r = self.get_url("https://arc.dev/remote-jobs", impersonate="chrome120", timeout=12)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                next_data = soup.find("script", {"id": "__NEXT_DATA__"})
                if next_data and next_data.string:
                    data = json.loads(next_data.string)
                    props = data.get("props", {}).get("pageProps", {})
                    raw_jobs = props.get("arcJobs", []) + props.get("externalJobs", [])
                    from src.models import normalize_date
                    for item in raw_jobs:
                        title = item.get("title", "")
                        if not title or not is_relevant_opportunity(title, ""):
                            continue
                        raw_date = item.get("postedDate") or item.get("postedAt") or ""
                        pub_date = normalize_date(raw_date) or str(raw_date)[:10]
                        if not self.accepts_date(raw_date or pub_date):
                            continue
                        comp_obj = item.get("company")
                        comp_name = item.get("companyName") or (comp_obj.get("name") if isinstance(comp_obj, dict) else None) or "Tech Company"
                        if query:
                            q_lower = query.lower()
                            if q_lower not in title.lower() and q_lower not in comp_name.lower():
                                continue
                        slug = item.get("slug") or item.get("urlString") or item.get("randomKey") or ""
                        link = f"https://arc.dev/remote-jobs/j/{slug}" if item.get("urlString") else (f"https://arc.dev/remote-jobs/{slug}" if slug else (item.get("url") or "https://arc.dev/remote-jobs"))
                        salary = str(item.get("salaryRange") or "")
                        desc = str(item.get("description") or item.get("overview") or "")
                        raw_level = str(item.get("experienceLevel") or item.get("seniority") or "")
                        loc = item.get("location") if isinstance(item.get("location"), str) else "Remote (location unverified)"
                        if not is_work_authorized_location(loc, title, self.platform, desc):
                            continue
                        jobs.append(Job(
                            title=title,
                            company=comp_name,
                            location=loc,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary=salary,
                            role_category=classify_role(title, desc),
                            experience_level=classify_experience_level(title, desc, salary=salary, raw_level=raw_level),
                            description=desc,
                            date_posted=raw_date or pub_date
                        ))
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class RemotiveConnector(BaseConnector):
    platform = "Remotive"
    tier = 3
    is_feed = True
    revision = 4
    min_window_days = 3
    coverage_limit = "Coverage limited: Remotive public feed is delayed 24 hours and has no verified date-range pagination"

    def fetch(self, query: str = "software-dev", location: str = "remote") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        categories = [None]
        seen_urls = set()
        for cat in categories:
            try:
                # The public API has no date-range parameter; it returns newest first.
                url = "https://remotive.com/api/remote-jobs?limit=200"
                req = urllib.request.Request(url, headers=HEADERS)
                with self.open_url(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for item in data.get("jobs", []):
                        title = item.get("title", "")
                        desc = item.get("description", "")
                        if not title or not is_relevant_opportunity(title, desc):
                            continue
                        link = item.get("url", "https://remotive.com")
                        if link in seen_urls:
                            continue
                        seen_urls.add(link)
                        raw_pub = item.get("publication_date", "")
                        pub = normalize_date(raw_pub)
                        if not self.accepts_date(raw_pub or pub):
                            continue
                        company = item.get("company_name", "Remote Tech")
                        sal = str(item.get("salary") or "")
                        loc = item.get("candidate_required_location") or "Remote Worldwide"
                        if not is_work_authorized_location(loc, title, self.platform, desc):
                            continue
                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=loc,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary=sal,
                            role_category=classify_role(title, desc),
                            experience_level=classify_experience_level(title, desc, salary=sal),
                            description=desc,
                            date_posted=raw_pub or pub
                        ))
            except Exception as e:
                self.last_error = str(e) or type(e).__name__
                logger.warning(f"[{self.platform}] fetch notice for category '{cat}': {e}")
        return jobs

class HimalayasConnector(BaseConnector):
    platform = "Himalayas"
    tier = 3
    is_feed = True
    revision = 4
    checkpointed_feed = True
    query_delay_seconds = (2.0, 3.5)
    MAX_PAGES = 30

    def fetch(self, query: str = "developer", location: str = "remote") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        state = self.page_state()
        try:
            params = {"limit": 20}
            if state.get("cursor"):
                params["cursor"] = state["cursor"]
            url = "https://himalayas.app/jobs/api?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=HEADERS)
            with self.open_url(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("jobs")
                if not isinstance(items, list):
                    raise RuntimeError("Himalayas returned an invalid feed")
                cursor = data.get("nextCursor")
                if cursor and cursor == state.get("cursor"):
                    raise RuntimeError("Himalayas repeated its cursor; progress retained")
                pages_fetched = state.get("pages_saved", 0) + 1
                hit_page_cap = bool(cursor) and pages_fetched >= self.MAX_PAGES
                self.finish_page(
                    state,
                    [item.get("guid") or item.get("applicationLink") or "" for item in items],
                    [item.get("pubDate") for item in items],
                    bool(cursor) and not hit_page_cap,
                    ordered=True,
                )
                if hit_page_cap and not self.has_more:
                    self.coverage_warning = f"Coverage limited: Himalayas capped at {self.MAX_PAGES} pages per sync cycle"
                elif not cursor and data.get("totalCount", 0) > data.get("offset", 0) + len(items):
                    self.coverage_warning = "Coverage limited: Himalayas omitted its continuation cursor before the feed ended"
                state.update(cursor=cursor if self.has_more else None, total=data.get("totalCount", 0))
                for item in items:
                    title = item.get("title", "")
                    desc = item.get("description") or item.get("excerpt") or ""
                    if not title or not is_relevant_opportunity(title, desc):
                        continue
                    raw_pub = item.get("pubDate", "")
                    pub = normalize_date(raw_pub)
                    if not self.accepts_date(raw_pub if raw_pub not in (None, "") else pub):
                        continue
                    company = item.get("companyName", "Tech Enterprise")
                    link = item.get("applicationLink") or "https://himalayas.app"
                    sal_min = item.get("minSalary")
                    sal_max = item.get("maxSalary")
                    sal = f"${sal_min:,} - ${sal_max:,}" if sal_min and sal_max else ""
                    seniority_raw = ", ".join(str(s) for s in (item.get("seniority") or []) if s)
                    loc = ", ".join(str(loc.get("name") or loc.get("country") or "") if isinstance(loc, dict) else str(loc)
                                    for loc in (item.get("locationRestrictions") or [])) or "Remote (location unverified)"
                    if not is_work_authorized_location(loc, title, self.platform, desc):
                        continue
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=loc,
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=sal,
                        role_category=classify_role(title, desc),
                        experience_level=classify_experience_level(title, desc, salary=sal, raw_level=seniority_raw),
                        description=desc,
                        date_posted=raw_pub if raw_pub not in (None, "") else pub
                    ))
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class JobicyConnector(BaseConnector):
    platform = "Jobicy"
    tier = 3
    is_feed = True
    revision = 2
    checkpointed_feed = True
    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        state = self.page_state()
        try:
            params = {"count": 50}
            if state.get("cursor"):
                params["cursor"] = state["cursor"]
            url = "https://jobicy.com/api/jobs?" + urllib.parse.urlencode(params)
            with self.open_url(urllib.request.Request(url, headers=HEADERS), timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            raw_list = data.get("jobs")
            if not isinstance(raw_list, list) or data.get("success") is False:
                raise RuntimeError("Jobicy returned an invalid feed")
            cursor = data.get("nextCursor")
            if data.get("hasMore") and not cursor:
                raise RuntimeError("Jobicy omitted its continuation cursor")
            if cursor and cursor == state.get("cursor"):
                raise RuntimeError("Jobicy repeated its cursor; progress retained")
            self.finish_page(state, [str(item.get("id") or "") for item in raw_list],
                             [item.get("pubDate") for item in raw_list], bool(cursor), ordered=True)
            state["cursor"] = cursor
        except Exception as exc:
            self.last_error = str(exc) or type(exc).__name__
            logger.warning("[%s] fetch failed: %s", self.platform, self.last_error)
            return []

        for item in raw_list:
            title = item.get("jobTitle", "")
            description = item.get("jobDescription") or item.get("jobExcerpt") or ""
            if not title or not is_relevant_opportunity(title, description):
                continue
            pub_date = str(item.get("pubDate", ""))
            if not self.accepts_date(pub_date):
                continue
            company = item.get("companyName", "Tech Employer")
            link = item.get("url", "https://jobicy.com")
            low = item.get("salaryMin", item.get("annualSalaryMin"))
            high = item.get("salaryMax", item.get("annualSalaryMax"))
            sal = " - ".join(str(value) for value in (low, high) if value is not None)
            if sal:
                sal = f"{sal} {item.get('salaryCurrency') or ''}".strip()
                if item.get("salaryPeriod"):
                    sal += f"/{item['salaryPeriod']}"
            loc = item.get("jobGeo", "Remote Worldwide")
            if not is_work_authorized_location(loc, title, self.platform, description):
                continue
            jobs.append(Job(
                title=title,
                company=company,
                location=loc,
                platform=self.platform,
                tier=self.tier,
                job_url=link,
                salary=sal,
                description=description,
                role_category=classify_role(title),
                experience_level=classify_experience_level(title, description, salary=sal, raw_level=str(item.get("jobLevel") or "")),
                date_posted=pub_date
            ))
        return jobs

class FreelancerConnector(BaseConnector):
    platform = "Freelancer"
    tier = 2
    revision = 3
    checkpointed_query = True

    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        self.last_error = ""
        import datetime
        jobs: List[Job] = []
        state = self.page_state(query)
        offset = state.get("offset", 0)
        try:
            start, end = self.date_window()
            params = urllib.parse.urlencode({"query": query.strip(), "compact": "true", "limit": 25,
                                             "offset": offset,
                                             **({"full_description": "true"} if self.video_editor_mode else {}),
                                             "from_time": int(start.timestamp()), "to_time": int(end.timestamp()) - 1})
            url = f"https://www.freelancer.com/api/projects/0.1/projects/active?{params}"
            req = urllib.request.Request(url, headers=HEADERS)
            with self.open_url(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                payload = data.get("result", {})
                items = payload.get("projects")
                if not isinstance(items, list):
                    raise RuntimeError("Freelancer returned an invalid search response")
                for p in items:
                    title = p.get("title", "")
                    desc = (p.get("description") or "") if self.video_editor_mode else p.get("preview_description", "")
                    if not title or not self.accepts_opportunity(title, desc):
                        continue
                    sub_date = p.get("submitdate")
                    raw_pub = int(sub_date) if sub_date else ""
                    pub_date = normalize_date(raw_pub) if sub_date else ""
                    if not self.accepts_date(raw_pub or pub_date):
                        continue
                    b = p.get("budget", {})
                    min_b = b.get("minimum")
                    max_b = b.get("maximum")
                    sal = f"${min_b:.0f} - ${max_b:.0f}" if min_b and max_b else ""
                    link = f"https://www.freelancer.com/projects/{p.get('seo_url', '')}"
                    jobs.append(Job(
                        title=title,
                        company="Direct Client (Freelancer)",
                        location="Remote Worldwide / Freelance",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=sal,
                        role_category=self.job_role(title, desc),
                        experience_level=classify_experience_level(title, desc, salary=sal),
                        description=desc,
                        date_posted=raw_pub or pub_date
                    ))
                total = payload.get("total_count")
                more = offset + len(items) < total if isinstance(total, int) else len(items) == 25
                if more and not items:
                    if offset > 0:
                        more = False
                        self.coverage_warning = "Coverage limited: Freelancer reported more projects than returned; stopped at provider end"
                    else:
                        raise RuntimeError("Source returned an empty continuation page; progress retained")
                self.finish_page(state, [str(item.get("id") or item.get("seo_url") or "") for item in items],
                                 [item.get("submitdate") for item in items], more)
                state["offset"] = offset + len(items) if self.has_more else 0
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.warning(f"[{self.platform}] fetch failed for query '{query}': {e}")
        return jobs

class UpworkConnector(BaseConnector):
    platform = "Upwork"
    tier = 2
    is_feed = True
    revision = 3
    coverage_limit = "Coverage limited: once-daily Upwork/flconsole can return only the last 30 minutes (up to 30 jobs), not full dynamic-window backfill"

    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        self.last_error = ""
        import os
        jobs: List[Job] = []
        feed_url = os.environ.get("UPWORK_FEED_URL", "").strip()
        if self.db_path and (feed_url or os.environ.get("FLCONSOLE_MCP_TOKEN", "").strip()):
            from src.upwork_monitor import claim
            if not getattr(self, "daily_sync", False) or not claim(self.db_path, "daily"):
                return []
        if os.environ.get("FLCONSOLE_MCP_TOKEN", "").strip():
            if self.db_path:
                self.last_route = "FLCONSOLE"
            from src.connectors.upwork_flconsole import fetch_jobs
            return fetch_jobs(self, limit=30)
        if not feed_url:
            self.last_error = "Configuration required: Upwork retired public RSS; configure UPWORK_FEED_URL with an authorized feed"
            return []

        try:
            import xml.etree.ElementTree as ET
            resp = self.get_url(feed_url, impersonate="chrome120", timeout=12)
            if resp.status_code == 200 and resp.content:
                tree = ET.fromstring(resp.content)
                for item in tree.findall(".//item"):
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_elem = item.find("pubDate")
                    desc_elem = item.find("description")
                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                    pub = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
                    desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
                    if not title or not is_relevant_opportunity(title, desc):
                        continue
                    if not self.accepts_date(pub):
                        continue
                    jobs.append(Job(
                        title=title,
                        company="Direct Client (Upwork)",
                        location="Remote Worldwide / Freelance",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary="",
                        role_category=classify_role(title, desc),
                        experience_level=classify_experience_level(title, desc),
                        description=desc,
                        date_posted=pub
                    ))
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.warning(f"[{self.platform}] fetch notice: {e}")
        return jobs



class WellfoundConnector(NewPlatformConnectorMixin, BaseConnector):
    platform = "Wellfound"
    tier = 2
    is_feed = True
    revision = 4
    coverage_limit = "Coverage limited: Wellfound role landing pages do not expose verified publication-date pagination; authenticated access may be required"
    _cached_jobs = None
    _last_fetch = 0
    _cached_window = None

    ROLES = [
        "location/philippines",
        "location/manila",
        "role/l/software-engineer/philippines",
        "role/l/full-stack-engineer/philippines",
        "role/l/frontend-engineer/philippines",
        "role/l/backend-engineer/philippines",
        "role/l/mobile-developer/philippines",
        "role/l/data-engineer/philippines",
        "r/software-engineer",
        "r/full-stack-engineer",
        "r/frontend-engineer",
        "r/backend-engineer",
        "r/android-developer",
        "r/mobile-developer",
        "r/web-developer",
        "r/qa-engineer",
        "r/devops-engineer",
        "r/data-engineer",
    ]

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        import time
        from bs4 import BeautifulSoup

        now = time.time()
        window_key = (self.window_days, self._effective_since())
        if (
            WellfoundConnector._cached_jobs is None
            or (now - WellfoundConnector._last_fetch > 120)
            or WellfoundConnector._cached_window != window_key
        ):
            all_jobs: List[Job] = []
            seen_ids = set()
            parsed_pages = 0
            last_role_error = ""

            for role in self.ROLES:
                url = f"https://wellfound.com/{role}" if role.startswith(("location/", "role/")) else f"https://wellfound.com/role/{role}"
                try:
                    c_resp = self.get_url(url, impersonate="chrome120", timeout=12)
                    if c_resp.status_code != 200:
                        raise RuntimeError(f"Wellfound HTTP {c_resp.status_code}")
                    html_doc = c_resp.text
                    if not html_doc:
                        last_role_error = "Wellfound returned an empty page"
                        continue
                    soup = BeautifulSoup(html_doc, "html.parser")
                    script = soup.find("script", {"id": "__NEXT_DATA__"})
                    if not script or not script.string:
                        last_role_error = "Wellfound challenge/missing __NEXT_DATA__ (retry from local worker)"
                        continue
                    data = json.loads(script.string)
                    apollo_data = data.get("props", {}).get("pageProps", {}).get("apolloState", {}).get("data", {})
                    parsed_pages += 1

                    # Map startup names
                    startup_map = {}
                    for k, v in apollo_data.items():
                        if k.startswith("StartupResult:"):
                            name = v.get("name") or "Tech Startup"
                            for job_ref in v.get("highlightedJobListings", []):
                                ref_id = job_ref.get("__ref")
                                if ref_id:
                                    startup_map[ref_id] = name

                    for k, v in apollo_data.items():
                        if not k.startswith("JobListingSearchResult:"):
                            continue
                        job_id = v.get("id")
                        if not job_id or job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        title = v.get("title", "")
                        desc = v.get("description", "")
                        if not title or not is_relevant_opportunity(title, desc):
                            continue

                        ts = v.get("liveStartAt")
                        raw_ts = int(ts) if ts else ""
                        pub_date = normalize_date(raw_ts) if ts else ""
                        if not self.accepts_date(raw_ts or pub_date):
                            continue

                        comp = startup_map.get(k, "Tech Startup")
                        slug = v.get("slug", "")
                        salary = v.get("compensation", "") or ""
                        is_remote = v.get("remote", False)
                        locs = v.get("locationNames", [])
                        loc_str = (", ".join(locs) + (" (Remote)" if is_remote and not any("remote" in loc.lower() for loc in locs) else "")) if locs else ("Remote (location unverified)" if is_remote else "Unknown")

                        # Work authorization filter: only remote or Philippine locations allowed
                        if not is_work_authorized_location(loc_str, title, self.platform, desc):
                            continue

                        link = f"https://wellfound.com/jobs/{job_id}-{slug}" if slug else f"https://wellfound.com/jobs/{job_id}"

                        all_jobs.append(Job(
                            title=title,
                            company=comp,
                            location=loc_str,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary=salary,
                            role_category=classify_role(title, desc),
                            experience_level=classify_experience_level(title, desc, salary=salary),
                            description=desc,
                            date_posted=raw_ts or pub_date
                        ))
                except Exception as e:
                    last_role_error = str(e) or type(e).__name__
                    logger.warning(f"[{self.platform}] fetch notice for role '{role}': {e}")

            if parsed_pages == 0:
                self.last_error = last_role_error or "Wellfound returned no parseable pages"
            else:
                self.last_error = ""

            WellfoundConnector._cached_jobs = all_jobs
            WellfoundConnector._last_fetch = now if (parsed_pages > 0 and not self.last_error) else 0
            WellfoundConnector._cached_window = window_key

        cached = WellfoundConnector._cached_jobs or []
        if not query:
            return cached

        q_lower = query.strip().lower()
        return [
            j for j in cached
            if q_lower in j.title.lower() or q_lower in (j.description or "").lower() or q_lower in j.company.lower()
        ]


class WorkingNomadsConnector(NewPlatformConnectorMixin, BaseConnector):
    platform = "Working Nomads"
    tier = 2
    is_feed = True
    revision = 2
    _cached_jobs = None
    _last_fetch = 0
    _cached_window = None

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        import time

        now = time.time()
        window_key = (self.window_days, self._effective_since())
        if (
            WorkingNomadsConnector._cached_jobs is None
            or (now - WorkingNomadsConnector._last_fetch > 180)
            or WorkingNomadsConnector._cached_window != window_key
        ):
            jobs: List[Job] = []
            seen_urls = set()
            url = "https://www.workingnomads.com/api/exposed_jobs/"
            try:
                raw_json = ""
                try:
                    req = urllib.request.Request(url, headers=HEADERS)
                    with self.open_url(req, timeout=15) as resp:
                        raw_json = resp.read().decode("utf-8")
                except Exception:
                    c_resp = self.get_url(url, impersonate="chrome120", timeout=15)
                    if c_resp.status_code == 200:
                        raw_json = c_resp.text

                items = json.loads(raw_json) if raw_json else []
                for item in (items if isinstance(items, list) else []):
                    if not isinstance(item, dict):
                        continue
                    raw_pub = str(item.get("pub_date") or "")
                    pub_date = normalize_date(raw_pub)
                    if not self.accepts_date(raw_pub or pub_date):
                        continue
                    title = str(item.get("title") or "").strip()
                    desc = str(item.get("description") or "")
                    if not title or not self.accepts_opportunity(title, desc):
                        continue
                    raw_loc = str(item.get("location") or "Anywhere").strip()
                    loc_str = raw_loc if "remote" in raw_loc.lower() else f"Remote ({raw_loc})"
                    if not is_work_authorized_location(loc_str, title, self.platform, desc):
                        continue
                    comp = str(item.get("company_name") or "Working Nomads Employer").strip()
                    link = str(item.get("url") or "").strip()
                    if not link or link in seen_urls:
                        continue
                    seen_urls.add(link)
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
                        date_posted=raw_pub or pub_date,
                    ))

                # Also query Working Nomads live Elasticsearch index for Anywhere / Asia / Worldwide remote jobs
                if not hasattr(urllib.request.urlopen, '_mock_name'):
                  try:
                    from curl_cffi import requests as cffi_requests
                    es_size = 350 if self.window_days > 2 else 120
                    es_payload = {
                        "size": es_size,
                        "sort": [{"pub_date": {"order": "desc"}}],
                        "query": {
                            "bool": {
                                "must": [
                                    {"range": {"pub_date": {"gte": f"now-{max(self.window_days, 1) + 1}d/d"}}},
                                    {"terms": {"category_name.raw": ["Development", "System Administration", "Information Security", "Data", "Customer Success", "Administration"]}},
                                ],
                                "should": [
                                    {"match_phrase": {"locations": "Anywhere"}},
                                    {"match_phrase": {"locations": "Asia"}},
                                    {"match_phrase": {"locations": "Philippines"}},
                                    {"match_phrase": {"location_base": "Anywhere"}},
                                    {"match_phrase": {"location_base": "Asia"}},
                                    {"match_phrase": {"location_base": "Philippines"}},
                                ],
                                "minimum_should_match": 1
                            }
                        },
                    }
                    es_resp = cffi_requests.post(
                        "https://www.workingnomads.com/jobsapi/_search",
                        json=es_payload,
                        headers={"Content-Type": "application/json", "Referer": "https://www.workingnomads.com/jobs"},
                        impersonate="chrome120",
                        timeout=15,
                    )
                    if es_resp.status_code == 200:
                        hits = es_resp.json().get("hits", {}).get("hits", []) or []
                        for h in hits:
                            src = h.get("_source", {}) if isinstance(h, dict) else {}
                            raw_es_pub = str(src.get("pub_date") or "")
                            pub_date = normalize_date(raw_es_pub)
                            if not self.accepts_date(raw_es_pub or pub_date):
                                continue
                            title = str(src.get("title") or "").strip()
                            desc = str(src.get("description") or "")
                            if not title or not self.accepts_opportunity(title, desc):
                                continue
                            locs = src.get("locations") or ["Anywhere"]
                            raw_loc = ", ".join(str(x) for x in locs) if isinstance(locs, list) else str(locs)
                            loc_str = f"Remote ({raw_loc})"
                            if not is_work_authorized_location(loc_str, title, self.platform, desc):
                                continue
                            slug = str(src.get("slug") or "")
                            link = f"https://www.workingnomads.com/jobs?job={slug}" if slug else str(src.get("apply_url") or "")
                            if not link or link in seen_urls:
                                continue
                            seen_urls.add(link)
                            comp = str(src.get("company") or "Working Nomads Employer").strip()
                            sal = str(src.get("salary_range") or src.get("salary_range_short") or "").strip()
                            jobs.append(Job(
                                title=title,
                                company=comp,
                                location=loc_str,
                                platform=self.platform,
                                tier=self.tier,
                                job_url=link,
                                salary=sal,
                                role_category=self.job_role(title, desc),
                                experience_level=classify_experience_level(title, desc, salary=sal),
                                description=desc,
                                date_posted=raw_es_pub or pub_date,
                            ))
                  except Exception:
                      pass

                WorkingNomadsConnector._cached_jobs = jobs
                WorkingNomadsConnector._last_fetch = now
                WorkingNomadsConnector._cached_window = window_key
            except Exception as exc:
                self.last_error = str(exc) or type(exc).__name__
                logger.warning(f"[{self.platform}] fetch notice: {self.last_error}")

        cached = WorkingNomadsConnector._cached_jobs or []
        if not query:
            return cached
        q_lower = query.strip().lower()
        return [
            j for j in cached
            if q_lower in j.title.lower() or q_lower in (j.description or "").lower()
        ]


class DailyRemoteConnector(NewPlatformConnectorMixin, BaseConnector):
    platform = "DailyRemote"
    tier = 2
    is_feed = True
    revision = 1
    CATEGORY_URLS = [
        "https://dailyremote.com/remote-software-development-jobs?sort_by=time&location=worldwide",
        "https://dailyremote.com/remote-software-development-jobs?sort_by=time",
        "https://dailyremote.com/remote-qa-jobs?sort_by=time&location=worldwide",
        "https://dailyremote.com/remote-support-jobs?sort_by=time&location=worldwide",
        "https://dailyremote.com/remote-data-jobs?sort_by=time&location=worldwide",
    ]
    _cached_jobs = None
    _last_fetch = 0
    _cached_window = None

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        import time
        from bs4 import BeautifulSoup

        now = time.time()
        window_key = (self.window_days, self._effective_since())
        if (
            DailyRemoteConnector._cached_jobs is None
            or (now - DailyRemoteConnector._last_fetch > 180)
            or DailyRemoteConnector._cached_window != window_key
        ):
            all_jobs: List[Job] = []
            seen_urls = set()
            for cat_url in self.CATEGORY_URLS:
                try:
                    resp = self.get_url(cat_url, impersonate="chrome120", timeout=15)
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for card in soup.select("article.lst-card"):
                        title_a = card.select_one("h2.lst-card__title a[href]")
                        if not title_a:
                            continue
                        title = title_a.get_text(" ", strip=True)
                        href = title_a.get("href", "")
                        link = urllib.parse.urljoin("https://dailyremote.com", href)
                        if not title or link in seen_urls:
                            continue

                        byline = card.select_one(".lst-card__byline")
                        byline_parts = [
                            sp.get_text(" ", strip=True)
                            for sp in (byline.find_all("span", recursive=False) if byline else [])
                            if sp.get_text(" ", strip=True) and sp.get_text(" ", strip=True) != "\u00b7"
                        ]
                        comp = "DailyRemote Employer"
                        raw_date = ""
                        for part in byline_parts:
                            p_low = part.lower()
                            if "ago" in p_low or p_low in ("today", "yesterday", "just now"):
                                raw_date = part
                            elif p_low not in ("full time", "part time", "contract", "freelance", "internship", "company hidden"):
                                comp = part

                        pub_date = normalize_date(raw_date)
                        if not self.accepts_date(raw_date or pub_date):
                            continue

                        pills = [p.get_text(" ", strip=True) for p in card.select(".lst-card__meta .lst-pill") if p.get_text(" ", strip=True)]
                        raw_loc = pills[0] if pills else "Worldwide"
                        loc_str = raw_loc if "remote" in raw_loc.lower() else f"Remote ({raw_loc})"
                        salary = ""
                        for p in pills[1:]:
                            if "$" in p or "per year" in p.lower() or "per hour" in p.lower() or "per month" in p.lower():
                                salary = p
                                break

                        summary_el = card.select_one(".lst-card__summary")
                        tags = [t.get_text(" ", strip=True) for t in card.select(".lst-card__tags .lst-tag")]
                        desc = " | ".join(filter(None, [
                            summary_el.get_text(" ", strip=True) if summary_el else "",
                            ", ".join(tags),
                        ]))

                        if not self.accepts_opportunity(title, desc):
                            continue
                        if not is_work_authorized_location(loc_str, title, self.platform, desc):
                            continue

                        seen_urls.add(link)
                        all_jobs.append(Job(
                            title=title,
                            company=comp,
                            location=loc_str,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary=salary,
                            role_category=self.job_role(title, desc),
                            experience_level=classify_experience_level(title, desc, salary=salary),
                            description=desc,
                            date_posted=raw_date or pub_date,
                        ))
                except Exception as exc:
                    self.last_error = str(exc) or type(exc).__name__
                    logger.warning(f"[{self.platform}] fetch notice: {self.last_error}")

            DailyRemoteConnector._cached_jobs = all_jobs
            DailyRemoteConnector._last_fetch = now if (all_jobs or not self.last_error) else 0
            DailyRemoteConnector._cached_window = window_key

        cached = DailyRemoteConnector._cached_jobs or []
        if not query:
            return cached
        q_lower = query.strip().lower()
        return [
            j for j in cached
            if q_lower in j.title.lower() or q_lower in (j.description or "").lower()
        ]


class RealWorkFromAnywhereConnector(NewPlatformConnectorMixin, BaseConnector):
    platform = "Real Work From Anywhere"
    tier = 2
    is_feed = True
    revision = 1
    _cached_jobs = None
    _last_fetch = 0
    _cached_window = None

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        import time
        from bs4 import BeautifulSoup

        now = time.time()
        window_key = (self.window_days, self._effective_since())
        if (
            RealWorkFromAnywhereConnector._cached_jobs is None
            or (now - RealWorkFromAnywhereConnector._last_fetch > 180)
            or RealWorkFromAnywhereConnector._cached_window != window_key
        ):
            all_jobs: List[Job] = []
            seen_urls = set()
            try:
                resp = self.get_url("https://www.realworkfromanywhere.com/", impersonate="chrome120", timeout=15)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.select("a[href^='/jobs/']"):
                        href = a.get("href", "")
                        link = urllib.parse.urljoin("https://www.realworkfromanywhere.com", href)
                        if not href or link in seen_urls:
                            continue
                        h3 = a.find("h3")
                        title = h3.get_text(" ", strip=True) if h3 else ""
                        if not title:
                            continue
                        p_comp = a.find("p")
                        comp = p_comp.get_text(" ", strip=True) if p_comp else "Work From Anywhere Company"

                        badge_date = ""
                        raw_badge = ""
                        for sp in a.find_all("span"):
                            txt = sp.get_text(" ", strip=True)
                            if txt.lower() == "new":
                                raw_badge = "today"
                                badge_date = normalize_date("today")
                                break
                            if "ago" in txt.lower() or txt.lower() in ("today", "yesterday"):
                                badge_date = normalize_date(txt)
                                if badge_date:
                                    raw_badge = txt
                                    break
                        if not self.accepts_date(raw_badge or badge_date):
                            continue

                        badges = [b.get_text(" ", strip=True) for b in a.select("span.badge")]
                        loc_str = "Remote (Anywhere in the World)"
                        salary = ""
                        for b in badges:
                            if "$" in b or "usd" in b.lower() or "eur" in b.lower():
                                salary = b
                            elif "anywhere" in b.lower() or "world" in b.lower():
                                loc_str = f"Remote ({b})"

                        desc = " | ".join(filter(None, [title, comp, ", ".join(badges)]))
                        if not self.accepts_opportunity(title, desc):
                            continue
                        if not is_work_authorized_location(loc_str, title, self.platform, desc):
                            continue

                        seen_urls.add(link)
                        all_jobs.append(Job(
                            title=title,
                            company=comp,
                            location=loc_str,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary=salary,
                            role_category=self.job_role(title, desc),
                            experience_level=classify_experience_level(title, desc, salary=salary),
                            description=desc,
                            date_posted=raw_badge or badge_date,
                        ))
                else:
                    self.last_error = f"Real Work From Anywhere HTTP {resp.status_code}"
            except Exception as exc:
                self.last_error = str(exc) or type(exc).__name__
                logger.warning(f"[{self.platform}] fetch notice: {self.last_error}")

            RealWorkFromAnywhereConnector._cached_jobs = all_jobs
            RealWorkFromAnywhereConnector._last_fetch = now if (all_jobs or not self.last_error) else 0
            RealWorkFromAnywhereConnector._cached_window = window_key

        cached = RealWorkFromAnywhereConnector._cached_jobs or []
        if not query:
            return cached
        q_lower = query.strip().lower()
        return [
            j for j in cached
            if q_lower in j.title.lower() or q_lower in (j.description or "").lower()
        ]


class YCombinatorConnector(NewPlatformConnectorMixin, BaseConnector):
    platform = "Y Combinator"
    tier = 2
    is_feed = True
    revision = 2
    _cached_jobs = None
    _last_fetch = 0
    _cached_window = None

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        import time
        from bs4 import BeautifulSoup

        now = time.time()
        window_key = (self.window_days, self._effective_since())
        if (
            YCombinatorConnector._cached_jobs is None
            or (now - YCombinatorConnector._last_fetch > 180)
            or YCombinatorConnector._cached_window != window_key
        ):
            all_jobs: List[Job] = []
            seen_urls = set()
            feed_urls = [
                "https://hnrss.org/whoishiring/jobs.jsonfeed?q=remote&count=50",
                "https://hnrss.org/jobs.jsonfeed?count=50",
            ]
            for url in feed_urls:
                try:
                    raw_json = ""
                    try:
                        req = urllib.request.Request(url, headers=HEADERS)
                        with self.open_url(req, timeout=15) as resp:
                            raw_json = resp.read().decode("utf-8")
                    except Exception:
                        c_resp = self.get_url(url, impersonate="chrome120", timeout=15)
                        if c_resp.status_code == 200:
                            raw_json = c_resp.text
                        else:
                            continue

                    data = json.loads(raw_json) if raw_json else {}
                    for item in (data.get("items") or []):
                        if not isinstance(item, dict):
                            continue
                        raw_pub = str(item.get("date_published") or "")
                        pub_date = normalize_date(raw_pub)
                        if not self.accepts_date(raw_pub or pub_date):
                            continue
                        link = str(item.get("url") or item.get("id") or "").strip()
                        if not link or link in seen_urls:
                            continue
                        raw_title = str(item.get("title") or "").strip()
                        content_html = str(item.get("content_html") or "")
                        soup = BeautifulSoup(content_html, "html.parser")
                        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if p.get_text(" ", strip=True)]
                        full_text = "\n".join(paragraphs) if paragraphs else soup.get_text(" ", strip=True)

                        if "|" in full_text:
                            header_line = paragraphs[0] if paragraphs else full_text.split("\n")[0]
                            parts = [p.strip() for p in header_line.split("|") if p.strip()]
                            if len(parts) < 2:
                                continue
                            comp = parts[0][:80]
                            title = parts[1][:120]
                            for part in parts[1:]:
                                if any(k in part.lower() for k in ("engineer", "developer", "programmer", "architect", "qa", "devops", "sdet", "full stack", "frontend", "backend", "android", "mobile")):
                                    title = part[:120]
                                    break
                            loc_str = "Remote (Worldwide)"
                            salary = ""
                            for part in parts[1:]:
                                p_low = part.lower()
                                if "remote" in p_low or "worldwide" in p_low or "anywhere" in p_low or "onsite" in p_low:
                                    loc_str = part[:100]
                                if "$" in part or "eur" in p_low or "gbp" in p_low:
                                    salary = part[:80]
                        elif " is hiring" in raw_title.lower():
                            # Official daily YC job story: e.g. "Nango (YC W23) Is Hiring Across Eng..."
                            m_yc = re.split(r"\s+is\s+hiring\s*", raw_title, maxsplit=1, flags=re.I)
                            comp = m_yc[0].strip() if m_yc else "Y Combinator Startup"
                            role_suffix = m_yc[1].strip() if len(m_yc) > 1 and m_yc[1].strip() else "Software Engineer"
                            if role_suffix.lower().startswith("a ") or role_suffix.lower().startswith("an "):
                                role_suffix = role_suffix.split(" ", 1)[1].strip()
                            if "across eng" in role_suffix.lower() or role_suffix.lower().startswith("in "):
                                title = f"Software Engineer ({role_suffix})"
                            else:
                                title = role_suffix
                            loc_str = "Remote (Worldwide)" if " in " not in raw_title.lower() else raw_title
                            salary = ""
                            full_text = f"{raw_title}. {full_text}".strip()
                        else:
                            continue

                        if not self.accepts_opportunity(title, full_text):
                            continue
                        if not is_work_authorized_location(loc_str, title, self.platform, full_text):
                            continue

                        seen_urls.add(link)
                        all_jobs.append(Job(
                            title=title,
                            company=comp,
                            location=loc_str,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary=salary,
                            role_category=self.job_role(title, full_text),
                            experience_level=classify_experience_level(title, full_text, salary=salary),
                            description=full_text,
                            date_posted=raw_pub or pub_date,
                        ))
                except Exception as exc:
                    self.last_error = str(exc) or type(exc).__name__
                    logger.warning(f"[{self.platform}] fetch notice: {self.last_error}")

            YCombinatorConnector._cached_jobs = all_jobs
            YCombinatorConnector._last_fetch = now if (all_jobs or not self.last_error) else 0
            YCombinatorConnector._cached_window = window_key

        cached = YCombinatorConnector._cached_jobs or []
        if not query:
            return cached
        q_lower = query.strip().lower()
        return [
            j for j in cached
            if q_lower in j.title.lower() or q_lower in (j.description or "").lower()
        ]
