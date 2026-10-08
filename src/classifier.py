import re

JUNIOR_PATTERNS = [
    r"\bjunior\b", r"\bjr\.?\b", r"\bentry[- ]level\b", r"\bgraduate\b",
    r"\bfresh grad(?:uate)?\b", r"\bassociate\b", r"\bintern\b", r"\binternship\b",
    r"\b0-1 year\b", r"\b0-2 years\b", r"\btrainee\b"
]

SENIOR_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b",
    r"\barchitect\b", r"\bstaff\b", r"\bhead of\b", r"\bdirector\b",
    r"\bmanager\b", r"\b5\+ years\b", r"\b7\+ years\b"
]

MID_PATTERNS = [
    r"\bmid[- ]level\b", r"\bintermediate\b", r"\b2-4 years\b", r"\b3-5 years\b"
]

WEB_PATTERNS = [
    r"\bfrontend\b", r"\bfront[- ]end\b", r"\bbackend\b", r"\bback[- ]end\b",
    r"\bfull[- ]?stack\b", r"\bsoftware (?:engineer|dev|developer)\b",
    r"\bweb (?:dev|developer)\b", r"\bpython (?:dev|developer|engineer)\b",
    r"\breact\b", r"\bnode(?:\.js)?\b",
    r"\bjavascript\b", r"\btypescript\b", r"\bgolang\b", r"\bjava\b", r"\bc#\b", r"\b\.net\b",
    r"\bmobile\b", r"\bandroid\b", r"\bios\b", r"\bflutter\b", r"\breact native\b",
    r"\bdevops\b", r"\bcloud\b", r"\baws\b", r"\bsre\b", r"\bsite reliability\b", r"\bkubernetes\b", r"\bdocker\b",
    r"\bqa\b", r"\bquality assurance\b", r"\btester\b", r"\btesting\b", r"\bsdet\b"
]

DATA_AI_PATTERNS = [
    r"\bdata analyst\b", r"\bdata analytics\b", r"\bdata engineer\b",
    r"\bmachine learning\b", r"\bml\b", r"\bml engineer\b", r"\bai\b", r"\bai engineer\b",
    r"\bdata scientist\b", r"\bnlp\b", r"\bdeep learning\b", r"\bcomputer vision\b",
    r"\bbi developer\b", r"\bbusiness intelligence\b", r"\banalytics engineer\b",
    r"\bartificial intelligence\b"
]

def classify_experience_level(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()
    is_junior = any(re.search(pat, text) for pat in JUNIOR_PATTERNS)
    is_senior = any(re.search(pat, text) for pat in SENIOR_PATTERNS)
    is_mid = any(re.search(pat, text) for pat in MID_PATTERNS)

    if is_junior and not is_senior:
        return "Junior / Entry"
    if is_senior and not is_junior:
        return "Senior / Lead"
    if is_junior and is_senior:
        return "Junior / Entry"
    if is_mid:
        return "Mid-Level"
    return "Mid-Level" if any(re.search(pat, text) for pat in WEB_PATTERNS + DATA_AI_PATTERNS) else "Unspecified"

def classify_role(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()
    matches_web = any(re.search(pat, text) for pat in WEB_PATTERNS)
    matches_data = any(re.search(pat, text) for pat in DATA_AI_PATTERNS)

    if matches_web and matches_data:
        return "Both"
    if matches_data:
        return "Data/AI/ML"
    if matches_web:
        return "Web/Software Dev"
    return "Web/Software Dev"
