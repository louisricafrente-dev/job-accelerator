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

    def fetch(self, query: str = "software engineer", location: str = "Philippines") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        seen_codes = set()
        for page in (1, 2):
            params = urllib.parse.urlencode({"name": query, "limit": 100, "page": page})
            url = f"https://www.kalibrr.com/api/job_board/search?{params}"
            req = urllib.request.Request(url, headers=HEADERS)
            try:
                with self.open_url(req, timeout=12) as resp:
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
                        if not is_relevant_opportunity(title, ""):
                            continue
                        pub_date = item.get("published", "")[:10]
                        if not is_within_15_days(pub_date):
                            continue
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
                            date_posted=pub_date
                        )
                        jobs.append(job)
                # Polite anti-ban pause between pages
                time.sleep(random.uniform(0.4, 0.7))
            except Exception as e:
                self.last_error = str(e) or type(e).__name__
                logger.error(f"[{self.platform}] fetch failed on page {page}: {e}")
                break
        return jobs

class BossjobConnector(BaseConnector):
    platform = "Bossjob"
    tier = 2
    revision = 2

    def fetch(self, query: str = "developer", location: str = "Philippines") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        try:
            params = urllib.parse.urlencode({"query": query, "size": 20, "country_id": 167})
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
    revision = 2

    def fetch(self, query: str = "developer", location: str = "philippines") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        try:
            from bs4 import BeautifulSoup

            queries = [query]
            if query.lower() in ("developer", "software developer", "software engineer", "dev"):
                queries.append("junior-developer")

            seen_urls = set()
            for q_term in queries:
                clean_q = urllib.parse.quote("-".join(q_term.lower().replace("/", " ").split()), safe="")
                for page in (1, 2):
                    url = f"https://ph.jobstreet.com/{clean_q}-jobs?page={page}"
                    try:
                        req_kwargs = {"impersonate": "chrome120", "timeout": 12}
                        resp = self.get_url(url, **req_kwargs)
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
                                if not title or not is_relevant_opportunity(title, ""):
                                    continue
                                href = title_a.get("href", "")
                                if href and not href.startswith("http"):
                                    href = "https://ph.jobstreet.com" + href
                                if href in seen_urls:
                                    continue
                                seen_urls.add(href)
                                date_elem = art.find(attrs={"data-automation": "jobListingDate"}) or art.find("time")
                                date_val = date_elem.text.strip() if date_elem else ""
                                if not is_within_15_days(date_val):
                                    continue
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
                                    date_posted=date_val
                                ))
                        time.sleep(random.uniform(0.6, 1.0))
                    except Exception as inner_e:
                        self.last_error = str(inner_e) or type(inner_e).__name__
                        logger.warning(f"[{self.platform}] sub-query '{q_term}' page {page} notice: {inner_e}")
                        break
        except Exception as e:
            self.last_error = str(e) or type(e).__name__
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs


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

            for page in range(1, 5):
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

