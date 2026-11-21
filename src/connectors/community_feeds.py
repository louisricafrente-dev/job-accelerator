import json
import re
import time
from typing import List
from urllib.parse import urlencode, urlsplit

from bs4 import BeautifulSoup

from src.classifier import classify_experience_level, is_relevant_opportunity, is_work_authorized_location
from src.connectors.base import BaseConnector
from src.models import Job

SCAM_PATTERNS = (
    # Proxy / Account / Identity Fraud
    r"\bproxy\s+interviewer\b",
    r"\b(?:take|attend)\s+(?:an?\s+)?interview\s+(?:for\s+me|on\s+my\s+behalf)\b",
    r"\b(?:rent|lease|buy|verify|borrow|share)\s+(?:your\s+|an?\s+|my\s+)?(?:upwork|linkedin|fiverr|freelancer|github|outlier|remotasks|apple\s+developer|google\s+play)\s+account\b",
    r"\bkyc\s+verification\b",
    # Upfront Fee / Unpaid / Commission-Only / Task Scams
    r"\b(?:registration|application|onboarding|processing|activation|membership)\s+fee\b",
    r"\bsecurity\s+deposit\b",
    r"\b(?:1099\s+)?commission[- ]only\b",
    r"\b(?:unpaid|no\s+pay|for\s+exposure|volunteer\s+only)\b",
    r"\b(?:rev(?:enue)?[- ]?share|equity)\s+only\b",
    r"\b\d{1,3}%\s+rev(?:enue)?[- ]?share\b",
    r"\bcheck\s+cashing\b",
    r"\bsend\s+crypto\b",
    # Bot / Review / Upvote Manipulation & Adult Chatters
    r"\b(?:buy|need|looking\s+for)\s+upvotes\b",
    r"\b(?:google|trustpilot|app\s+store|play\s+store|amazon|yelp)\s+reviews?\b",
    r"\bonlyfans\b",
    r"\b(?:adult\s+chat|of\s+chatter|chatter\s+for\s+of)\b",
    # Aggregator Link-Farm Spam & Anonymous Off-Platform Traps
    r"\b\d+\s+remote\s+[a-z]+\s+jobs\b",
    r"\bquick\s+roundup\s+of\b",
    r"\b(?:whatsapp|telegram)\s+only\b",
    r"\bt\.me/[a-z0-9_]+",
)

_SALARY_RE = re.compile(
    r"(?:\$|USD\s*|PHP\s*|₱)\s*\d[\d,]*(?:\s*[kK])?(?:\s*[-–to]+\s*(?:\$|USD\s*|PHP\s*|₱)?\s*\d[\d,]*(?:\s*[kK])?)?"
    r"(?:\s*/\s*(?:hr|hour|mo|month|yr|year)|\s+per\s+(?:hour|month|year))?"
)


def is_scam_or_sketchy_post(title: str, body: str = "") -> bool:
    """Reject proxy-interviewer, account-rental, unpaid/rev-share, review-farm, and link-spam posts."""
    combined = f"{title or ''}\n{body or ''}".lower()
    return any(re.search(pat, combined) for pat in SCAM_PATTERNS)


def _extract_salary(text: str) -> str:
    match = _SALARY_RE.search(str(text or ""))
    return match.group(0).strip() if match else ""


class RedditConnector(BaseConnector):
    """Public Arctic Shift Reddit feed for verified, unremoved direct-client [Hiring] posts."""

    platform = "Reddit"
    tier = 2
    is_feed = True
    revision = 1
    SUBREDDITS = ("forhire", "jobbit", "remotejs", "DeveloperJobs", "buhaydigital", "pinoyprogrammer")
    PH_SUBREDDITS = {"buhaydigital", "pinoyprogrammer"}
    SEARCH_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
    MIN_BODY_CHARS = 80

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        self.coverage_warning = ""
        self.last_route = "DIRECT"
        jobs: List[Job] = []
        raw_count = 0
        successful_subs = 0
        warnings: List[str] = []
        seen_urls = set()

        start, _ = self.date_window()
        after_date = start.date().isoformat()

        for idx, sub in enumerate(self.SUBREDDITS):
            if idx and self.db_path:
                time.sleep(2.0)
            params = urlencode({"subreddit": sub, "after": after_date, "limit": 100, "sort": "desc"})
            url = f"{self.SEARCH_URL}?{params}"
            try:
                resp = self.get_url(url, impersonate="chrome120", timeout=10)
                if getattr(resp, "status_code", 0) != 200:
                    warnings.append(f"r/{sub}: HTTP {getattr(resp, 'status_code', 'error')}")
                    continue
                payload = resp.json() if callable(getattr(resp, "json", None)) else json.loads(resp.text)
                posts = payload.get("data")
                if not isinstance(posts, list):
                    warnings.append(f"r/{sub}: invalid posts payload")
                    continue
                successful_subs += 1
                raw_count += len(posts)
            except Exception as exc:
                warnings.append(f"r/{sub}: {exc}")
                continue

            for post in posts:
                if not isinstance(post, dict):
                    continue
                if (
                    post.get("removed_by_category") is not None
                    or post.get("removed_by") is not None
                    or post.get("banned_by") is not None
                    or post.get("over_18")
                    or post.get("quarantine")
                    or post.get("is_created_from_ads_ui")
                    or post.get("author_is_blocked")
                ):
                    continue
                author = str(post.get("author") or "").strip()
                if not author or author.lower() in ("[deleted]", "deleted", "automoderator", "none"):
                    continue
                score = post.get("score")
                if isinstance(score, (int, float)) and score < 0:
                    continue

                raw_title = str(post.get("title") or "").strip()
                flair = str(post.get("link_flair_text") or "").strip().lower()
                if (
                    re.search(r"\[\s*for\s*hire\s*\]", raw_title, re.I)
                    or flair == "for hire"
                    or re.search(r"^\s*for\s+hire\b", raw_title, re.I)
                ):
                    continue
                if not (re.search(r"\[\s*hiring\s*\]", raw_title, re.I) or flair in ("hiring", "job opening", "job posting")):
                    continue

                selftext = str(post.get("selftext") or "").strip()
                if selftext.lower() in ("[removed]", "[deleted]", "") or len(selftext) < self.MIN_BODY_CHARS:
                    continue
                if "title goes here" in raw_title.lower() or "put a job description, location in the title" in selftext.lower():
                    continue

                created_utc = post.get("created_utc")
                if not self.accepts_date(created_utc):
                    continue
                if is_scam_or_sketchy_post(raw_title, selftext):
                    continue

                clean_title = re.sub(
                    r"^(?:\[\s*hiring\s*\]|\(\s*hiring\s*\))\s*[-:–—|]*\s*",
                    "",
                    raw_title,
                    flags=re.I,
                ).strip() or raw_title

                if sub in self.PH_SUBREDDITS:
                    loc = "Philippines (Remote)"
                elif re.search(r"\b(?:philippines|manila|makati|bgc|cebu|davao)\b", f"{raw_title} {selftext}", re.I):
                    loc = "Philippines (Remote)"
                elif re.search(r"\b(?:remote|online|anywhere|worldwide|global)\b", f"{raw_title} {selftext}", re.I):
                    loc = "Remote Worldwide"
                else:
                    loc = ""

                if not is_work_authorized_location(loc, clean_title, self.platform, selftext):
                    continue
                if not self.accepts_opportunity(clean_title, selftext, allow_va_training=False):
                    continue

                permalink = str(post.get("permalink") or "").strip()
                if permalink.startswith("/r/"):
                    job_url = f"https://www.reddit.com{permalink}"
                else:
                    candidate_url = str(post.get("url") or "").strip()
                    host = urlsplit(candidate_url)
                    if host.scheme == "https" and host.netloc.lower().endswith("reddit.com"):
                        job_url = candidate_url
                    else:
                        continue
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                salary = _extract_salary(f"{raw_title} {selftext[:400]}")
                jobs.append(Job(
                    title=clean_title,
                    company=f"Direct Client (Reddit r/{sub} - u/{author})",
                    location=loc or "Remote Worldwide",
                    platform=self.platform,
                    tier=self.tier,
                    job_url=job_url,
                    salary=salary,
                    role_category=self.job_role(clean_title, selftext),
                    experience_level=classify_experience_level(clean_title, selftext),
                    description=selftext,
                    date_posted=int(created_utc),
                ))

        self.last_raw_count = raw_count
        if successful_subs == 0 and warnings:
            self.last_error = "; ".join(warnings)
        elif warnings:
            self.coverage_warning = "Coverage limited: " + "; ".join(warnings)
        return jobs


class HackerNewsConnector(BaseConnector):
    """Official Algolia HN API for 'Ask HN: Who is hiring?' direct founder/CTO comments."""

    platform = "Hacker News"
    tier = 2
    is_feed = True
    revision = 1
    STORY_SEARCH_URL = (
        "https://hn.algolia.com/api/v1/search_by_date"
        "?tags=story,author_whoishiring&query=Who%20is%20hiring&hitsPerPage=5"
    )
    COMMENTS_URL = (
        "https://hn.algolia.com/api/v1/search_by_date"
        "?tags=comment,story_{story_id}&query=remote&hitsPerPage=100"
    )

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        self.coverage_warning = ""
        self.last_route = "DIRECT"
        jobs: List[Job] = []

        try:
            story_resp = self.get_url(self.STORY_SEARCH_URL, impersonate="chrome120", timeout=10)
            if getattr(story_resp, "status_code", 0) != 200:
                raise RuntimeError(f"Hacker News story search HTTP {getattr(story_resp, 'status_code', 'error')}")
            story_payload = story_resp.json() if callable(getattr(story_resp, "json", None)) else json.loads(story_resp.text)
            stories = story_payload.get("hits") or []
            hiring_story = next(
                (s for s in stories if isinstance(s, dict) and "who is hiring?" in str(s.get("title") or "").lower()),
                None,
            )
            if not hiring_story:
                raise RuntimeError("No active 'Who is hiring?' thread found")
            story_id = str(hiring_story.get("objectID") or "").strip()
            if not story_id.isascii() or not story_id.isdecimal():
                raise RuntimeError("Invalid Hacker News story ID")

            comm_resp = self.get_url(self.COMMENTS_URL.format(story_id=story_id), impersonate="chrome120", timeout=10)
            if getattr(comm_resp, "status_code", 0) != 200:
                raise RuntimeError(f"Hacker News comments HTTP {getattr(comm_resp, 'status_code', 'error')}")
            comm_payload = comm_resp.json() if callable(getattr(comm_resp, "json", None)) else json.loads(comm_resp.text)
            hits = comm_payload.get("hits")
            if not isinstance(hits, list):
                raise RuntimeError("Invalid Hacker News comments payload")
            self.last_raw_count = len(hits)

            for hit in hits:
                if not isinstance(hit, dict) or str(hit.get("parent_id") or "") != story_id:
                    continue
                object_id = str(hit.get("objectID") or "").strip()
                created_at = str(hit.get("created_at") or "").strip()
                if not (object_id.isascii() and object_id.isdecimal()) or not self.accepts_date(created_at):
                    continue
                raw_html = str(hit.get("comment_text") or "").strip()
                if not raw_html:
                    continue
                plain_text = BeautifulSoup(raw_html, "html.parser").get_text("\n", strip=True)
                if len(plain_text) < 60:
                    continue
                if re.search(r"\bseeking\s+(?:work|freelance|opportunities|employment)\b", plain_text, re.I):
                    continue

                lines = [ln.strip() for ln in plain_text.splitlines() if ln.strip()]
                first_line = lines[0] if lines else ""
                if is_scam_or_sketchy_post(first_line, plain_text):
                    continue

                segments = [seg.strip() for seg in first_line.split("|") if seg.strip()]
                if len(segments) >= 2:
                    company = segments[0][:80]
                    role_seg = next((seg for seg in segments[1:] if is_relevant_opportunity(seg, "")), segments[1])
                    title = role_seg[:120]
                    loc_segs = [
                        seg for seg in segments[1:]
                        if seg != role_seg and re.search(
                            r"\b(?:remote|worldwide|global|apac|asia|philippines|anywhere|us|europe|eu|uk|hybrid|onsite)\b",
                            seg,
                            re.I,
                        )
                    ]
                    loc = " | ".join(loc_segs) or ("Remote Worldwide" if "remote" in first_line.lower() else "")
                else:
                    if not is_relevant_opportunity(first_line, ""):
                        continue
                    company = "Startup (Hacker News)"
                    title = first_line[:90]
                    loc = "Remote Worldwide" if "remote" in plain_text.lower() else ""

                if not is_work_authorized_location(loc, title, self.platform, plain_text):
                    continue
                if not self.accepts_opportunity(title, plain_text, allow_va_training=False):
                    continue

                salary = _extract_salary(first_line) or _extract_salary(plain_text[:400])
                jobs.append(Job(
                    title=title,
                    company=company,
                    location=loc or "Remote Worldwide",
                    platform=self.platform,
                    tier=self.tier,
                    job_url=f"https://news.ycombinator.com/item?id={object_id}",
                    salary=salary,
                    role_category=self.job_role(title, plain_text),
                    experience_level=classify_experience_level(title, plain_text),
                    description=plain_text,
                    date_posted=created_at,
                ))
        except Exception as exc:
            self.last_error = str(exc) or type(exc).__name__
        return jobs
