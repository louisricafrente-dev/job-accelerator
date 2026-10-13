import json
import urllib.request
import xml.etree.ElementTree as ET
from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job
from src.classifier import classify_experience_level, classify_role

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

class RemoteOKConnector(BaseConnector):
    platform = "Remote OK"
    tier = 3

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
                    company = item.get("company", "")
                    link = item.get("url", "")
                    salary = ""
                    if item.get("salary_min") and item.get("salary_max"):
                        salary = f"${item['salary_min']:,} - ${item['salary_max']:,}"
                    job = Job(
                        title=title,
                        company=company,
                        location=item.get("location", "Remote Worldwide"),
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=item.get("date", "")[:10]
                    )
                    jobs.append(job)
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class WeWorkRemotelyConnector(BaseConnector):
    platform = "We Work Remotely"
    tier = 3

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        feed_urls = [
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"
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
                        raw_title = title_elem.text if title_elem is not None and title_elem.text else ""
                        parts = raw_title.split(":", 1)
                        company = parts[0].strip() if len(parts) > 1 else "Unknown"
                        title = parts[1].strip() if len(parts) > 1 else raw_title

                        job = Job(
                            title=title,
                            company=company,
                            location="Remote Worldwide",
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary="",
                            role_category=classify_role(title),
                            experience_level=classify_experience_level(title),
                            date_posted=pub_date.text.strip() if pub_date is not None and pub_date.text else ""
                        )
                        jobs.append(job)
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
                        if not title:
                            continue
                        # If query provided, check keyword relevance
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
                            date_posted=str(item.get("postedDate", ""))[:10]
                        ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class WellfoundConnector(BaseConnector):
    platform = "Wellfound"
    tier = 2

    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        jobs: List[Job] = []
        try:
            url = "https://remotive.com/api/remote-jobs?category=software-dev&limit=25"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    if query and query.lower() not in title.lower():
                        continue
                    company = item.get("company_name", "Startup")
                    link = item.get("url", "https://wellfound.com")
                    salary = item.get("salary", "")
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location="Remote / Global",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=str(item.get("publication_date", ""))[:10]
                    ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class FounditConnector(BaseConnector):
    platform = "Foundit"
    tier = 2
    _cached_data = None
    _last_fetch = 0

    def fetch(self, query: str = "developer", location: str = "Philippines") -> List[Job]:
        import time
        jobs: List[Job] = []
        now = time.time()
        # Cache Jobicy feed for 60 seconds to prevent 429 Too Many Requests
        if not FounditConnector._cached_data or (now - FounditConnector._last_fetch > 60):
            try:
                url = "https://jobicy.com/api/v2/remote-jobs?count=50&geo=apac"
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    FounditConnector._cached_data = json.loads(resp.read().decode("utf-8")).get("jobs", [])
                    FounditConnector._last_fetch = now
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    logger.warning("[Foundit] Rate limited by upstream API (HTTP 429). Skipping.")
                else:
                    logger.warning(f"[Foundit] HTTP error: {e}")
                return []
            except Exception as e:
                logger.warning(f"[{self.platform}] fetch failed: {e}")
                return []

        raw_list = FounditConnector._cached_data or []
        q_lower = (query or "").lower().strip()
        for item in raw_list:
            title = item.get("jobTitle", "")
            if q_lower and q_lower not in title.lower():
                continue
            company = item.get("companyName", "Tech Enterprise")
            link = item.get("url", "https://foundit.com.ph")
            sal = f"{item.get('annualSalaryMin', '')} - {item.get('annualSalaryMax', '')} {item.get('salaryCurrency', '')}".strip()
            jobs.append(Job(
                title=title,
                company=company,
                location=item.get("jobGeo", "APAC / Philippines"),
                platform=self.platform,
                tier=self.tier,
                job_url=link,
                salary=sal if sal != "-" else "",
                role_category=classify_role(title),
                experience_level=classify_experience_level(title),
                date_posted=str(item.get("pubDate", ""))
            ))
        return jobs

class UpworkConnector(BaseConnector):
    platform = "Upwork"
    tier = 4
    _cached_data = None
    _last_fetch = 0

    def fetch(self, query: str = "developer", location: str = "") -> List[Job]:
        import time
        jobs: List[Job] = []
        now = time.time()
        # Cache Jobicy contract engineering feed for 60 seconds to prevent 429 Too Many Requests
        if not UpworkConnector._cached_data or (now - UpworkConnector._last_fetch > 60):
            try:
                url = "https://jobicy.com/api/v2/remote-jobs?count=50&industry=engineering"
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    UpworkConnector._cached_data = json.loads(resp.read().decode("utf-8")).get("jobs", [])
                    UpworkConnector._last_fetch = now
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    logger.warning("[Upwork] Rate limited by upstream API (HTTP 429). Skipping.")
                else:
                    logger.warning(f"[Upwork] HTTP error: {e}")
                return []
            except Exception as e:
                logger.warning(f"[{self.platform}] fetch failed: {e}")
                return []

        raw_list = UpworkConnector._cached_data or []
        q_lower = (query or "").lower().strip()
        for item in raw_list:
            title = item.get("jobTitle", "")
            if q_lower and q_lower not in title.lower():
                continue
            company = item.get("companyName", "Contract Client")
            link = item.get("url", "https://www.upwork.com")
            sal = f"{item.get('annualSalaryMin', '')} - {item.get('annualSalaryMax', '')}".strip()
            jobs.append(Job(
                title=f"[Contract] {title}",
                company=company,
                location="Remote / Contract",
                platform=self.platform,
                tier=self.tier,
                job_url=link,
                salary=sal if sal != "-" else "",
                role_category=classify_role(title),
                experience_level=classify_experience_level(title),
                date_posted=str(item.get("pubDate", ""))
            ))
        return jobs

class RemotiveConnector(BaseConnector):
    platform = "Remotive"
    tier = 3
    is_feed = True

    def fetch(self, query: str = "software-dev", location: str = "remote") -> List[Job]:
        jobs: List[Job] = []
        try:
            url = "https://remotive.com/api/remote-jobs?category=software-dev&limit=40"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    if not title:
                        continue
                    company = item.get("company_name", "Remote Tech")
                    link = item.get("url", "https://remotive.com")
                    sal = str(item.get("salary") or "")
                    loc = item.get("candidate_required_location") or "Remote Worldwide"
                    pub = str(item.get("publication_date", ""))[:10]
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=loc,
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=sal,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=pub
                    ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class HimalayasConnector(BaseConnector):
    platform = "Himalayas"
    tier = 3
    is_feed = True

    def fetch(self, query: str = "developer", location: str = "remote") -> List[Job]:
        jobs: List[Job] = []
        try:
            url = "https://himalayas.app/jobs/api?limit=35"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    if not title:
                        continue
                    company = item.get("companyName", "Tech Enterprise")
                    link = item.get("applicationLink") or "https://himalayas.app"
                    sal_min = item.get("minSalary")
                    sal_max = item.get("maxSalary")
                    sal = f"${sal_min:,} - ${sal_max:,}" if sal_min and sal_max else ""
                    pub = str(item.get("pubDate", ""))[:10]
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location="Remote Worldwide",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=sal,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=pub
                    ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs



