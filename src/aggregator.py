import concurrent.futures
from typing import List, Dict, Any, Optional
from src.connectors.base import BaseConnector
from src.connectors.remote_feed import (
    RemoteOKConnector,
    WeWorkRemotelyConnector,
    ArcConnector,
    WellfoundConnector,
    FounditConnector,
    UpworkConnector,
    RemotiveConnector,
    HimalayasConnector
)
from src.connectors.ph_jobs import KalibrrConnector, BossjobConnector, JobStreetConnector, OnlineJobsConnector
from src.connectors.jobspy_adapter import JobSpyAdapter
from src.database import insert_jobs
from src.classifier import is_relevant_opportunity
import time
from src.models import Job

DEFAULT_QUERIES = [
    # Priority 1: Core Titles & Junior/Entry (Highest Priority)
    "junior developer", "software developer", "junior software engineer",
    "associate software engineer", "entry level software engineer",
    "graduate software engineer", "application developer", "programmer",
    
    # Priority 2: Mobile & Candidate Specialization
    "android developer", "mobile developer", "kotlin developer",
    "flutter developer", "react native developer", "ios developer",
    
    # Priority 3 & 4: Web, Frontend, Backend & Full-Stack
    "frontend developer", "backend developer", "full stack developer",
    "web developer", "api developer", "react developer", "node.js developer",
    "python developer", "java developer", ".net developer",
    
    # Priority 5: Testing, QA & DevOps
    "qa automation engineer", "sdet", "devops engineer",
    
    # Priority 6 & 7: AI/Data & Systems Specialization
    "ai engineer", "data engineer", "systems developer"
]

def get_default_connectors() -> List[BaseConnector]:
    return [
        # Tier 1 — Core PH & High-Yield Direct Client Boards
        JobSpyAdapter("LinkedIn", "linkedin", tier=1),
        JobStreetConnector(),
        OnlineJobsConnector(),
        JobSpyAdapter("Indeed", "indeed", tier=1),
        KalibrrConnector(),

        # Tier 2 — High Value Startups & PH Portals
        BossjobConnector(),
        WellfoundConnector(),
        FounditConnector(),

        # Tier 3 — Global Remote & Direct APIs (High Reliability)
        RemotiveConnector(),
        HimalayasConnector(),
        RemoteOKConnector(),
        WeWorkRemotelyConnector(),
        ArcConnector(),

        # Tier 4 — Freelance & Company Reviews
        UpworkConnector(),
        JobSpyAdapter("Glassdoor", "glassdoor", tier=4),
    ]

import threading

class Aggregator:
    def __init__(self, db_path: str = "data/jobs.db", connectors: Optional[List[BaseConnector]] = None):
        self.db_path = db_path
        self.connectors = connectors or get_default_connectors()
        self._sync_lock = threading.Lock()
        self.is_syncing = False
        self.last_sync_result: Dict[str, Any] = {"added": 0, "skipped": 0, "total_fetched": 0, "platforms": {}}
        self.last_sync_time: float = 0.0
        self.sync_logs: List[str] = [
            f"[{time.strftime('%H:%M:%S')}] System initialized with {len(self.connectors)} job board connectors."
        ]
        self.platform_telemetry: Dict[str, Dict[str, Any]] = {
            conn.platform: {"status": "ready", "count": 0, "tier": conn.tier} for conn in self.connectors
        }
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl: float = 300.0  # 5-minute cache per connector

    def log_event(self, msg: str) -> None:
        entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self.sync_logs.append(entry)
        if len(self.sync_logs) > 120:
            self.sync_logs.pop(0)

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "is_syncing": self.is_syncing,
            "last_sync_time": self.last_sync_time,
            "total_boards": len(self.connectors),
            "telemetry": self.platform_telemetry,
            "platforms": self.last_sync_result.get("platforms", {}),
            "logs": list(self.sync_logs)
        }

    def start_background_sync(self, queries: Optional[List[str]] = None, force: bool = False) -> bool:
        """Starts run_sync in a non-blocking daemon thread. Returns True if launched, False if already running."""
        if self.is_syncing:
            return False
        thread = threading.Thread(
            target=self.run_sync,
            kwargs={"queries": queries, "force": force},
            daemon=True
        )
        thread.start()
        return True

    def run_sync(self, queries: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
        # Guard against concurrent duplicate runs / spamming
        acquired = self._sync_lock.acquire(blocking=False)
        if not acquired:
            return {
                "status": "already_syncing",
                "is_syncing": True,
                "message": "A sync operation is already actively running in the background.",
                "total_fetched": 0,
                "added": 0,
                "skipped": 0,
                "platforms": self.last_sync_result.get("platforms", {})
            }

        self.is_syncing = True
        all_jobs: List[Job] = []
        platform_reports: Dict[str, int] = {}
        search_queries = queries if queries is not None else DEFAULT_QUERIES

        try:
            self.log_event(f"[Orchestrator] Multi-board sync cycle started across {len(self.connectors)} platforms.")
            def execute_connector(conn: BaseConnector) -> List[Job]:
                now = time.time()
                # 1. Check connector cache (prevents 429 rate limits & duplicate network overhead)
                if not force and conn.platform in self._cache:
                    cached_entry = self._cache[conn.platform]
                    if now - cached_entry["timestamp"] < self.cache_ttl:
                        self.log_event(f"[{conn.platform}] Cache active: {len(cached_entry['jobs'])} listings ready.")
                        self.platform_telemetry[conn.platform] = {
                            "status": "cached",
                            "count": len(cached_entry["jobs"]),
                            "tier": conn.tier,
                            "timestamp": time.strftime("%H:%M:%S")
                        }
                        return cached_entry["jobs"]

                # 2. Distinguish feed connectors from query-based scrapers
                is_feed = hasattr(conn, "is_feed") or conn.platform in (
                    "Remote OK", "We Work Remotely", "Arc", "Foundit", "Upwork", "Wellfound", "Remotive", "Himalayas"
                )

                if is_feed:
                    # Feed connectors return whole listings in 1 call; avoid looping redundant keywords
                    try:
                        self.log_event(f"[{conn.platform}] Reading high-yield stream...")
                        jobs = conn.fetch()
                        results.extend(jobs)
                        self.log_event(f"[{conn.platform}] Retrieved {len(jobs)} active opportunities.")
                        self.platform_telemetry[conn.platform] = {
                            "status": "active",
                            "count": len(jobs),
                            "tier": conn.tier,
                            "timestamp": time.strftime("%H:%M:%S")
                        }
                    except Exception as e:
                        self.log_event(f"[{conn.platform}] Stream notice: {e}")
                        self.platform_telemetry[conn.platform] = {
                            "status": "error",
                            "count": 0,
                            "tier": conn.tier,
                            "timestamp": time.strftime("%H:%M:%S")
                        }
                else:
                    # MAX MODE: Multi-track dynamic query selection covering the user's entire stack
                    tech_q = [q for q in search_queries if not any(j in q.lower() for j in ["junior", "jr", "entry", "intern", "associate", "grad", "android", "mobile", "kotlin", "flutter", "react native", "ios"])]
                    jr_q = [q for q in search_queries if any(j in q.lower() for j in ["junior", "jr", "entry", "intern", "associate", "grad"])]
                    mob_q = [q for q in search_queries if any(m in q.lower() for m in ["android", "mobile", "kotlin", "flutter", "react native", "ios"])]

                    active_queries = []
                    # 1. Junior / Entry tracks (take up to 2 variations)
                    if jr_q:
                        active_queries.extend(jr_q[:2])
                    else:
                        active_queries.append("junior software engineer")

                    # 2. Mobile / Android tracks (take up to 2 variations)
                    if mob_q:
                        active_queries.extend(mob_q[:2])
                    else:
                        active_queries.append("android developer")

                    # 3. Web / Fullstack / Backend tracks (take up to 3 variations, e.g. React, Node, Next.js)
                    if tech_q:
                        active_queries.extend(tech_q[:3])
                    else:
                        active_queries.append("software developer")

                    # Deduplicate while preserving priority order (up to 5-6 queries in parallel)
                    seen_q = set()
                    final_queries = []
                    for q in active_queries:
                        ql = q.lower().strip()
                        if ql not in seen_q:
                            seen_q.add(ql)
                            final_queries.append(q)

                    for q in final_queries:
                        try:
                            self.log_event(f"[{conn.platform}] Querying '{q}'...")
                            jobs = conn.fetch(query=q)
                            results.extend(jobs)
                            time.sleep(0.1)
                        except Exception as e:
                            self.log_event(f"[{conn.platform}] Notice for '{q}': {e}")

                    self.log_event(f"[{conn.platform}] Harvested {len(results)} total listings across queries.")
                    self.platform_telemetry[conn.platform] = {
                        "status": "active",
                        "count": len(results),
                        "tier": conn.tier,
                        "timestamp": time.strftime("%H:%M:%S")
                    }

                # Store in cache
                self._cache[conn.platform] = {"timestamp": now, "jobs": results}
                return results

            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                futures = {executor.submit(execute_connector, conn): conn for conn in self.connectors}
                for future in concurrent.futures.as_completed(futures):
                    conn = futures[future]
                    try:
                        jobs = future.result()
                        all_jobs.extend(jobs)
                        platform_reports[conn.platform] = len(jobs)
                    except Exception:
                        platform_reports[conn.platform] = 0

            try:
                relevant_jobs = [j for j in all_jobs if is_relevant_opportunity(j.title, getattr(j, "description", ""), allow_va_training=True)]
                dropped_cnt = len(all_jobs) - len(relevant_jobs)
                if dropped_cnt > 0:
                    self.log_event(f"[Filter Engine] Screened {len(all_jobs)} harvested listings: blocked {dropped_cnt} non-tech/unrelated listings; verified {len(relevant_jobs)} tech & training VA opportunities.")
                added, skipped = insert_jobs(self.db_path, relevant_jobs)
                self.log_event(f"[Database] Synchronized {len(relevant_jobs)} listings: +{added} new opportunities, {skipped} existing/cross-board merged.")
            except Exception as e:
                added, skipped = 0, 0
                self.log_event(f"[Database] Ingestion notice: {e}")

            summary = {
                "status": "ok",
                "is_syncing": False,
                "total_fetched": len(all_jobs),
                "added": added,
                "skipped": skipped,
                "platforms": platform_reports,
                "telemetry": self.platform_telemetry,
                "logs": list(self.sync_logs),
                "timestamp": time.time()
            }
            self.last_sync_result = summary
            self.last_sync_time = time.time()
            return summary
        finally:
            self.is_syncing = False
            self._sync_lock.release()

