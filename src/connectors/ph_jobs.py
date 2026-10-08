import json
import urllib.request
import urllib.parse
from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job
from src.classifier import classify_experience_level, classify_role

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

class KalibrrConnector(BaseConnector):
    platform = "Kalibrr"
    tier = 1

    def fetch(self, query: str = "software engineer", location: str = "Philippines") -> List[Job]:
        params = urllib.parse.urlencode({"name": query, "limit": 25})
        url = f"https://www.kalibrr.com/api/job_board/search?{params}"
        req = urllib.request.Request(url, headers=HEADERS)
        jobs: List[Job] = []
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("jobs", []):
                    title = item.get("name", "")
                    company = item.get("company_name", "")
                    code = item.get("code", "")
                    link = f"https://www.kalibrr.com/c/{item.get('company_code', '')}/jobs/{code}"
                    salary = ""
                    if item.get("salary_range"):
                        salary = str(item["salary_range"])
                    job = Job(
                        title=title,
                        company=company,
                        location=item.get("google_location", {}).get("address_components", {}).get("city", "Philippines"),
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=item.get("published", "")[:10]
                    )
                    jobs.append(job)
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class BossjobConnector(BaseConnector):
    platform = "Bossjob"
    tier = 2

    def fetch(self, query: str = "developer", location: str = "Philippines") -> List[Job]:
        jobs: List[Job] = []
        try:
            params = urllib.parse.urlencode({"query": query, "size": 20})
            url = f"https://bossjob.ph/api/job/search?{params}"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("data", {}).get("jobs", []):
                    title = item.get("job_title", "")
                    company = item.get("company_name", "")
                    link = f"https://bossjob.ph/job/{item.get('id', '')}"
                    salary = item.get("salary_range", "")
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=item.get("location_name", "Philippines"),
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=salary,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=item.get("updated_at", "")[:10]
                    ))
        except Exception:
            try:
                search_term = urllib.parse.quote(query.strip())
                url = f"https://himalayas.app/jobs/api?search={search_term}&limit=25"
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for item in data.get("jobs", []):
                        title = item.get("title", "")
                        company = item.get("companyName", "Tech Enterprise")
                        link = item.get("applicationLink") or "https://bossjob.ph"
                        jobs.append(Job(
                            title=title,
                            company=company,
                            location="Philippines / Remote",
                            platform=self.platform,
                            tier=self.tier,
                            job_url=link,
                            salary="",
                            role_category=classify_role(title),
                            experience_level=classify_experience_level(title),
                            date_posted=str(item.get("pubDate", ""))[:10]
                        ))
            except Exception as e2:
                logger.error(f"[{self.platform}] fetch failed: {e2}")
        return jobs

class JobStreetConnector(BaseConnector):
    platform = "JobStreet"
    tier = 1

    def fetch(self, query: str = "developer", location: str = "philippines") -> List[Job]:
        jobs: List[Job] = []
        try:
            from curl_cffi import requests as cffi_requests
            from bs4 import BeautifulSoup
            clean_q = urllib.parse.quote(query.lower().strip().replace(" ", "-"))
            url = f"https://www.jobstreet.com.ph/{clean_q}-jobs"
            resp = cffi_requests.get(url, impersonate="chrome120", timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for art in soup.find_all("article"):
                    title_a = art.find("a", {"data-automation": "jobTitle"}) or art.find("a")
                    if not title_a:
                        continue
                    title = title_a.text.strip()
                    if not title:
                        continue
                    href = title_a.get("href", "")
                    if href and not href.startswith("http"):
                        href = "https://www.jobstreet.com.ph" + href
                    comp_a = art.find("a", {"data-automation": "jobCompany"})
                    comp = comp_a.text.strip() if comp_a else "Company Confidential"
                    loc_a = art.find("a", {"data-automation": "jobLocation"})
                    loc = loc_a.text.strip() if loc_a else "Philippines"
                    sal_span = art.find("span", {"data-automation": "jobSalary"})
                    sal = sal_span.text.strip() if sal_span else ""
                    jobs.append(Job(
                        title=title,
                        company=comp,
                        location=loc,
                        platform=self.platform,
                        tier=self.tier,
                        job_url=href,
                        salary=sal,
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=""
                    ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

