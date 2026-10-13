import json
import urllib.request
import urllib.parse
from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job
from src.classifier import classify_experience_level, classify_role

import time
import random

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

class KalibrrConnector(BaseConnector):
    platform = "Kalibrr"
    tier = 1

    def fetch(self, query: str = "software engineer", location: str = "Philippines") -> List[Job]:
        jobs: List[Job] = []
        seen_codes = set()
        for page in (1, 2):
            params = urllib.parse.urlencode({"name": query, "limit": 100, "page": page})
            url = f"https://www.kalibrr.com/api/job_board/search?{params}"
            req = urllib.request.Request(url, headers=HEADERS)
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    items = data.get("jobs", [])
                    if not items:
                        break
                    for item in items:
                        code = item.get("code", "")
                        if code and code in seen_codes:
                            continue
                        if code:
                            seen_codes.add(code)
                        title = item.get("name", "")
                        company = item.get("company_name", "")
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
                # Polite anti-ban pause between pages
                time.sleep(random.uniform(0.4, 0.7))
            except Exception as e:
                logger.error(f"[{self.platform}] fetch failed on page {page}: {e}")
                break
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
                url = f"https://himalayas.app/jobs/api?search={search_term}&limit=50"
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

            queries = [query]
            if query.lower() in ("developer", "software developer", "software engineer", "dev"):
                queries.append("junior-developer")

            seen_urls = set()
            for q_term in queries:
                clean_q = urllib.parse.quote(q_term.lower().strip().replace(" ", "-"))
                for page in (1, 2):
                    url = f"https://www.jobstreet.com.ph/{clean_q}-jobs?page={page}"
                    try:
                        resp = cffi_requests.get(url, impersonate="chrome120", timeout=12)
                        if resp.status_code == 200:
                            soup = BeautifulSoup(resp.text, "html.parser")
                            articles = soup.find_all("article")
                            if not articles:
                                break
                            for art in articles:
                                title_a = art.find("a", {"data-automation": "jobTitle"}) or art.find("a")
                                if not title_a:
                                    continue
                                title = title_a.text.strip()
                                if not title:
                                    continue
                                href = title_a.get("href", "")
                                if href and not href.startswith("http"):
                                    href = "https://www.jobstreet.com.ph" + href
                                if href in seen_urls:
                                    continue
                                seen_urls.add(href)
                                comp_a = art.find("a", {"data-automation": "jobCompany"})
                                comp = comp_a.text.strip() if comp_a else "Company Confidential"
                                loc_a = art.find("a", {"data-automation": "jobLocation"})
                                loc = loc_a.text.strip() if loc_a else "Philippines"
                                sal_span = art.find("span", {"data-automation": "jobSalary"})
                                sal = sal_span.text.strip() if sal_span else ""
                                date_elem = art.find(attrs={"data-automation": "jobListingDate"}) or art.find("time")
                                date_val = date_elem.text.strip() if date_elem else ""
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
                                    date_posted=date_val
                                ))
                        time.sleep(random.uniform(0.6, 1.0))
                    except Exception as inner_e:
                        logger.warning(f"[{self.platform}] sub-query '{q_term}' page {page} notice: {inner_e}")
                        break
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs


class OnlineJobsConnector(BaseConnector):
    platform = "OnlineJobs.ph"
    tier = 1

    def fetch(self, query: str = "developer", location: str = "philippines") -> List[Job]:
        jobs: List[Job] = []
        try:
            from bs4 import BeautifulSoup

            clean_q = urllib.parse.quote(query.strip())
            seen_urls = set()

            for page in (1, 2, 3):
                url = f"https://www.onlinejobs.ph/jobseekers/jobsearch?jobkeyword={clean_q}&fullTime=on&partTime=on&page={page}"
                req = urllib.request.Request(url, headers=HEADERS)
                try:
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        html = resp.read().decode("utf-8")
                        soup = BeautifulSoup(html, "html.parser")
                        cards = soup.select(".jobpost-cat-box")
                        if not cards:
                            break
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

                            a = c.find("a", href=lambda h: h and "/jobseekers/job/" in h)
                            link = a["href"] if a else ""
                            if link and not link.startswith("http"):
                                link = "https://www.onlinejobs.ph" + link

                            if not link or link in seen_urls:
                                continue
                            seen_urls.add(link)

                            sal_el = c.select_one("dd.col")
                            salary = sal_el.get_text(strip=True) if sal_el else ""

                            date_el = c.select_one("p.fs-13")
                            date_val = ""
                            if date_el:
                                date_val = date_el.get("data-temp", "")[:10]
                                if not date_val:
                                    raw_t = date_el.get_text(strip=True)
                                    if "Posted on " in raw_t:
                                        date_val = raw_t.replace("Posted on ", "")[:10]

                            company = "Direct Client (OnlineJobs.ph)"
                            desc_el = c.select_one(".desc")
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

                            jobs.append(Job(
                                title=title,
                                company=company,
                                location="Philippines (Remote / Direct Client)",
                                platform=self.platform,
                                tier=self.tier,
                                job_url=link,
                                salary=salary,
                                role_category=classify_role(title),
                                experience_level=classify_experience_level(title),
                                date_posted=date_val
                            ))
                    # Polite anti-ban delay between pages
                    time.sleep(random.uniform(0.4, 0.7))
                except Exception as page_e:
                    logger.warning(f"[{self.platform}] page {page} fetch notice: {page_e}")
                    break
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs

