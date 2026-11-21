import json
import re
import time
import xml.etree.ElementTree as ET
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
    revision = 2
    min_window_days = 7
    SUBREDDITS = ("forhire", "jobbit", "remotejs", "DeveloperJobs", "TechJobs", "RemoteJobs", "buhaydigital", "pinoyprogrammer")
    PH_SUBREDDITS = {"buhaydigital", "pinoyprogrammer"}
    MAX_PAGES_PER_SUB = {"forhire": 3}
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
        start_ts = int(start.timestamp())

        for idx, sub in enumerate(self.SUBREDDITS):
            max_pages = self.MAX_PAGES_PER_SUB.get(sub, 1)
            before_ts = None
            sub_posts: List[dict] = []
            sub_succeeded = False
            for page_idx in range(max_pages):
                if (idx or page_idx) and self.db_path:
                    time.sleep(2.0)
                query_params = {"subreddit": sub, "after": after_date, "limit": 100, "sort": "desc"}
                if before_ts is not None:
                    query_params["before"] = before_ts
                url = f"{self.SEARCH_URL}?{urlencode(query_params)}"
                try:
                    resp = self.get_url(url, impersonate="chrome120", timeout=10)
                    if getattr(resp, "status_code", 0) != 200:
                        warnings.append(f"r/{sub}: HTTP {getattr(resp, 'status_code', 'error')}")
                        break
                    payload = resp.json() if callable(getattr(resp, "json", None)) else json.loads(resp.text)
                    posts = payload.get("data")
                    if not isinstance(posts, list):
                        warnings.append(f"r/{sub}: invalid posts payload")
                        break
                    sub_succeeded = True
                    sub_posts.extend(posts)
                    if len(posts) < 100:
                        break
                    oldest = min(
                        (int(p["created_utc"]) for p in posts if isinstance(p, dict) and p.get("created_utc") is not None),
                        default=0,
                    )
                    if not oldest or oldest < start_ts or (before_ts is not None and oldest >= before_ts):
                        break
                    before_ts = oldest - 1
                except Exception as exc:
                    warnings.append(f"r/{sub}: {exc}")
                    break

            if sub_succeeded:
                successful_subs += 1
                raw_count += len(sub_posts)

            for post in sub_posts:
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
                if not (
                    re.search(r"\[\s*hiring\b", raw_title, re.I)
                    or flair in ("hiring", "job opening", "job posting", "job posts", "job")
                ):
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
    revision = 2
    min_window_days = 14
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


class VueJobsConnector(BaseConnector):
    """Official VueJobs RSS feed for remote/PH-eligible frontend and full-stack roles."""

    platform = "VueJobs"
    tier = 2
    is_feed = True
    revision = 1
    min_window_days = 7
    FEED_URL = "https://vuejobs.com/feed"
    MAX_ITEMS = 100

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        self.coverage_warning = ""
        self.last_route = "DIRECT"
        jobs: List[Job] = []
        seen_pairs = set()
        try:
            resp = self.get_url(self.FEED_URL, impersonate="chrome120", timeout=10)
            if getattr(resp, "status_code", 0) != 200:
                raise RuntimeError(f"VueJobs HTTP {getattr(resp, 'status_code', 'error')}")
            root = ET.fromstring(resp.content if getattr(resp, "content", None) else resp.text.encode("utf-8"))
            items = root.findall(".//item")[:self.MAX_ITEMS]
            self.last_raw_count = len(items)
            for item in items:
                title = str(item.findtext("title") or "").strip()
                pub = str(item.findtext("pubDate") or "").strip()
                link = str(item.findtext("guid") or item.findtext("link") or "").strip()
                host = urlsplit(link)
                if not title or not pub or not self.accepts_date(pub) or host.scheme != "https" or not host.netloc:
                    continue
                raw_desc = str(item.findtext("description") or "").strip()
                text_desc = BeautifulSoup(raw_desc, "html.parser").get_text("\n", strip=True)
                if is_scam_or_sketchy_post(title, text_desc):
                    continue
                m_emp = re.search(r"Employer:\s*([^\n]+)", text_desc, re.I)
                m_loc = re.search(r"Location:\s*([^\n]+)", text_desc, re.I)
                comp = m_emp.group(1).strip() if m_emp else "VueJobs Employer"
                loc = m_loc.group(1).strip() if m_loc else "Remote"
                if "remote" in text_desc.lower() and "remote" not in loc.lower():
                    loc = f"{loc} (Remote)"
                pair = (comp.lower(), title.lower())
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if not is_work_authorized_location(loc, title, self.platform, text_desc):
                    continue
                if not self.accepts_opportunity(title, text_desc, allow_va_training=False):
                    continue
                jobs.append(Job(
                    title=title,
                    company=comp,
                    location=loc,
                    platform=self.platform,
                    tier=self.tier,
                    job_url=link,
                    salary=_extract_salary(text_desc),
                    role_category=self.job_role(title, text_desc),
                    experience_level=classify_experience_level(title, text_desc),
                    description=text_desc,
                    date_posted=pub,
                ))
        except Exception as exc:
            self.last_error = str(exc) or type(exc).__name__
        return jobs


class LaraJobsConnector(BaseConnector):
    """Official LaraJobs RSS feed for remote Laravel/PHP/full-stack roles."""

    platform = "LaraJobs"
    tier = 2
    is_feed = True
    revision = 1
    min_window_days = 14
    FEED_URL = "https://larajobs.com/feed"

    def fetch(self, query: str = "", location: str = "") -> List[Job]:
        self.last_error = ""
        self.coverage_warning = ""
        self.last_route = "DIRECT"
        jobs: List[Job] = []
        try:
            resp = self.get_url(self.FEED_URL, impersonate="chrome120", timeout=10)
            if getattr(resp, "status_code", 0) != 200:
                raise RuntimeError(f"LaraJobs HTTP {getattr(resp, 'status_code', 'error')}")
            root = ET.fromstring(resp.content if getattr(resp, "content", None) else resp.text.encode("utf-8"))
            items = root.findall(".//item")
            self.last_raw_count = len(items)
            for item in items:
                title = str(item.findtext("title") or "").strip()
                pub = str(item.findtext("pubDate") or "").strip()
                link = str(item.findtext("link") or item.findtext("guid") or "").strip()
                host = urlsplit(link)
                if not title or not pub or not self.accepts_date(pub) or host.scheme != "https" or not host.netloc:
                    continue
                comp = str(
                    item.findtext("{https://larajobs.com}company")
                    or item.findtext("{http://purl.org/dc/elements/1.1/}creator")
                    or "LaraJobs Employer"
                ).strip()
                loc = str(item.findtext("{https://larajobs.com}location") or "Remote").strip()
                salary = str(item.findtext("{https://larajobs.com}salary") or "").strip()
                tags = str(item.findtext("{https://larajobs.com}tags") or "").strip()
                raw_desc = BeautifulSoup(str(item.findtext("description") or ""), "html.parser").get_text(" ", strip=True)
                desc = " | ".join(part for part in (tags, raw_desc) if part)
                if is_scam_or_sketchy_post(title, desc):
                    continue
                if not is_work_authorized_location(loc, title, self.platform, desc):
                    continue
                if not self.accepts_opportunity(title, desc, allow_va_training=False):
                    continue
                jobs.append(Job(
                    title=title,
                    company=comp,
                    location=loc,
                    platform=self.platform,
                    tier=self.tier,
                    job_url=link,
                    salary=salary,
                    role_category=self.job_role(title, desc),
                    experience_level=classify_experience_level(title, desc),
                    description=desc,
                    date_posted=pub,
                ))
        except Exception as exc:
            self.last_error = str(exc) or type(exc).__name__
        return jobs
