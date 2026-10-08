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
        rss_url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
        req = urllib.request.Request(rss_url, headers=HEADERS)
        jobs: List[Job] = []
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                tree = ET.fromstring(resp.read().decode("utf-8"))
                for item in tree.findall(".//item"):
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_date = item.find("pubDate")
                    raw_title = title_elem.text if title_elem is not None and title_elem.text else ""
                    parts = raw_title.split(":", 1)
                    company = parts[0].strip() if len(parts) > 1 else "Unknown"
                    title = parts[1].strip() if len(parts) > 1 else raw_title
                    link = link_elem.text if link_elem is not None and link_elem.text else ""
                    job = Job(
                        title=title,
                        company=company,
                        location="Remote",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary="",
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=pub_date.text[:16] if pub_date is not None and pub_date.text else ""
                    )
                    jobs.append(job)
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

class ArcConnector(BaseConnector):
    platform = "Arc"
    tier = 3

    def fetch(self, query: str = "developer", location: str = "remote") -> List[Job]:
        jobs: List[Job] = []
        try:
            url = f"https://arc.dev/api/jobs?keyword={query}"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("data", []):
                    title = item.get("title", "")
                    company = item.get("companyName", "")
                    link = f"https://arc.dev/job/{item.get('slug', '')}"
                    jobs.append(Job(
                        title=title,
                        company=company,
                        location="Remote Worldwide",
                        platform=self.platform,
                        tier=self.tier,
                        job_url=link,
                        salary=item.get("salaryRange", ""),
                        role_category=classify_role(title),
                        experience_level=classify_experience_level(title),
                        date_posted=item.get("postedDate", "")[:10]
                    ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs
