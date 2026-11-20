import re
import time
from typing import List
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from src.classifier import classify_experience_level, is_work_authorized_location
from src.connectors.base import BaseConnector
from src.models import Job, normalize_date


class TalentPHConnector(BaseConnector):
    """Dedicated Philippine job board connector for ph.talent.com."""

    platform = "Talent.com PH"
    tier = 1
    is_feed = True
    QUERIES = (
        "software developer",
        "web developer",
        "android developer",
        "mobile developer",
        "full stack developer",
        "frontend developer",
        "backend developer",
        "qa engineer",
        "remote developer",
        "junior developer",
    )
    MAX_PAGES = 2

    def _date_param(self) -> int:
        days = self.window_days
        if days <= 1:
            return 1
        if days <= 3:
            return 3
        if days <= 7:
            return 7
        return 30

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        self.coverage_warning = ""
        self.last_raw_count = 0
        self.last_route = "DIRECT"

        start, _ = self.date_window()
        window_start = start.date().isoformat()
        date_param = self._date_param()
        queries = (query.strip(),) if query and query.strip() else self.QUERIES

        jobs: List[Job] = []
        seen_ids = set()
        raw_count = 0
        successful_queries = 0
        warnings = []
        made_request = False

        for q in queries:
            query_succeeded = False
            for page in range(1, self.MAX_PAGES + 1):
                params = {"k": q, "l": "Philippines", "date": date_param}
                if page > 1:
                    params["p"] = page
                url = "https://ph.talent.com/jobs?" + urlencode(params)
                try:
                    if made_request and self.db_path:
                        time.sleep(0.3)
                    made_request = True
                    resp = self.get_url(url, impersonate="chrome120", timeout=12)
                    if resp.status_code != 200:
                        raise RuntimeError(f"Talent.com PH HTTP {resp.status_code}")
                    query_succeeded = True
                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = soup.select("article[class*='JobCard_card']")
                    raw_count += len(cards)
                    if not cards:
                        break

                    new_in_page = 0
                    dated_norms = []
                    for card in cards:
                        title_el = card.find("h2")
                        title = title_el.get_text(" ", strip=True) if title_el else ""
                        link_el = card.select_one("a[href*='/view?id=']")
                        href = str(link_el.get("href") or "") if link_el else ""
                        job_id = parse_qs(urlsplit(href).query).get("id", [""])[0].strip()
                        if not title or not job_id:
                            continue

                        if job_id not in seen_ids:
                            new_in_page += 1

                        time_el = card.find("time")
                        raw_dt = str(time_el.get("datetime") or "").strip() if time_el else ""
                        if not raw_dt and time_el:
                            raw_dt = re.sub(r"^last updated:\s*", "", time_el.get_text(" ", strip=True), flags=re.IGNORECASE).strip()
                        norm_dt = normalize_date(raw_dt) if raw_dt else ""
                        if norm_dt:
                            dated_norms.append(norm_dt)

                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        comp_el = card.select_one("span[class*='JobCard_company']")
                        company = (comp_el.get_text(" ", strip=True) if comp_el else "") or "PH Employer"
                        loc_el = card.select_one("span[class*='JobCard_location']")
                        loc = (loc_el.get_text(" ", strip=True) if loc_el else "") or "Philippines"

                        snippet_el = card.select_one("p[class*='JobCard_snippet']")
                        desc = ""
                        if snippet_el:
                            parts = [t.strip() for t in snippet_el.find_all(string=True) if not t.find_parent("a")]
                            desc = " ".join(p for p in parts if p)

                        if not self.accepts_date(raw_dt or norm_dt):
                            continue
                        if not is_work_authorized_location(loc, title, self.platform, desc):
                            continue
                        if not self.accepts_opportunity(title, desc, allow_va_training=True, location=loc, platform=self.platform):
                            continue

                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=loc,
                            platform=self.platform,
                            tier=self.tier,
                            job_url=f"https://ph.talent.com/view?id={job_id}",
                            salary="",
                            role_category=self.job_role(title, desc),
                            experience_level=classify_experience_level(title, desc),
                            description=desc,
                            date_posted=raw_dt or norm_dt,
                        ))

                    all_old = bool(dated_norms) and all(d < window_start for d in dated_norms)
                    if len(cards) < 15 or new_in_page == 0 or all_old:
                        break
                except Exception as exc:
                    warnings.append(f"{q}: {exc}")
                    break

            if query_succeeded:
                successful_queries += 1

        self.last_raw_count = raw_count
        if successful_queries == 0 and warnings:
            self.last_error = "; ".join(warnings)
        elif warnings:
            self.coverage_warning = "Coverage limited: " + "; ".join(warnings)
        return jobs
