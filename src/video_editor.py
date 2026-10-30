"""Conservative discovery rules for the candidate's basic CapCut portfolio."""
import re

from src.classifier import is_relevant_opportunity, is_work_authorized_location
from src.models import is_today_or_yesterday, normalize_date, scrape_date_window

VIDEO_SOURCES = {"OnlineJobs.ph", "Freelancer", "Indeed", "JobStreet"}
VIDEO_QUERIES = ("CapCut", "short form video editor", "gaming video editor", "reels editor")


def is_video_candidate(title, description=""):
    return bool(re.search(r"\b(?:video edit(?:or|ing)|capcut.{0,30}edit(?:or|ing)|edit(?:or|ing).{0,30}capcut|(?:reels?|short[- ]form|gaming|tiktok|ugc|youtube shorts)\s+(?:video\s+)?edit(?:or|ing))\b",
                          title, re.I)) and not re.search(r"\b(?:senior|lead|head|manager|director)\b", title, re.I)


def video_fit(title, description):
    """Return a reason for rejection, or an empty string for a supported basic edit."""
    from bs4 import BeautifulSoup
    text = BeautifulSoup(description or "", "html.parser").get_text("\n", strip=True)
    if not is_video_candidate(title, text):
        return "Not an individual video editor role"
    if len(text) < 140 or re.search(r"(?:see more|\.\.\.|…)\s*$", text, re.I):
        return "Full job description needed"
    optional_section = False
    for line in re.split(r"[\n.!?;]+", text):
        line = line.strip().lower()
        if not line:
            continue
        if re.match(r"(?:bonus|nice[- ]to[- ]have|preferred|optional)\b", line):
            optional_section = True
        if re.match(r"(?:requirements?|responsibilities|must[- ]have|how to apply|qualifications)\b", line):
            optional_section = False
        if optional_section or re.search(r"\b(?:optional|not required|nice[- ]to[- ]have|a plus|preferred|no (?:heavy |advanced )?(?:vfx|motion graphics)|without (?:vfx|motion graphics))\b", line):
            continue
        if re.search(r"\b(?:after effects|premiere pro|davinci resolve|final cut|blender)\b", line):
            if not re.search(r"\b(?:or|any (?:editing )?software|tool of your choice)\b", line):
                return "Other editing software required"
        if re.search(r"\b(?:advanced (?:video )?(?:editing|motion|color)|vfx|visual effects|3d|rotoscop\w*|compositing|motion graphics|cinematic color grading|expert[- ]level)\b", line):
            return "Advanced editing required"
        if re.search(r"\b\d+\+?\s*years?\b", line) and re.search(r"\b(?:experience|required|minimum|at least|must)\b", line):
            return "Required editing tenure needs confirmation"
        if re.search(r"\b(?:spanish|german|french|japanese|korean|mandarin|arabic|portuguese)\b", line):
            return "Additional language requirement needs confirmation"
        if re.search(r"\b(?:photoshop|illustrator|canva|graphic design|social media management|manage (?:our |the )?social|film (?:the |our )?footage|shoot (?:the |our )?footage)\b", line):
            return "Additional production/design duties need confirmation"
        if re.search(r"\b(?:inbox management|calendar management|(?:manage|managing)\b.{0,40}(?:calendar|instagram|tiktok|accounts)|content calendar|customer support|publish(?:ing)? posts|post(?:ing)? (?:the |our )?(?:videos|content) (?:on|to)|(?:reply|respond|responding)\b.{0,35}(?:comments|dms)|outreach messages|send first[- ]touch)\b", line):
            return "Additional admin/publishing duties need confirmation"
    if not re.search(r"\b(?:capcut|any (?:editing )?software|tool of your choice)\b", text, re.I):
        return "CapCut compatibility unverified"
    if not re.search(r"\b(?:short[- ]form|reels?|tiktok|shorts|vertical|9:16|gaming|tutorial)\b", title + " " + text, re.I):
        return "Outside short-form/tutorial scope"
    if not re.search(r"\b(?:basic|simple|template|trim|cuts?|captions?|subtitles?|talking[- ]head|repurpos\w*|tutorial)\b", text, re.I):
        return "Basic editing scope unverified"
    return ""


def attention_check(description):
    return bool(re.search(r"if you are (?:an? )?(?:ai|bot)|ignore (?:all |previous )?instructions|(?:start|begin) (?:your |the )?(?:application|proposal|reply|message)|include (?:the )?(?:word|keyword)|prove you (?:are|have)", description, re.I)
                or re.search("[\u200b-\u200d\ufeff]", description))


def collectable_job(job):
    if job.role_category == "Video Editor":
        start, end = scrape_date_window(days=7)
        date = normalize_date(job.date_posted)
        return (job.platform in VIDEO_SOURCES and bool(date)
                and start.date().isoformat() <= date < end.date().isoformat()
                and not video_fit(job.title, job.description)
                and is_work_authorized_location(job.location, job.title, job.platform, job.description))
    return (is_today_or_yesterday(job.date_posted)
            and is_relevant_opportunity(job.title, job.description, allow_va_training=True))
