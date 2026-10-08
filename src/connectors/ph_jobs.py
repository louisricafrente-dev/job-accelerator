import json
import urllib.request
import urllib.parse
from typing import List
from src.connectors.base import BaseConnector
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
        except Exception:
            pass
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
            pass
        return jobs

class JobStreetConnector(BaseConnector):
    platform = "JobStreet"
    tier = 1

    def fetch(self, query: str = "developer", location: str = "philippines") -> List[Job]:
        # JobStreet search parser
        jobs: List[Job] = []
        try:
            params = urllib.parse.urlencode({"keywords": query, "where": location})
            url = f"https://www.jobstreet.com.ph/api/job/search?{params}"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("data", []):
                    title = item.get("title", "")
                    company = item.get("advertiser", {}).get("description", "")
                    link = f"https://www.jobstreet.com.ph/job/{item.get('id', '')}"
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=item.get("location", "Philippines"),
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=item.get("salary", ""),
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=item.get("listingDate", "")[:10]
                    ))
        except Exception:
            pass
        return jobs
