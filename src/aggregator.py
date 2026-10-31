import concurrent.futures
from typing import List, Dict, Any, Optional
from src.connectors.base import BaseConnector
from src.connectors.remote_feed import (
    RemoteOKConnector,
    WeWorkRemotelyConnector,
    ArcConnector,
    RemotiveConnector,
    HimalayasConnector,
    JobicyConnector,
    FreelancerConnector,
    UpworkConnector,
    WellfoundConnector,
    ContraConnector,
    FlexJobsConnector,
    WorkingNomadsConnector,
    DailyRemoteConnector,
    RealWorkFromAnywhereConnector,
    YCombinatorConnector,
)
from src.connectors.ph_jobs import (
    KalibrrConnector,
    BossjobConnector,
    JobStreetCatalogConnector,
    OnlineJobsConnector,
    FounditPHConnector,
    VirtualStaffPHConnector,
    PhilJobNetConnector,
    JobgetherPHConnector,
)
from src.connectors.jobspy_adapter import JobSpyAdapter
from src.database import insert_jobs, get_user_setting, set_user_setting, acquire_sync_lease, release_sync_lease
from src.classifier import is_relevant_opportunity
import time
import json
import uuid
from src.models import Job, is_today_or_yesterday
from src.video_editor import collectable_job
from src.connectors.video_editor import video_connectors

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
    "ai engineer", "data engineer", "systems developer",

    # Priority 8: Virtual Assistant & Remote Matrix (Entry Level / Training Only)
    "virtual assistant trainee", "entry level virtual assistant",
    "virtual assistant", "cyberbacker", "athena", "virtudesk", "pineapple staffing"
]

def get_default_connectors() -> List[BaseConnector]:
    return [
        # Tier 1 — Core PH & High-Yield Direct Client Boards
        JobSpyAdapter("LinkedIn", "linkedin", tier=1),
        JobSpyAdapter("Indeed", "indeed", tier=1),
        JobSpyAdapter("Glassdoor", "glassdoor", tier=1),
        JobSpyAdapter("ZipRecruiter", "zip_recruiter", tier=2),
        JobStreetCatalogConnector(),
        OnlineJobsConnector(),
        KalibrrConnector(),
        FounditPHConnector(),
        VirtualStaffPHConnector(),
        JobgetherPHConnector(),

        # Tier 2 — High Value Startups, Direct Clients & Portals
        BossjobConnector(),
        PhilJobNetConnector(),
        WellfoundConnector(),
        ContraConnector(),
        FlexJobsConnector(),
        WorkingNomadsConnector(),
        DailyRemoteConnector(),
        RealWorkFromAnywhereConnector(),
        YCombinatorConnector(),
        # Tier 3 — Global Remote & Direct APIs (High Reliability)
        RemotiveConnector(),
        HimalayasConnector(),
        JobicyConnector(),
        RemoteOKConnector(),
        WeWorkRemotelyConnector(),
        ArcConnector(),
        FreelancerConnector(),
        UpworkConnector(),
        *video_connectors(),
    ]

import collections
import threading

class Aggregator:
    def __init__(self, db_path: str = "data/jobs.db", connectors: Optional[List[BaseConnector]] = None):
        self.db_path = db_path
        self.connectors = connectors if connectors is not None else get_default_connectors()
        for connector in self.connectors:
            connector.db_path = db_path
        self._sync_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self.is_syncing = False
        self.last_sync_result: Dict[str, Any] = {"added": 0, "skipped": 0, "total_fetched": 0, "platforms": {}}
        self.last_sync_time: float = 0.0
        self.sync_logs: collections.deque = collections.deque(
            [f"[{time.strftime('%H:%M:%S')}] System initialized with {len(self.connectors)} job board connectors."],
            maxlen=120
        )
        self.platform_telemetry: Dict[str, Dict[str, Any]] = {
            conn.platform: {"status": "ready", "count": 0, "tier": conn.tier} for conn in self.connectors
        }
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl: float = 300.0  # 5-minute cache per connector

    def log_event(self, msg: str) -> None:
        entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
        with self._cache_lock:
            self.sync_logs.append(entry)

    def get_telemetry(self) -> Dict[str, Any]:
        shared = get_user_setting(self.db_path, "sync_status", "")
        if shared and not self.is_syncing:
            status = json.loads(shared)
            valid_platforms = {conn.platform for conn in self.connectors}
            status["total_boards"] = len(self.connectors)
            if "progress" in status and isinstance(status["progress"], dict) and "boards" in status["progress"]:
                status["progress"]["boards"] = {
                    p: b for p, b in status["progress"]["boards"].items() if p in valid_platforms
                }
            if "last_result" in status and isinstance(status["last_result"], dict):
                lr_prog = status["last_result"].get("progress")
                if isinstance(lr_prog, dict) and "boards" in lr_prog:
                    lr_prog["boards"] = {
                        p: b for p, b in lr_prog["boards"].items() if p in valid_platforms
                    }
                    query_boards = [c for c in self.connectors if not getattr(c, "is_feed", False)]
                    lr_prog["total_searches"] = lr_prog.get("keywords", 0) * len(query_boards)
                    lr_prog["completed_searches"] = sum(
                        max(0, lr_prog["boards"].get(c.platform, {}).get("cursor", 0) - len(lr_prog["boards"].get(c.platform, {}).get("retry", [])))
                        for c in query_boards
                    )
            if "telemetry" in status and isinstance(status["telemetry"], dict):
                status["telemetry"] = {
                    conn.platform: status["telemetry"].get(
                        conn.platform, {"status": "ready", "count": 0, "tier": conn.tier}
                    )
                    for conn in self.connectors
                }
            lease = get_user_setting(self.db_path, "sync_lease", "0|")
            status["is_syncing"] = int(lease.split("|", 1)[0]) > time.time()
            if not status["is_syncing"] and status.get("last_result", {}).get("status") == "running":
                status["last_result"] = {"status": "error", "error": "Previous sync expired before completing"}
            return status
        with self._cache_lock:
            cached_logs = list(self.sync_logs)
            cached_telem = dict(self.platform_telemetry)
        return {
            "is_syncing": self.is_syncing,
            "last_sync_time": self.last_sync_time,
            "last_result": self.last_sync_result,
            "progress": self.last_sync_result.get("progress"),
            "total_boards": len(self.connectors),
            "telemetry": cached_telem,
            "platforms": self.last_sync_result.get("platforms", {}),
            "logs": cached_logs
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

    def run_sync(self, queries: Optional[List[str]] = None, force: bool = False, budget_seconds: Optional[float] = None, cycle_id=None, resume=False, restart=False) -> Dict[str, Any]:
        if queries is None:
            saved_stack = get_user_setting(self.db_path, "target_stack", "")
            saved_queries = list(dict.fromkeys(q.strip() for q in saved_stack.split(",") if q.strip()))
            if saved_queries:
                queries = saved_queries
        search_queries = list(dict.fromkeys(
            q.strip() for q in (queries if queries is not None else DEFAULT_QUERIES)
            if isinstance(q, str) and q.strip()
        ))
        if budget_seconds is None and any(getattr(conn, "checkpointed_feed", False) is True or
                                          getattr(conn, "checkpointed_query", False) is True for conn in self.connectors):
            budget_seconds = 150
        if budget_seconds is not None:
            from src.sync_batches import run_batch
            return run_batch(self, search_queries, budget_seconds=budget_seconds, cycle_id=cycle_id, resume=resume, restart=restart)
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
        lease = f"{int(time.time()) + 600}|{uuid.uuid4().hex}"
        try:
            if not acquire_sync_lease(self.db_path, lease, int(time.time())):
                self.is_syncing = False
                self._sync_lock.release()
                return {"status": "already_syncing", "is_syncing": True}
        except Exception:
            self.is_syncing = False
            self._sync_lock.release()
            raise
        all_jobs: List[Job] = []
        platform_reports: Dict[str, int] = {}

        try:
            set_user_setting(self.db_path, "sync_status", json.dumps({"is_syncing": True, "total_boards": len(self.connectors), "last_result": {"status": "running"}, "logs": [], "telemetry": {}}))
            self.log_event(f"[Orchestrator] Multi-board sync cycle started across {len(self.connectors)} platforms.")
            def execute_connector(conn: BaseConnector) -> List[Job]:
                now = time.time()
                limit = getattr(conn, "coverage_limit", "")
                conn.coverage_warning = limit if isinstance(limit, str) else ""
                # 1. Check connector cache (prevents 429 rate limits & duplicate network overhead)
                cache_key = (conn.platform, tuple(sorted(str(q).strip().lower() for q in search_queries)))
                if not force and cache_key in self._cache:
                    cached_entry = self._cache[cache_key]
                    if now - cached_entry["timestamp"] < self.cache_ttl:
                        self.log_event(f"[{conn.platform}] Cache active: {len(cached_entry['jobs'])} listings ready.")
                        self.platform_telemetry[conn.platform] = {
                            "status": "cached",
                            "count": len(cached_entry["jobs"]),
                            "tier": conn.tier,
                            "timestamp": time.strftime("%H:%M:%S")
                        }
                        if conn.coverage_warning:
                            self.platform_telemetry[conn.platform].update(coverage_warning=conn.coverage_warning,
                                                                         error=conn.coverage_warning)
                        return cached_entry["jobs"]

                results: List[Job] = []
                errors: List[str] = []
                if hasattr(conn, "last_error"):
                    conn.last_error = ""
                # 2. Distinguish feed connectors from query-based scrapers
                is_feed = getattr(conn, "is_feed", False)

                if is_feed:
                    # Feed connectors return whole listings in 1 call; avoid looping redundant keywords
                    try:
                        self.log_event(f"[{conn.platform}] Reading high-yield stream...")
                        jobs = conn.fetch()
                        if isinstance(getattr(conn, "last_error", None), str) and conn.last_error:
                            errors.append(conn.last_error)
                        results.extend(jobs)
                        self.log_event(f"[{conn.platform}] Retrieved {len(jobs)} active opportunities.")
                        self.platform_telemetry[conn.platform] = {
                            "status": "active",
                            "count": len(jobs),
                            "tier": conn.tier,
                            "timestamp": time.strftime("%H:%M:%S")
                        }
                    except Exception as e:
                        errors.append(str(e) or type(e).__name__)
                        self.log_event(f"[{conn.platform}] Stream notice: {e}")
                        self.platform_telemetry[conn.platform] = {
                            "status": "error",
                            "count": 0,
                            "tier": conn.tier,
                            "timestamp": time.strftime("%H:%M:%S")
                        }
                else:
                    final_queries = search_queries

                    group_size = conn.query_group_size
                    for start in range(0, len(final_queries), group_size):
                        group = final_queries[start:start + group_size]
                        q = " OR ".join(group)
                        try:
                            conn.last_error = ""
                            self.log_event(f"[{conn.platform}] Querying '{q}'...")
                            jobs = conn.fetch_group(group) if len(group) > 1 else conn.fetch(query=group[0])
                            if isinstance(getattr(conn, "last_error", None), str) and conn.last_error:
                                errors.append(conn.last_error)
                            results.extend(jobs)
                            time.sleep(0.1)
                        except Exception as e:
                            errors.append(str(e) or type(e).__name__)
                            self.log_event(f"[{conn.platform}] Notice for '{q}': {e}")

                    self.log_event(f"[{conn.platform}] Harvested {len(results)} total listings across queries.")
                    if errors:
                        self.platform_telemetry[conn.platform] = {
                            "status": "error",
                            "count": len(results),
                            "tier": conn.tier,
                            "timestamp": time.strftime("%H:%M:%S")
                        }
                        self.log_event(f"[{conn.platform}] Source error: {'; '.join(errors)}")
                    else:
                        self.platform_telemetry[conn.platform] = {
                            "status": "active",
                            "count": len(results),
                            "tier": conn.tier,
                            "timestamp": time.strftime("%H:%M:%S")
                        }

                if errors:
                    self.platform_telemetry[conn.platform].update(status="error", error="; ".join(errors))
                    self._cache.pop(cache_key, None)
                else:
                    self._cache[cache_key] = {"timestamp": now, "jobs": results}
                if conn.coverage_warning:
                    self.platform_telemetry[conn.platform].update(coverage_warning=conn.coverage_warning,
                                                                 error=conn.coverage_warning)
                return results

            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                futures = {executor.submit(execute_connector, conn): conn for conn in self.connectors}
                for future in concurrent.futures.as_completed(futures):
                    conn = futures[future]
                    try:
                        jobs = future.result()
                        all_jobs.extend(jobs)
                        platform_reports[conn.platform] = len(jobs)
                    except Exception as exc:
                        platform_reports[conn.platform] = 0
                        self.platform_telemetry[conn.platform] = {"status": "error", "count": 0, "tier": conn.tier, "error": str(exc)}

            ingestion_error = None
            try:
                relevant_jobs = [
                    j for j in all_jobs
                    if collectable_job(j)
                ]
                dropped_cnt = len(all_jobs) - len(relevant_jobs)
                if dropped_cnt > 0:
                    self.log_event(f"[Filter Engine] Screened {len(all_jobs)} harvested listings: blocked {dropped_cnt} outside the role's date window or relevance rules; verified {len(relevant_jobs)} opportunities (video: 7 dates; other jobs: today/yesterday, Asia/Manila).")
                added, skipped = insert_jobs(self.db_path, relevant_jobs)
                self.log_event(f"[Database] Synchronized {len(relevant_jobs)} listings: +{added} new opportunities, {skipped} existing/cross-board merged.")
            except Exception as e:
                added, skipped = 0, 0
                ingestion_error = str(e)
                self.log_event(f"[Database] Ingestion notice: {e}")

            summary = {
                "status": "error" if ingestion_error else ("partial" if any(p.get("status") == "error" or p.get("coverage_warning") for p in self.platform_telemetry.values()) else "ok"),
                "error": ingestion_error,
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
            if not ingestion_error:
                self.last_sync_time = time.time()
            set_user_setting(self.db_path, "sync_status", json.dumps({"is_syncing": False, "last_sync_time": self.last_sync_time, "total_boards": len(self.connectors), "last_result": summary, "logs": summary["logs"], "telemetry": self.platform_telemetry}))
            return summary
        finally:
            self.is_syncing = False
            self._sync_lock.release()
            release_sync_lease(self.db_path, lease)

