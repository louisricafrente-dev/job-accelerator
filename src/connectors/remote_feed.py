import json
import urllib.request
import xml.etree.ElementTree as ET
from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job, is_today_or_yesterday, normalize_date, scrape_date_window
from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity, is_work_authorized_location

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

class RemoteOKConnector(BaseConnector):
    platform = "Remote OK"
    tier = 3
    is_feed = True
    revision = 2
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
                    if not title or not is_relevant_opportunity(title, ""):
                        continue
                    pub_date = normalize_date(item.get("date", ""))
                    if not is_today_or_yesterday(pub_date):
                        continue
                    company = item.get("company", "")
                    link = item.get("url", "")
                    salary = ""
                    if item.get("salary_min") and item.get("salary_max"):
                        salary = f"${item['salary_min']:,} - ${item['salary_max']:,}"
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=item.get("location") or "Remote (location unverified)",
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
                        if not is_today_or_yesterday(pub_text):
                            continue

                        raw_title = title_elem.text if title_elem is not None and title_elem.text else ""
                        parts = raw_title.split(":", 1)
                        company = parts[0].strip() if len(parts) > 1 else "Unknown"
                        title = parts[1].strip() if len(parts) > 1 else raw_title
                        if not title:
                            continue

                        desc_elem = item.find("description")
                        desc_text = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""

                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=item.findtext("region") or "Remote (location unverified)",
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
                        if not is_today_or_yesterday(pub_date):
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
                        jobs.append(Job(
                            title=title,
                            company=comp_name,
                            location=item.get("location") if isinstance(item.get("location"), str) else "Remote (location unverified)",
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

class RemotiveConnector(BaseConnector):
    platform = "Remotive"
    tier = 3
    is_feed = True
    revision = 3
    coverage_limit = "Coverage limited: Remotive public feed is delayed 24 hours and has no verified date-range pagination"

    def fetch(self, query: str = "software-dev", location: str = "remote") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        categories = [None]
        seen_urls = set()
        for cat in categories:
            try:
                # The public API has no date-range parameter; it returns newest first.
                url = "https://remotive.com/api/remote-jobs?limit=100"
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
                        pub = normalize_date(item.get("publication_date", ""))
                        if not is_today_or_yesterday(pub):
                            continue
                        company = item.get("company_name", "Remote Tech")
                        sal = str(item.get("salary") or "")
                        loc = item.get("candidate_required_location") or "Remote Worldwide"
                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=loc,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary=sal,
                            role_category=classify_role(title, desc),
                            experience_level=classify_experience_level(title, desc),
                            description=desc,
                            date_posted=pub
                        ))
            except Exception as e:
                self.last_error = str(e) or type(e).__name__
                logger.warning(f"[{self.platform}] fetch notice for category '{cat}': {e}")
        return jobs

class HimalayasConnector(BaseConnector):
    platform = "Himalayas"
    tier = 3
    is_feed = True
    revision = 3
    checkpointed_feed = True

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
                self.finish_page(state, [item.get("guid") or item.get("applicationLink") or "" for item in items],
                                 [item.get("pubDate") for item in items], bool(cursor), ordered=True)
                if not cursor and data.get("totalCount", 0) > data.get("offset", 0) + len(items):
                    self.coverage_warning = "Coverage limited: Himalayas omitted its continuation cursor before the feed ended"
                state.update(cursor=cursor, total=data.get("totalCount", 0))
                for item in items:
                    title = item.get("title", "")
                    desc = item.get("excerpt", "") or item.get("description", "")
                    if not title or not is_relevant_opportunity(title, desc):
                        continue
                    pub = normalize_date(item.get("pubDate", ""))
                    if not is_today_or_yesterday(pub):
                        continue
                    company = item.get("companyName", "Tech Enterprise")
                    link = item.get("applicationLink") or "https://himalayas.app"
                    sal_min = item.get("minSalary")
                    sal_max = item.get("maxSalary")
                    sal = f"${sal_min:,} - ${sal_max:,}" if sal_min and sal_max else ""
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=", ".join(str(loc.get("name") or loc.get("country") or "") if isinstance(loc, dict) else str(loc)
                                           for loc in (item.get("locationRestrictions") or [])) or "Remote (location unverified)",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=sal,
                        role_category=classify_role(title, desc),
                        experience_level=classify_experience_level(title, desc),
                        description=desc,
                        date_posted=pub
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
            if not is_today_or_yesterday(pub_date):
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
            jobs.append(Job(
                title=title,
                company=company,
                location=item.get("jobGeo", "Remote Worldwide"),
                platform=self.platform,
                tier=self.tier,
                job_url=link,
                salary=sal,
                description=description,
                role_category=classify_role(title),
                experience_level=classify_experience_level(title, description),
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
            start, end = scrape_date_window()
            params = urllib.parse.urlencode({"query": query.strip(), "compact": "true", "limit": 25,
                                             "offset": offset,
                                             "from_time": int(start.timestamp()), "to_time": int(end.timestamp()) - 1})
            url = f"https://www.freelancer.com/api/projects/0.1/projects/active?{params}"
            req = urllib.request.Request(url, headers=HEADERS)
            with self.open_url(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                payload = data.get("result", {})
                items = payload.get("projects")
                if not isinstance(items, list):
                    raise RuntimeError("Freelancer returned an invalid search response")
                total = payload.get("total_count")
                more = offset + len(items) < total if isinstance(total, int) else len(items) == 25
                self.finish_page(state, [str(item.get("id") or item.get("seo_url") or "") for item in items],
                                 [item.get("submitdate") for item in items], more)
                state["offset"] = offset + 25 if more else 0
                for p in items:
                    title = p.get("title", "")
                    desc = p.get("preview_description", "")
                    if not title or not is_relevant_opportunity(title, desc):
                        continue
                    sub_date = p.get("submitdate")
                    pub_date = normalize_date(int(sub_date)) if sub_date else ""
                    if not is_today_or_yesterday(pub_date):
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
                        role_category=classify_role(title, desc),
                        experience_level=classify_experience_level(title, desc),
                        description=desc,
                        date_posted=pub_date
                    ))
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.warning(f"[{self.platform}] fetch failed for query '{query}': {e}")
        return jobs

class UpworkConnector(BaseConnector):
    platform = "Upwork"
    tier = 2
    is_feed = True
    revision = 3
    coverage_limit = "Coverage limited: once-daily Upwork/flconsole can return only the last 30 minutes (up to 10 jobs), not two-day backfill"

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
            return fetch_jobs(self, limit=10) if self.db_path else fetch_jobs(self)
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
                    if not is_today_or_yesterday(pub):
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



class WellfoundConnector(BaseConnector):
    platform = "Wellfound"
    tier = 2
    is_feed = True
    revision = 2
    coverage_limit = "Coverage limited: Wellfound role landing pages do not expose verified publication-date pagination; authenticated access may be required"
    _cached_jobs = None
    _last_fetch = 0

    ROLES = ["software-engineer", "full-stack-engineer", "android-developer", "web-developer"]

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        import time
        import datetime
        from bs4 import BeautifulSoup

        now = time.time()
        if WellfoundConnector._cached_jobs is None or (now - WellfoundConnector._last_fetch > 120):
            all_jobs: List[Job] = []
            seen_ids = set()

            for role in self.ROLES:
                url = f"https://wellfound.com/role/{role}"
                try:
                    req = urllib.request.Request(url, headers=HEADERS)
                    with self.open_url(req, timeout=10) as resp:
                        soup = BeautifulSoup(resp.read().decode("utf-8"), "html.parser")
                        script = soup.find("script", {"id": "__NEXT_DATA__"})
                        if not script or not script.string:
                            continue
                        data = json.loads(script.string)
                        apollo_data = data.get("props", {}).get("pageProps", {}).get("apolloState", {}).get("data", {})

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
                            pub_date = normalize_date(int(ts)) if ts else ""
                            if not is_today_or_yesterday(pub_date):
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
                                experience_level=classify_experience_level(title, desc),
                                description=desc,
                                date_posted=pub_date
                            ))
                except Exception as e:
                    self.last_error = str(e) or type(e).__name__
                    logger.warning(f"[{self.platform}] fetch notice for role '{role}': {e}")

            WellfoundConnector._cached_jobs = all_jobs
            WellfoundConnector._last_fetch = now if not self.last_error else 0

        cached = WellfoundConnector._cached_jobs or []
        if not query:
            return cached

        q_lower = query.strip().lower()
        return [
            j for j in cached
            if q_lower in j.title.lower() or q_lower in (j.description or "").lower() or q_lower in j.company.lower()
        ]


class ContraConnector(BaseConnector):
    platform = "Contra"
    tier = 2
    is_feed = True
    revision = 2
    coverage_limit = "Coverage limited: Contra anonymous page does not expose a verified opportunity feed; authenticated source required"
    _cached_jobs = None
    _last_fetch = 0

    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        self.last_error = ""
        import time
        from bs4 import BeautifulSoup

        now = time.time()
        if ContraConnector._cached_jobs is not None and (now - ContraConnector._last_fetch < 120):
            return ContraConnector._cached_jobs

        jobs: List[Job] = []
        try:
            req = urllib.request.Request("https://contra.com/opportunities", headers=HEADERS)
            with self.open_url(req, timeout=10) as resp:
                soup = BeautifulSoup(resp.read().decode("utf-8"), "html.parser")
                script = soup.find("script", {"id": "vike_pageContext"})
                if script and script.string:
                    data = json.loads(script.string)
                    records = data.get("publicAppConfiguration", {}).get("relayRecordMap", {})
                    for k, v in records.items():
                        typename = v.get("__typename", "")
                        if typename in ["Opportunity", "Project", "Job"]:
                            title = v.get("title") or v.get("name") or ""
                            if not title or not is_relevant_opportunity(title, ""):
                                continue
                            slug = v.get("slug") or ""
                            link = f"https://contra.com/opportunity/{slug}" if slug else "https://contra.com/opportunities"
                            jobs.append(Job(
                                title=title,
                                company="Direct Client (Contra)",
                                location="Remote (location unverified)",
                                platform=self.platform,
                                tier=self.tier,
                                job_url=link,
                                salary="",
                                role_category=classify_role(title),
                                experience_level=classify_experience_level(title),
                                date_posted=v.get("datePosted") or v.get("publishedAt") or ""
                            ))
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.warning(f"[{self.platform}] fetch notice: {e}")

        ContraConnector._cached_jobs = jobs
        ContraConnector._last_fetch = now if not self.last_error else 0
        return jobs


class FlexJobsConnector(BaseConnector):
    platform = "FlexJobs"
    tier = 2
    is_feed = True
    revision = 4
    coverage_limit = "Coverage limited: FlexJobs requires an accessible authorized search/feed with publication dates and pagination"
    _cached_jobs = None
    _last_fetch = 0

    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        self.last_error = ""
        import os
        import time

        now = time.time()
        if FlexJobsConnector._cached_jobs is not None and (now - FlexJobsConnector._last_fetch < 120):
            return FlexJobsConnector._cached_jobs

        jobs: List[Job] = []
        custom_feed = os.environ.get("FLEXJOBS_FEED_URL", "").strip()
        feed_url = custom_feed or "https://www.flexjobs.com/search?search=software"

        try:
            from bs4 import BeautifulSoup
            resp = self.get_url(feed_url, impersonate="chrome120", timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.select("li.job, div.job-tile, .job-item"):
                    title_elem = item.select_one("a.job-title, .job-title a, h5 a")
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    if not title or not is_relevant_opportunity(title, ""):
                        continue
                    link = title_elem.get("href", "")
                    if link and not link.startswith("http"):
                        link = f"https://www.flexjobs.com{link}"
                    comp_elem = item.select_one(".job-company, .company")
                    comp = comp_elem.get_text(strip=True) if comp_elem else "Screened Tech Client"
                    jobs.append(Job(
                        title=title,
                        company=comp,
                        location="Remote (location unverified)",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link or "https://www.flexjobs.com",
                        salary="",
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=(item.select_one("time").get("datetime", "") if item.select_one("time") else "")
                    ))
            elif resp.status_code == 403:
                self.last_error = "Cloudflare Protected (HTTP 403); no undated sitemap fallback"
            else:
                self.last_error = f"FlexJobs HTTP {resp.status_code}"
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.warning(f"[{self.platform}] fetch notice: {e}")

        FlexJobsConnector._cached_jobs = jobs
        FlexJobsConnector._last_fetch = now if not self.last_error else 0
        return jobs
