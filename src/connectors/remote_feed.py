import json
import urllib.request
import xml.etree.ElementTree as ET
from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job, is_within_14_days
from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

class RemoteOKConnector(BaseConnector):
    platform = "Remote OK"
    tier = 3
    is_feed = True

    def fetch(self, query: str = "developer", location: str = "remote") -> List[Job]:
        url = "https://remoteok.com/api"
        req = urllib.request.Request(url, headers=HEADERS)
        jobs: List[Job] = []
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data:
                    if not isinstance(item, dict) or "position" not in item:
                        continue
                    title = item.get("position", "")
                    if not title or not is_relevant_opportunity(title, ""):
                        continue
                    pub_date = item.get("date", "")[:10]
                    if not is_within_14_days(pub_date):
                        continue
                    company = item.get("company", "")
                    link = item.get("url", "")
                    salary = ""
                    if item.get("salary_min") and item.get("salary_max"):
                        salary = f"${item['salary_min']:,} - ${item['salary_max']:,}"
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=item.get("location", "Remote Worldwide"),
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=pub_date
                    ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class WeWorkRemotelyConnector(BaseConnector):
    platform = "We Work Remotely"
    tier = 3
    is_feed = True

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        feed_urls = [
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
            "https://weworkremotely.com/categories/remote-customer-support-jobs.rss"
        ]
        jobs: List[Job] = []
        seen_links = set()

        for rss_url in feed_urls:
            try:
                req = urllib.request.Request(rss_url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=10) as resp:
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
                        if not is_within_14_days(pub_text):
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
                            location="Remote Worldwide",
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary="",
                            role_category=classify_role(title, desc_text),
                            experience_level=classify_experience_level(title, desc_text),
                            date_posted=pub_text
                        ))
            except Exception as e:
                logger.warning(f"[{self.platform}] feed notice for {rss_url}: {e}")
        return jobs

class ArcConnector(BaseConnector):
    platform = "Arc"
    tier = 3

    def fetch(self, query: str = "developer", location: str = "remote") -> List[Job]:
        jobs: List[Job] = []
        try:
            from curl_cffi import requests as cffi_requests
            from bs4 import BeautifulSoup
            r = cffi_requests.get("https://arc.dev/remote-jobs", impersonate="chrome120", timeout=12)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                next_data = soup.find("script", {"id": "__NEXT_DATA__"})
                if next_data and next_data.string:
                    data = json.loads(next_data.string)
                    props = data.get("props", {}).get("pageProps", {})
                    raw_jobs = props.get("arcJobs", []) + props.get("externalJobs", [])
                    for item in raw_jobs:
                        title = item.get("title", "")
                        if not title or not is_relevant_opportunity(title, ""):
                            continue
                        pub_date = str(item.get("postedDate", ""))[:10]
                        if not is_within_14_days(pub_date):
                            continue
                        comp_name = item.get("companyName") or "Tech Company"
                        if query:
                            q_lower = query.lower()
                            if q_lower not in title.lower() and q_lower not in comp_name.lower():
                                continue
                        slug = item.get("slug", "")
                        link = f"https://arc.dev/remote-jobs/{slug}" if slug else (item.get("url") or "https://arc.dev/remote-jobs")
                        salary = str(item.get("salaryRange") or "")
                        jobs.append(Job(
                            title=title,
                            company=comp_name,
                            location="Remote Worldwide",
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary=salary,
                            role_category=classify_role(title),
                            experience_level=classify_experience_level(title),
                            date_posted=pub_date
                        ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class RemotiveConnector(BaseConnector):
    platform = "Remotive"
    tier = 3
    is_feed = True

    def fetch(self, query: str = "software-dev", location: str = "remote") -> List[Job]:
        jobs: List[Job] = []
        categories = ["software-dev", "qa", "data", "customer-support"]
        seen_urls = set()
        for cat in categories:
            try:
                url = f"https://remotive.com/api/remote-jobs?category={cat}&limit=50"
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=12) as resp:
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
                        pub = str(item.get("publication_date", ""))[:10]
                        if not is_within_14_days(pub):
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
                            date_posted=pub
                        ))
            except Exception as e:
                logger.warning(f"[{self.platform}] fetch notice for category '{cat}': {e}")
        return jobs

class HimalayasConnector(BaseConnector):
    platform = "Himalayas"
    tier = 3
    is_feed = True

    def fetch(self, query: str = "developer", location: str = "remote") -> List[Job]:
        jobs: List[Job] = []
        try:
            url = "https://himalayas.app/jobs/api?limit=100"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    desc = item.get("excerpt", "") or item.get("description", "")
                    if not title or not is_relevant_opportunity(title, desc):
                        continue
                    pub = str(item.get("pubDate", ""))[:10]
                    if not is_within_14_days(pub):
                        continue
                    company = item.get("companyName", "Tech Enterprise")
                    link = item.get("applicationLink") or "https://himalayas.app"
                    sal_min = item.get("minSalary")
                    sal_max = item.get("maxSalary")
                    sal = f"${sal_min:,} - ${sal_max:,}" if sal_min and sal_max else ""
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location="Remote Worldwide",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=sal,
                        role_category=classify_role(title, desc),
                        experience_level=classify_experience_level(title, desc),
                        date_posted=pub
                    ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class JobicyConnector(BaseConnector):
    platform = "Jobicy"
    tier = 3
    is_feed = True
    _cached_data = None
    _last_fetch = 0

    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        import time
        jobs: List[Job] = []
        now = time.time()
        if not JobicyConnector._cached_data or (now - JobicyConnector._last_fetch > 60):
            try:
                url = "https://jobicy.com/api/v2/remote-jobs?count=50&tag=dev"
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    JobicyConnector._cached_data = json.loads(resp.read().decode("utf-8")).get("jobs", [])
                    JobicyConnector._last_fetch = now
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    logger.warning("[Jobicy] Rate limited by upstream API (HTTP 429). Skipping.")
                else:
                    logger.warning(f"[Jobicy] HTTP error: {e}")
                return []
            except Exception as e:
                logger.warning(f"[{self.platform}] fetch failed: {e}")
                return []

        raw_list = JobicyConnector._cached_data or []
        for item in raw_list:
            title = item.get("jobTitle", "")
            if not title or not is_relevant_opportunity(title, ""):
                continue
            pub_date = str(item.get("pubDate", ""))
            if not is_within_14_days(pub_date):
                continue
            company = item.get("companyName", "Tech Employer")
            link = item.get("url", "https://jobicy.com")
            sal = f"{item.get('annualSalaryMin', '')} - {item.get('annualSalaryMax', '')} {item.get('salaryCurrency', '')}".strip()
            jobs.append(Job(
                title=title,
                company=company,
                location=item.get("jobGeo", "Remote Worldwide"),
                platform=self.platform,
                tier=self.tier,
                job_url=link,
                salary=sal if sal != "-" else "",
                role_category=classify_role(title),
                experience_level=classify_experience_level(title),
                date_posted=pub_date
            ))
        return jobs

class FreelancerConnector(BaseConnector):
    platform = "Freelancer"
    tier = 2

    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        import datetime
        jobs: List[Job] = []
        try:
            q_enc = urllib.parse.quote(query.strip())
            url = f"https://www.freelancer.com/api/projects/0.1/projects/active?query={q_enc}&compact=true&limit=25"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for p in data.get("result", {}).get("projects", []):
                    title = p.get("title", "")
                    desc = p.get("preview_description", "")
                    if not title or not is_relevant_opportunity(title, desc):
                        continue
                    sub_date = p.get("submitdate")
                    pub_date = datetime.datetime.fromtimestamp(sub_date).strftime("%Y-%m-%d") if sub_date else ""
                    if not is_within_14_days(pub_date):
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
                        date_posted=pub_date
                    ))
        except Exception as e:
            logger.warning(f"[{self.platform}] fetch failed for query '{query}': {e}")
        return jobs

class UpworkConnector(BaseConnector):
    platform = "Upwork"
    tier = 2

    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        import os
        jobs: List[Job] = []
        feed_url = os.environ.get("UPWORK_FEED_URL", "").strip()
        if not feed_url:
            q_enc = urllib.parse.quote(query.strip())
            feed_url = f"https://www.upwork.com/ab/feed/jobs/rss?q={q_enc}&sort=recency"

        try:
            from curl_cffi import requests as cffi_requests
            import xml.etree.ElementTree as ET
            resp = cffi_requests.get(feed_url, impersonate="chrome120", timeout=12)
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
                    if not is_within_14_days(pub):
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
                        date_posted=pub
                    ))
        except Exception as e:
            logger.warning(f"[{self.platform}] fetch notice: {e}")
        return jobs

