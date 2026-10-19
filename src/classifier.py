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
    r"\bmid[- ]level\b", r"\bintermediate\b", r"\b2-4 years\b", r"\b3-5 years\b",
    r"\bdeveloper[- ]?ii\b", r"\bengineer[- ]?ii\b", r"\bprogrammer[- ]?ii\b", r"\bqa[- ]?engineer[- ]?ii\b", r"\bsde[- ]?ii\b",
    r"\bdeveloper[- ]?iii\b", r"\bengineer[- ]?iii\b", r"\bprogrammer[- ]?iii\b", r"\bsde[- ]?iii\b",
    r"\bdeveloper[- ]?2\b", r"\bengineer[- ]?2\b", r"\bprogrammer[- ]?2\b", r"\bsde[- ]?2\b",
    r"\bdeveloper[- ]?3\b", r"\bengineer[- ]?3\b", r"\bprogrammer[- ]?3\b", r"\bsde[- ]?3\b",
    r"\blevel[- ]?2\b", r"\bl2\b", r"\blevel[- ]?3\b", r"\bl3\b"
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
    r"\bjava (?:developer|dev|engineer)?\b", r"\bc#(?:[\s/,\.-]|$)", r"\b\.net\b", r"\basp\.net\b",
    r"\bphp\b", r"\blaravel\b", r"\bsymfony\b", r"\bruby\b", r"\brails\b", r"\bruby on rails\b",
    r"\bshopify\b", r"\bwordpress\b", r"\bdatabase administrator\b", r"\bdba\b",
    r"\bsysadmin\b", r"\bsystem(?:s)? administrator\b", r"\bnetwork engineer\b",
    r"\bsecurity analyst\b", r"\bapplication security engineer\b", r"\bsecurity engineer\b",
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

NON_TECH_BLACKLIST = [
    r"\baccountant\b", r"\baccounting\b", r"\bbookkeeper\b", r"\bbookkeeping\b",
    r"\bnurse\b", r"\bnursing\b", r"\bmedical billing\b", r"\bmedical coder\b",
    r"\bmedical coding\b", r"\bmedical content\b", r"\bhemodialysis\b", r"\bpharmacist\b",
    r"\bdoctor\b", r"\bphysician\b", r"\bphysical therapist\b", r"\bcashier\b", r"\bteller\b",
    r"\btelemarketer\b", r"\bfinancial advisor\b", r"\baudit\b", r"\bauditor\b",
    r"\bfinancial controller\b", r"\btax associate\b", r"\btax specialist\b",
    r"\bpayroll\b", r"\bunderwriter\b", r"\breceptionist\b", r"\bcall center agent\b",
    r"\bcustomer service representative\b", r"\bcsr\b", r"\bscientific communications\b",
    r"\bpainter\b", r"\bgardening\b", r"\bfacility maintenance\b", r"\bbidding specialist\b",
    r"\bleasing\b", r"\bleasing officer\b", r"\bpatient care\b", r"\bdental\b",
    r"\bfinancial wellness\b", r"\brisk management officer\b", r"\baccounts receivable\b",
    r"\baccounts payable\b", r"\btreasury analyst\b", r"\bcost accounting\b",
    r"\bcivil registry\b", r"\bdata encoder\b", r"\bsocial media content intern\b",
    r"\bschool engagement\b", r"\btechnical sales representative\b", r"\bsales and marketing\b",
    r"\bsales representative\b", r"\bsales agent\b", r"\bsales development\b",
    r"\bsales manager\b", r"\bsales assistant\b", r"\bmecánico\b", r"\bautomotriz\b",
    r"\bdispense technician\b", r"\bcider\b", r"\bcrypto trader\b", r"\boperations manager\b",
    r"\bhead of operations\b", r"\bpeople operations\b", r"\bhr specialist\b",
    r"\bhuman resources\b", r"\brecruiter\b", r"\btalent acquisition\b", r"\bcredentialing specialist\b"
]

TECH_WHITELIST_OVERRIDE = [
    r"\bdeveloper\b", r"\bengineer\b", r"\bprogrammer\b", r"\bsoftware\b",
    r"\bdevops\b", r"\bsdet\b", r"\barchitect\b", r"\bfrontend\b", r"\bbackend\b",
    r"\bfull[- ]?stack\b", r"\bandroid\b", r"\bios\b", r"\bdata engineer\b",
    r"\bweb dev\b", r"\bweb application\b", r"\bdatabase administrator\b", r"\bdba\b",
    r"\bcyber\s?security\b", r"\binfosec\b", r"\bweb designer\b", r"\bui/ux\b",
    r"\bqa\b", r"\bquality assurance\b", r"\bsysadmin\b", r"\bsystem(?:s)? administrator\b",
    r"\bnetwork engineer\b", r"\bcloud\b", r"\bproduct designer\b", r"\bquality engineering\b"
]

VA_PATTERNS = [
    r"\bvirtual assistant\b",
    r"\bvirtual administrative assistant\b",
    r"(?<!,\s)\bva\b(?!\s*[-–/]\s*gov)(?!\s*,\s*(?:usa|us|united states))\b",
    r"\bexecutive assistant\b",
    r"\badmin assistant\b",
    r"\badministrative assistant\b",
    r"\bremote assistant\b",
    r"\bcyberbacker\b",
    r"\bathena\b",
    r"\bvirtudesk\b",
    r"\bpineapple staffing\b",
    r"\bdata entry\b",
    r"\bemail management\b",
    r"\bcalendar management\b",
    r"\bcustomer support\b",
    r"\bresearch assistant\b"
]

VA_TRAINING_PATTERNS = [
    r"\bwith training\b", r"\bpaid training\b", r"\bwill train\b", r"\btraining provided\b",
    r"\btraining\b", r"\bno experience\b", r"\bno experience required\b", r"\bzero experience\b",
    r"\bentry[- ]level\b", r"\bjunior\b", r"\btrainee\b", r"\bopen for fresh\b",
    r"\bopen to fresh\b", r"\bbeginner\b", r"\bbeginners welcome\b", r"(?<!data\s)\bentry\s*(?:level|position|role)?\b",
    r"\bcyberbacker\b", r"\bathena\b", r"\bvirtudesk\b", r"\bpineapple staffing\b",
    r"\bno work experience\b", r"\bcomplete training\b", r"\bfull training\b", r"\bfree training\b"
]

def is_virtual_assistant(title: str, description: str = "") -> bool:
    t_str = str(title or "")
    d_str = str(description or "")
    title_lower = t_str.lower()
    text = f"{t_str} {d_str}".lower()
    if re.search(r"\bvirtual assistant\b", title_lower):
        return True
    # If title matches tech engineering override, do not misclassify as VA (e.g., Arlington, VA)
    if any(re.search(pat, title_lower) for pat in TECH_WHITELIST_OVERRIDE):
        return False
    return any(re.search(pat, text) for pat in VA_PATTERNS)

def is_entry_training_va(title: str, description: str = "") -> bool:
    t_str = str(title or "")
    d_str = str(description or "")
    text = f"{t_str} {d_str}".lower()
    if not is_virtual_assistant(t_str, d_str):
        return False
    return any(re.search(pat, text) for pat in VA_TRAINING_PATTERNS)

def is_non_tech(title: str, description: str = "") -> bool:
    t_str = str(title or "")
    d_str = str(description or "")
    title_lower = t_str.lower()
    text = f"{t_str} {d_str}".lower()
    has_tech_override = any(re.search(pat, title_lower) for pat in TECH_WHITELIST_OVERRIDE)
    if has_tech_override:
        return False
    if is_virtual_assistant(t_str, d_str):
        return False
    return any(re.search(pat, text) for pat in NON_TECH_BLACKLIST)

def classify_experience_level(title: str, description: str = "") -> str:
    t_str = str(title or "")
    d_str = str(description or "")
    title_lower = t_str.lower()
    desc_lower = d_str.lower()
    if is_entry_training_va(t_str, d_str):
        return "Junior / Entry"
    is_junior = any(re.search(pat, title_lower) for pat in JUNIOR_PATTERNS)
    is_senior = any(re.search(pat, title_lower) for pat in SENIOR_PATTERNS)
    is_mid = any(re.search(pat, title_lower) for pat in MID_PATTERNS)

    if is_junior and not is_senior:
        return "Junior / Entry"
    if is_senior and not is_junior:
        return "Senior / Lead"
    if is_junior and is_senior:
        if re.search(r"\bjunior\s*(?:to|or|/|-)\s*senior\b", title_lower):
            return "Junior / Entry"
        return "Senior / Lead"
    if is_mid:
        return "Mid-Level"
    if any(re.search(pat, desc_lower) for pat in JUNIOR_PATTERNS):
        return "Junior / Entry"
    matches_tech = any(re.search(pat, title_lower) for pat in WEB_PATTERNS + DATA_AI_PATTERNS + TECH_WHITELIST_OVERRIDE)
    return "Mid-Level" if matches_tech else "Unspecified"

def is_relevant_opportunity(title: str, description: str = "", allow_va_training: bool = True) -> bool:
    t_str = str(title or "")
    d_str = str(description or "")
    if is_non_tech(t_str, d_str):
        return False

    # Strictly reject Senior / Lead roles to match candidate's matrix
    if classify_experience_level(t_str, d_str) == "Senior / Lead":
        return False

    # Virtual Assistant roles must strictly be entry-level or provide training
    if is_virtual_assistant(t_str, d_str):
        if allow_va_training:
            return is_entry_training_va(t_str, d_str)
        return False

    text = f"{t_str} {d_str}".lower()
    is_web = any(re.search(pat, text) for pat in WEB_PATTERNS)
    is_data = any(re.search(pat, text) for pat in DATA_AI_PATTERNS)
    is_tech = any(re.search(pat, text) for pat in TECH_WHITELIST_OVERRIDE)
    return is_web or is_data or is_tech

def classify_role(title: str, description: str = "") -> str:
    t_str = str(title or "")
    d_str = str(description or "")
    text = f"{t_str} {d_str}".lower()
    if is_virtual_assistant(t_str, d_str):
        return "Virtual Assistant"
    matches_web = any(re.search(pat, text) for pat in WEB_PATTERNS)
    matches_data = any(re.search(pat, text) for pat in DATA_AI_PATTERNS)

    if matches_web and matches_data:
        return "Both"
    if matches_data:
        return "Data/AI/ML"
    if matches_web:
        return "Web/Software Dev"
    return "Web/Software Dev"
