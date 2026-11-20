import json
import time
from typing import List
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from src.classifier import classify_experience_level, is_work_authorized_location
from src.connectors.base import BaseConnector
from src.models import Job


def _format_salary(base_salary) -> str:
    if not isinstance(base_salary, dict):
        return ""
    currency = str(base_salary.get("currency") or "USD").strip()
    val = base_salary.get("value")
    if not isinstance(val, dict):
        return ""
    low = val.get("minValue")
    high = val.get("maxValue")
    unit = str(val.get("unitText") or "").strip().lower()
    suffix = f"/{unit}" if unit else ""
    if low is not None and high is not None:
        return f"{currency} {float(low):,.0f} - {float(high):,.0f}{suffix}"
    if low is not None:
        return f"{currency} {float(low):,.0f}{suffix}"
    if high is not None:
        return f"{currency} {float(high):,.0f}{suffix}"
    return ""


def _extract_location(ld: dict) -> str:
    reqs = ld.get("applicantLocationRequirements")
    req_list = reqs if isinstance(reqs, list) else ([reqs] if isinstance(reqs, dict) else [])
    names = [str(item.get("name") or "").strip() for item in req_list if isinstance(item, dict) and str(item.get("name") or "").strip()]
    if not names:
        jloc = ld.get("jobLocation")
        loc_list = jloc if isinstance(jloc, list) else ([jloc] if isinstance(jloc, dict) else [])
        for item in loc_list:
            if not isinstance(item, dict):
                continue
            addr = item.get("address") if isinstance(item.get("address"), dict) else {}
            part = str(addr.get("addressCountry") or addr.get("addressLocality") or item.get("name") or "").strip()
            if part and part not in names:
                names.append(part)

    telecommute = str(ld.get("jobLocationType") or "").upper() == "TELECOMMUTE"
    if any(n.lower() in ("anywhere", "worldwide", "global") for n in names):
        return "Remote (Worldwide)"
    if names:
        joined = ", ".join(names)
        if telecommute and "remote" not in joined.lower():
            return f"Remote ({joined})"
        return joined
    if telecommute:
        return "Remote (Worldwide)"
    return "Remote (Worldwide)"


class Web3CareerConnector(BaseConnector):
    """Remote tech connector using Web3.career HTML rows paired with JSON-LD JobPosting metadata."""

    platform = "Web3.career"
    tier = 2
    is_feed = True
    MAX_PAGES = 2
    BASE_URL = "https://web3.career/remote-jobs"

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        self.coverage_warning = ""
        self.last_raw_count = 0
        self.last_route = "DIRECT"

        jobs: List[Job] = []
        seen_ids = set()
        raw_count = 0
        successful_pages = 0
        warnings = []

        for page in range(1, self.MAX_PAGES + 1):
            url = self.BASE_URL if page == 1 else f"{self.BASE_URL}?page={page}"
            try:
                if page > 1 and self.db_path:
                    time.sleep(0.4)
                resp = self.get_url(url, impersonate="chrome120", timeout=12)
                if resp.status_code != 200:
                    raise RuntimeError(f"Web3.career HTTP {resp.status_code}")
                successful_pages += 1
                soup = BeautifulSoup(resp.text, "html.parser")
                rows = [tr for tr in soup.select("tr[data-jobid]") if str(tr.get("data-jobid") or "").strip()]
                ld_jobs = []
                for sc in soup.select("script[type='application/ld+json']"):
                    if not sc.string or '"JobPosting"' not in sc.string:
                        continue
                    try:
                        obj = json.loads(sc.string)
                        if isinstance(obj, dict) and obj.get("@type") == "JobPosting":
                            ld_jobs.append(obj)
                    except (ValueError, TypeError):
                        continue

                raw_count += len(rows)
                if not rows:
                    break

                ld_by_title = {
                    str(item.get("title") or "").strip().lower(): item
                    for item in ld_jobs
                    if str(item.get("title") or "").strip()
                }
                paired_by_index = len(rows) == len(ld_jobs)

                for idx, row in enumerate(rows):
                    job_id = str(row.get("data-jobid") or "").strip()
                    a_el = row.select_one("a[href]")
                    href = str(a_el.get("href") or "").strip() if a_el else ""
                    if not href:
                        continue
                    job_url = urljoin("https://web3.career", href)
                    host = urlsplit(job_url)
                    if host.scheme != "https" or not host.netloc:
                        continue

                    dedup_key = job_id or job_url
                    if dedup_key in seen_ids:
                        continue
                    seen_ids.add(dedup_key)

                    h2_el = row.select_one("h2")
                    h3_el = row.select_one("h3")
                    row_title = h2_el.get_text(" ", strip=True) if h2_el else ""
                    ld = ld_jobs[idx] if paired_by_index else ld_by_title.get(row_title.lower(), {})

                    title = str(ld.get("title") or row_title).strip()
                    if not title:
                        continue

                    org = ld.get("hiringOrganization") if isinstance(ld.get("hiringOrganization"), dict) else {}
                    company = str(org.get("name") or (h3_el.get_text(" ", strip=True) if h3_el else "") or "Web3 Employer").strip()

                    time_el = row.select_one("time")
                    raw_dt = str(ld.get("datePosted") or (time_el.get("datetime") if time_el else "") or "").strip()
                    if not self.accepts_date(raw_dt):
                        continue

                    desc = str(ld.get("description") or "").strip()
                    loc = _extract_location(ld) if ld else "Remote (Worldwide)"
                    salary = _format_salary(ld.get("baseSalary"))

                    if not is_work_authorized_location(loc, title, self.platform, desc):
                        continue
                    if not self.accepts_opportunity(title, desc, allow_va_training=False, location=loc, platform=self.platform):
                        continue

                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=loc,
                        platform=self.platform,
                        tier=self.tier,
                        job_url=job_url,
                        salary=salary,
                        role_category=self.job_role(title, desc),
                        experience_level=classify_experience_level(title, desc),
                        description=desc,
                        date_posted=raw_dt,
                    ))
            except Exception as exc:
                warnings.append(f"page {page}: {exc}")
                break

        self.last_raw_count = raw_count
        if successful_pages == 0 and warnings:
            self.last_error = "; ".join(warnings)
        elif warnings:
            self.coverage_warning = "Coverage limited: " + "; ".join(warnings)
        return jobs
