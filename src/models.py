import hashlib
import urllib.parse
from dataclasses import dataclass
from typing import Optional

def clean_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    query_params = urllib.parse.parse_qsl(parsed.query)
    filtered = [
        (k, v) for k, v in query_params
        if not k.lower().startswith("utm_") and k.lower() not in ("ref", "source", "trk", "tracking", "fbclid")
    ]
    new_query = urllib.parse.urlencode(filtered)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))

def hash_job(platform: str, company: str, title: str, url: str) -> str:
    cleaned = clean_url(url)
    key = f"{platform.strip().lower()}|{company.strip().lower()}|{title.strip().lower()}|{cleaned.lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

@dataclass
class Job:
    title: str
    company: str
    location: str
    platform: str
    tier: int
    job_url: str
    salary: str = ""
    role_category: str = "Web/Software Dev"
    experience_level: str = "Unspecified"
    date_posted: str = ""
    status: str = "new"
    notes: str = ""
    dedup_hash: Optional[str] = None

    def __post_init__(self):
        if not self.dedup_hash:
            self.dedup_hash = hash_job(self.platform, self.company, self.title, self.job_url)
