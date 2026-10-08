import concurrent.futures
from typing import List, Dict, Any, Optional
from src.connectors.base import BaseConnector
from src.connectors.remote_feed import (
    RemoteOKConnector,
    WeWorkRemotelyConnector,
    ArcConnector,
    WellfoundConnector,
    FounditConnector,
    UpworkConnector
)
from src.connectors.ph_jobs import KalibrrConnector, BossjobConnector, JobStreetConnector
from src.connectors.jobspy_adapter import JobSpyAdapter
from src.database import insert_jobs
from src.models import Job

DEFAULT_QUERIES = [
    "software engineer", "frontend developer", "backend developer",
    "full stack developer", "mobile developer", "flutter developer",
    "devops engineer", "cloud engineer", "qa engineer", "automation tester",
    "data analyst", "data engineer", "machine learning",
    "junior developer", "python developer", "react developer",
    "node developer", "java developer", ".net developer"
]

def get_default_connectors() -> List[BaseConnector]:
    return [
        # Tier 1 — Core PH & High-Yield Boards
        JobSpyAdapter("LinkedIn", "linkedin", tier=1),
        JobStreetConnector(),
        JobSpyAdapter("Indeed", "indeed", tier=1),
        KalibrrConnector(),

        # Tier 2 — High Value Startups & PH Portals
        BossjobConnector(),
        WellfoundConnector(),
        FounditConnector(),

        # Tier 3 — Global Remote & International
        RemoteOKConnector(),
        WeWorkRemotelyConnector(),
        ArcConnector(),

        # Tier 4 — Freelance & Company Reviews
        UpworkConnector(),
        JobSpyAdapter("Glassdoor", "glassdoor", tier=4),
    ]

class Aggregator:
    def __init__(self, db_path: str = "data/jobs.db", connectors: Optional[List[BaseConnector]] = None):
        self.db_path = db_path
        self.connectors = connectors or get_default_connectors()

    def run_sync(self, queries: Optional[List[str]] = None) -> Dict[str, Any]:
        search_queries = queries if queries is not None else DEFAULT_QUERIES
        all_jobs: List[Job] = []
        platform_reports: Dict[str, int] = {}

        def execute_connector(conn: BaseConnector) -> List[Job]:
            results = []
            for q in search_queries:
                try:
                    jobs = conn.fetch(query=q)
                    results.extend(jobs)
                except Exception as e:
                    pass
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(execute_connector, conn): conn for conn in self.connectors}
            for future in concurrent.futures.as_completed(futures):
                conn = futures[future]
                try:
                    jobs = future.result()
                    all_jobs.extend(jobs)
                    platform_reports[conn.platform] = len(jobs)
                except Exception:
                    platform_reports[conn.platform] = 0

        added, skipped = insert_jobs(self.db_path, all_jobs)
        return {
            "total_fetched": len(all_jobs),
            "added": added,
            "skipped": skipped,
            "platforms": platform_reports
        }
