import re

JUNIOR_PATTERNS = [
    r"\bjunior\b",
    r"\bjr\.?(?!\s*-\s*\d+)\b",
    r"\bjr/entry\b",
    r"\bentry[- ]level\b",
    r"\bentrylevel\b",
    r"(?<!data\s)\bentry(?!\s*(?:data|clerk|operator|records|accounting))\b",
    r"\bassociate\b",
    r"(?<!inter)\bintern(?:ship|s)?(?!\w)\b",
    r"\btrainee\b",
    r"\btraining\b",
    r"\bapprentice\b",
    r"\bapprenticeship\b",
    r"\bfresh[- ]?grad(?:uate)?s?\b",
    r"\bnew[- ]?grad(?:uate)?s?\b",
    r"\bcollege[- ]?grad(?:uate)?s?\b",
    r"\bgraduate\b",
    r"\bearly[- ]career\b",
    r"\bearly career\b",
    r"\bbeginner\b",
    r"\bbootcamp\b",
    r"\bojt\b",
    r"\bon[- ]the[- ]job[- ]train(?:ing|ee)\b",
    r"\blevel[- ]?1\b",
    r"\bl1\b",
    r"\bdeveloper[- ]?i\b",
    r"\bengineer[- ]?i\b",
    r"\bprogrammer[- ]?i\b",
    r"\bqa[- ]?engineer[- ]?i\b",
    r"\bsoftware developer 1\b",
    r"\bsoftware engineer 1\b",
    r"\bsde[- ]?i\b",
    r"\bsoftware development engineer[- ]?i\b",
    r"\bgraduate[- ](?:software[- ]|developer[- ]|engineer[- ]|program)\b",
    r"\bentry[- ]level[- ](?:software[- ]|developer[- ]|engineer[- ]|programmer)\b",
    r"\b(?:software|web|mobile|android|frontend|backend|full[- ]?stack)\s*(?:engineer|developer|programmer)\s*[-–/]\s*entry[- ]level\b",
    r"\b(?:software|engineering)\s*(?:trainee|apprentice)\b",
    r"\b(?:software|android|web|mobile|technology|programmer)\s*(?:developer\s*)?intern(?:ship)?\b",
    r"\b(?:software|developer|technology|programmer)\s*intern\b",
    r"\b0[- ]?1\s*(?:yr|year|years)?\b",
    r"\b0[- ]?2\s*(?:yrs|years|yr)\b",
    r"\b1[- ]?2\s*(?:yrs|years|yr)\b",
    r"\b< ?1\s*(?:yr|year)\b",
    r"\b< ?2\s*(?:yrs|years)\b",
    r"\bno[- ]experience\b",
    r"\bzero[- ]experience\b",
    r"\bwithout[- ]experience\b",
    r"\bno experience required\b",
    r"\bopen for fresh\b"
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
    r"\bapplication (?:engineer|developer)\b", r"\bproduct (?:engineer|developer)\b",
    r"\bplatform (?:engineer|developer)\b", r"\bsystems (?:engineer|developer)\b",
    r"\bweb (?:dev|developer)\b", r"\bweb application (?:developer|engineer)\b",
    r"\bapi (?:developer|engineer)\b", r"\bintegration (?:developer|engineer)\b",
    r"\bprogrammer\b", r"\bcomputer programmer\b",
    r"\bpython (?:dev|developer|engineer)\b", r"\breact\b", r"\bnode(?:\.js)?\b",
    r"\bjavascript\b", r"\btypescript\b", r"\bgolang\b", r"\bgo (?:developer|dev|engineer)\b",
    r"\bjava (?:developer|dev|engineer)?\b", r"\bc#\b", r"\b\.net\b", r"\basp\.net\b",
    r"\bphp\b", r"\blaravel\b", r"\bsymfony\b", r"\bruby\b", r"\brails\b", r"\bruby on rails\b",
    r"\bspring boot\b", r"\bspring framework\b", r"\bfastapi\b", r"\bdjango\b", r"\bflask\b",
    r"\bmobile\b", r"\bandroid\b", r"\bios\b", r"\bflutter\b", r"\breact native\b",
    r"\bkotlin\b", r"\bswift\b", r"\bswiftui\b", r"\bjetpack compose\b", r"\bcompose multiplatform\b",
    r"\bkmp\b", r"\bkmm\b", r"\bionic\b", r"\bcapacitor\b", r"\bxamarin\b", r"\bmaui\b",
    r"\bdevops\b", r"\bcloud\b", r"\baws\b", r"\bazure\b", r"\bgcp\b", r"\bsre\b",
    r"\bsite reliability\b", r"\bkubernetes\b", r"\bdocker\b", r"\bterraform\b", r"\bci/cd\b",
    r"\bqa\b", r"\bquality assurance\b", r"\btester\b", r"\btesting\b", r"\bsdet\b",
    r"\btest automation\b", r"\bqa automation\b", r"\bplaywright\b", r"\bcypress\b", r"\bselenium\b",
    r"\bgame (?:developer|programmer|engineer)\b", r"\bgameplay\b", r"\bunity\b", r"\bunreal engine\b",
    r"\bembedded\b", r"\bfirmware\b", r"\biot\b", r"\bsecurity engineer\b", r"\bdevsecops\b",
    r"\bsolutions architect\b", r"\bsoftware architect\b"
]

DATA_AI_PATTERNS = [
    r"\bdata analyst\b", r"\bdata analytics\b", r"\bdata engineer\b", r"\bdata platform\b",
    r"\bmachine learning\b", r"\bml\b", r"\bml engineer\b", r"\bai\b", r"\bai engineer\b",
    r"\bai developer\b", r"\bai application\b", r"\bgenerative ai\b", r"\bgen ai\b",
    r"\bllm\b", r"\bllm engineer\b", r"\bmlops\b",
    r"\bdata scientist\b", r"\bnlp\b", r"\bdeep learning\b", r"\bcomputer vision\b",
    r"\bbi developer\b", r"\bbusiness intelligence\b", r"\banalytics engineer\b",
    r"\bartificial intelligence\b", r"\bbig data\b", r"\bspark\b", r"\bpyspark\b",
    r"\bairflow\b", r"\bdbt\b", r"\bdatabricks\b", r"\bsnowflake\b", r"\bbigquery\b",
    r"\blangchain\b", r"\blanggraph\b", r"\bllamaindex\b", r"\brag\b", r"\bprompt engineering\b"
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
        if re.search(r"\bjunior\s*(?:to|or|/|-)\s*senior\b", text):
            return "Junior / Entry"
        return "Senior / Lead"
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
