from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job
from src.classifier import classify_experience_level, classify_role

class JobSpyAdapter(BaseConnector):
    def __init__(self, platform_name: str, site_name: str, tier: int):
        self.platform = platform_name
        self.site_name = site_name
        self.tier = tier

    def fetch(self, query: str = "software engineer", location: str = "Philippines") -> List[Job]:
        jobs: List[Job] = []
        try:
            import importlib
            jobspy = importlib.import_module("jobspy")
            scrape_jobs = getattr(jobspy, "scrape_jobs")
            df = scrape_jobs(
                site_name=[self.site_name],
                search_term=query,
                location=location,
                results_wanted=20,
                country_indeed="philippines" if "indeed" in self.site_name else None
            )
            for _, row in df.iterrows():
                title = str(row.get("title", ""))
                company = str(row.get("company", ""))
                url = str(row.get("job_url", ""))
                salary = str(row.get("min_amount", "")) if row.get("min_amount") else ""
                jobs.append(Job(
                    title=title,
                    company=company,
                    location=str(row.get("location", location)),
                    platform=self.platform,
                    tier=self.tier,
                    job_url=url,
                    salary=salary,
                    role_category=classify_role(title),
                    experience_level=classify_experience_level(title),
                    date_posted=str(row.get("date_posted", ""))
                ))
        except Exception as e:
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs
