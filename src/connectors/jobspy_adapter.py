from typing import List
from src.connectors.base import BaseConnector, logger
from src.models import Job, is_within_15_days
from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity, is_work_authorized_location

class JobSpyAdapter(BaseConnector):
    def __init__(self, platform_name: str, site_name: str, tier: int):
        self.platform = platform_name
        self.site_name = site_name
        self.tier = tier
        self.last_error = ""

    def fetch(self, query: str = "software engineer", location: str = "Philippines") -> List[Job]:
        self.last_error = ""
        jobs: List[Job] = []
        try:
            import importlib
            jobspy = importlib.import_module("jobspy")
            scrape_jobs = getattr(jobspy, "scrape_jobs")
            try:
                from src.proxy_manager import get_proxy_pool
                active_proxies = get_proxy_pool()
            except Exception:
                active_proxies = []
            df = scrape_jobs(
                site_name=[self.site_name],
                search_term=query,
                location=location,
                results_wanted=35,
                country_indeed="philippines" if self.site_name in ("indeed", "glassdoor") else None,
                hours_old=360,  # Strict 15 days (15 * 24 hours)
                proxies=active_proxies if active_proxies else None
            )
            errors = getattr(df, "attrs", {}).get("errors")
            if errors:
                self.last_error = str(errors)
            import pandas as pd
            for _, row in df.iterrows():
                title = str(row.get("title", "")).strip()
                company = str(row.get("company", "")).strip()
                url = str(row.get("job_url", "")).strip()
                if not title or title.lower() in ("nan", "none", "null"):
                    continue
                if not url or url.lower() in ("nan", "none", "null"):
                    continue
                raw_description = row.get("description")
                description = "" if pd.isna(raw_description) else str(raw_description).strip()
                raw_loc = row.get("location")
                loc = location if pd.isna(raw_loc) or str(raw_loc).lower() in ("nan", "none", "") else str(raw_loc).strip()
                if not is_work_authorized_location(loc, title, self.platform, description):
                    continue
                if not is_relevant_opportunity(title, description, allow_va_training=True, location=loc, platform=self.platform):
                    continue
                if company.lower() in ("nan", "none", "null", ""):
                    company = "Direct Employer"
                raw_sal = row.get("min_amount")
                salary = "" if pd.isna(raw_sal) or str(raw_sal).lower() in ("nan", "none", "") else str(raw_sal).strip()
                raw_date = row.get("date_posted")
                date_str = "" if pd.isna(raw_date) or str(raw_date).lower() in ("nan", "none", "") else str(raw_date).strip()
                if not is_within_15_days(date_str):
                    continue
                jobs.append(Job(
                    title=title,
                    company=company,
                    location=loc,
                    platform=self.platform,
                    tier=self.tier,
                    job_url=url,
                    salary=salary,
                    role_category=classify_role(title),
                    experience_level=classify_experience_level(title, description),
                    date_posted=date_str,
                    description=description
                ))
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"[{self.platform}] fetch failed: {e}")
        return jobs
