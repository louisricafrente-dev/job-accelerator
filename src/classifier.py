import re

REMOTE_PATTERNS = [

    r"\bremote\b", r"\bwfh\b", r"\bwork from home\b", r"\banywhere\b",
    r"\bworldwide\b", r"\btelecommute\b", r"\bvirtual\b", r"\bhome-based\b",
    r"\bwork from anywhere\b", r"\bremoto\b", r"\bdistributed\b"
]

REMOTE_KEYWORDS = REMOTE_PATTERNS

DEDICATED_REMOTE_PLATFORMS = {
    "remote ok", "we work remotely", "remotive", "himalayas", "jobicy", "arc",
    "contra", "flexjobs", "upwork", "freelancer"
}

DEDICATED_PH_PLATFORMS = {
    "jobstreet", "onlinejobs.ph", "bossjob", "kalibrr"
}

FOREIGN_BOARDS = {
    "naukri", "bdjobs", "bayt", "hellowork"
}

FOREIGN_LOCATION_PATTERNS = [
    # India
    r"\bindia\b", r"\bmumbai\b", r"\bpune\b", r"\bpalampur\b", r"\bkochi\b", r"\bhyderabad\b",
    r"\bdelhi\b", r"\bnew delhi\b", r"\bbengaluru\b", r"\bbangalore\b", r"\bchennai\b", r"\bkolkata\b",
    r"\bnoida\b", r"\bgurugram\b", r"\bgurgaon\b", r"\bahmedabad\b", r"\bjaipur\b",
    r"\bhimachal\b", r"\bkarnataka\b", r"\bmaharashtra\b", r"\btamil nadu\b", r"\btelangana\b",
    r"\bkerala\b", r"\bharyana\b", r"\buttar pradesh\b", r"\bwest bengal\b", r"\bgujarat\b",
    # Bangladesh
    r"\bbangladesh\b", r"\bdhaka\b", r"\bchittagong\b", r"\bgulshan\b", r"\buttara\b",
    r"\bsylhet\b", r"\brajshahi\b", r"\bkhulna\b", r"\bbarisal\b", r"\brangpur\b",
    r"\bcomilla\b", r"\bgazipur\b", r"\bnarayanganj\b",
    # South Asia / Middle East
    r"\bpakistan\b", r"\bkarachi\b", r"\blahore\b", r"\bislamabad\b", r"\bnepal\b",
    r"\bkathmandu\b", r"\bsri lanka\b", r"\bcolombo\b", r"\buae\b", r"\bdubai\b",
    r"\babu dhabi\b", r"\bsaudi arabia\b", r"\briyadh\b", r"\bjeddah\b", r"\bqatar\b",
    r"\bdoha\b", r"\bkuwait\b", r"\bbahrain\b", r"\boman\b",
    # Americas / Europe / Others
    r"\bunited states\b", r"\busa\b", r"\bcanada\b", r"\bunited kingdom\b", r"\buk\b",
    r"\blondon\b", r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b", r"\bsingapore\b",
    r"\bmalaysia\b", r"\bkuala lumpur\b", r"\bgermany\b", r"\bberlin\b", r"\bmunich\b",
    r"\bfrance\b", r"\bparis\b", r"\bnetherlands\b", r"\bamsterdam\b", r"\bjapan\b",
    r"\btokyo\b"
]

PH_LOCATION_PATTERNS = [
    r"\bphilippines\b", r"\bph\b", r"\bpilipinas\b",
    # Metro Manila & NCR
    r"\bmetro manila\b", r"(?<!delhi[\s\/\-])\bncr\b", r"\bnational capital region\b",
    r"\bmanila\b", r"\bquezon\b", r"\btaguig\b", r"\bmakati\b", r"\bpasig\b",
    r"\bmandaluyong\b", r"\bpasay\b", r"\bparanaque\b", r"\bparañaque\b",
    r"\blas pinas\b", r"\blas piñas\b", r"\bmuntinlupa\b", r"\bmarikina\b",
    r"\bcaloocan\b", r"\bmalabon\b", r"\bnavotas\b", r"\bvalenzuela\b",
    r"\bsan juan\b", r"\bpateros\b", r"\bbgc\b", r"\bbonifacio\b", r"\bortigas\b",
    r"\bayala\b", r"\balabang\b", r"\bfilinvest\b", r"\brockwell\b",
    r"\beastwood\b", r"\baraneta\b", r"\bcubao\b", r"\bdiliman\b", r"\bpaco\b",
    r"\bintramuros\b", r"\bermita\b", r"\bmalate\b", r"\bbinondo\b", r"\bsampaloc\b",
    # Provinces & Regions
    r"\bcebu\b", r"\bmandaue\b", r"\blapu-lapu\b", r"\bdavao\b", r"\bclark\b",
    r"\bangeles\b", r"\bpampanga\b", r"\bsan fernando\b", r"\bcavite\b",
    r"\bbacoor\b", r"\bimus\b", r"\bdasmarinas\b", r"\bdasmariñas\b",
    r"\bgeneral trias\b", r"\bsilang\b", r"\blaguna\b", r"\bsanta rosa\b",
    r"\bsta\. rosa\b", r"\bbinan\b", r"\bbiñan\b", r"\bcalamba\b",
    r"\blos banos\b", r"\blos baños\b", r"\bsan pedro\b", r"\bcabuyao\b",
    r"\bbatangas\b", r"\blipa\b", r"\btanauan\b", r"\bsto\. tomas\b",
    r"\bsanto tomas\b", r"\brizal\b", r"\bantipolo\b", r"\bcainta\b",
    r"\btaytay\b", r"\bangono\b", r"\bsan mateo\b", r"\bbulacan\b",
    r"\bmalolos\b", r"\bmeycauayan\b", r"\bmarilao\b", r"\bsan jose del monte\b",
    r"\bbaguio\b", r"\bbenguet\b", r"\bbataan\b", r"\bmariveles\b",
    r"\bbalanga\b", r"\biloilo\b", r"\bbacolod\b", r"\bnegros\b",
    r"\bcagayan de oro\b", r"\bcdo\b", r"\bmisamis\b", r"\bzamboanga\b",
    r"\bgeneral santos\b", r"\bgensan\b", r"\bcamarines\b", r"\bdaet\b",
    r"\bnaga\b", r"\bbicol\b", r"\blegazpi\b", r"\balbay\b", r"\btarlac\b",
    r"\bnueva ecija\b", r"\bla union\b", r"\bpangasinan\b", r"\bsubic\b",
    r"\bzambales\b", r"\blucena\b", r"\bmimaropa\b", r"\bcalabarzon\b",
    # Indeed PH codes
    r"\bp00\b", r"\bp01\b", r"\bp02\b", r"\bp03\b", r"\bp04\b", r"\bp05\b",
    r"\bp06\b", r"\bp07\b", r"\bp08\b", r"\bp09\b", r"\bp10\b", r"\b04a\b", r"\b04b\b"
]

def is_work_authorized_location(location: str, title: str = "", platform: str = "", description: str = "") -> bool:
    loc = (location or "").strip().lower()
    t = (title or "").strip().lower()
    plat = (platform or "").strip().lower()
    desc = (description or "").lower()
    foreign = FOREIGN_LOCATION_PATTERNS + [
        r"\bu\.?s\.?\b", r"\bpoland\b", r"\bpolish\b", r"\bvancouver\b", r"\bcincinnati\b",
        r"\beurope\b", r"\beu\b", r"\beea\b", r"\bemea\b", r"\bamericas\b",
        r"\blatin america\b", r"\blatam\b", r"\bnew zealand\b", r"\bireland\b",
        r"\bspain\b", r"\bitaly\b", r"\bportugal\b", r"\bbrazil\b", r"\bmexico\b",
    ]
    # Remote work can still require residence or work authorization abroad.
    foreign_name = "(?:" + "|".join(foreign) + ")"
    restrictions = [
        rf"{foreign_name}[- ]only\b",
        rf"\bonly\s+(?:in|within|from|for)\s+(?:the\s+)?{foreign_name}",
        rf"\b(?:must|need to|required to)\s+(?:be\s+)?(?:reside|live|based|located|eligible to work|authorized to work)\b[^.\n]{{0,100}}{foreign_name}",
        rf"\b(?:residency|residence|work authorization|work permit|citizenship)\b[^.\n]{{0,60}}{foreign_name}",
        rf"{foreign_name}[^.\n]{{0,50}}\b(?:residents? only|citizens? only|work authorization required)\b",
        rf"\bremote\s+(?:within|in)\s+(?:the\s+)?{foreign_name}",
    ]
    if any(re.search(pattern, f"{loc}\n{t}\n{desc}") for pattern in restrictions):
        return False
    ph_location = any(re.search(pat, loc) for pat in PH_LOCATION_PATTERNS)
    worldwide = bool(re.search(r"\b(?:worldwide|anywhere|global|apac|asia|asia[- ]pacific|southeast asia)\b", loc))
    if any(re.search(pat, loc) for pat in foreign) and not (ph_location or worldwide):
        return False
    remote_label = re.fullmatch(
        r"(?:remote|wfh|work from home|telecommute|remoto|distributed|home-based)"
        r"(?:\s*[/()-]?\s*(?:contract|freelance|location unverified)\s*\)?)*", loc)
    if loc and not (ph_location or worldwide or remote_label):
        return False

    # Unrestricted remote feeds can be considered only after geographic exclusions.
    if plat in DEDICATED_REMOTE_PLATFORMS:
        return True

    # 2. Remote check (in location, title, or description)
    text_to_check = f"{loc} {t}"
    if any(re.search(pat, text_to_check) for pat in REMOTE_PATTERNS):
        return True
    if any(re.search(pat, desc) for pat in [r"\b100%\s*remote\b", r"\bfully\s*remote\b", r"\bwork\s*from\s*home\b"]):
        return True

    # 3. Foreign board check (Naukri, BDJobs, Bayt, HelloWork are inherently non-PH)
    # Since step 2 passed without being remote, any listing from these boards is foreign onsite!
    if plat in FOREIGN_BOARDS:
        return False

    # 4. Foreign location check
    if any(re.search(pat, loc) for pat in FOREIGN_LOCATION_PATTERNS):
        return False

    # 5. Dedicated Philippine platforms
    if plat in DEDICATED_PH_PLATFORMS:
        return True

    # 6. Philippine location check
    if any(re.search(pat, loc) for pat in PH_LOCATION_PATTERNS):
        return True

    # Default: if neither verified remote nor verified Philippine location, reject.
    return False


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
    r"\bmachine learning\b", r"\bml (?:engineer|developer|researcher|scientist|model|pipeline)\b", r"\bai\b", r"\bai engineer\b",
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
    r"\bhuman resources\b", r"\brecruiter\b", r"\btalent acquisition\b", r"\bcredentialing specialist\b",
    r"\bgraphic designer\b", r"\bvideo editor\b", r"\bcopywriter\b", r"\bcontent writer\b",
    r"\btranscriptionist\b", r"\bcontent moderator\b", r"\bcnc machinist\b", r"\bmachinist\b",
    r"\belectrician\b", r"\bplumber\b", r"\bcarpenter\b", r"\bwelder\b", r"\bdriver\b", r"\brider\b"
]

TECH_WHITELIST_OVERRIDE = [
    r"\bdeveloper\b",
    r"\bprogrammer\b",
    r"\bcomputer programmer\b",
    r"\bsoftware\b",
    r"\b(?:software|web|frontend|front[- ]?end|backend|back[- ]?end|full[- ]?stack|mobile|android|ios|cloud|devops|sre|qa|sdet|data|ai|ml|systems?|platform|application|firmware|embedded|security|solutions?|infrastructure)\s+(?:engineer|developer|architect)\b",
    r"\b(?:junior|jr|associate|entry[- ]level|graduate|trainee|intern)\s+(?:developer|engineer|programmer)\b",
    r"\bdevops\b", r"\bsdet\b", r"\bsoftware architect\b", r"\bsolutions architect\b",
    r"\bfrontend\b", r"\bbackend\b", r"\bfull[- ]?stack\b", r"\bandroid\b", r"\bios\b",
    r"\bdata engineer\b", r"\bweb dev\b", r"\bweb application\b",
    r"\bdatabase administrator\b", r"\bdba\b", r"\bcyber\s?security\b", r"\binfosec\b",
    r"\bweb designer\b", r"\bui/ux\b", r"\bqa\b", r"\bquality assurance\b",
    r"\bsysadmin\b", r"\bsystem(?:s)? administrator\b", r"\bnetwork engineer\b",
    r"\bcloud\b", r"\bproduct designer\b", r"\bquality engineering\b",
    r"\bsalesforce (?:developer|administrator|admin)\b",
    r"\bmarketing cloud developer\b"
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
    title_lower = t_str.lower()
    text = f"{t_str} {d_str}".lower()
    if not is_virtual_assistant(t_str, d_str):
        return False
    # Strict rejection of senior, lead, executive-to-c-level, or high-tenure VA roles
    if any(re.search(pat, title_lower) for pat in SENIOR_PATTERNS):
        return False
    if re.search(r"\b(?:senior|lead|director|head of|manager|5\+|7\+|10\+)\b", text):
        return False
    if re.search(r"\b(?:executive assistant to (?:the )?(?:ceo|president|vp|vice president|director|managing director|board))\b", title_lower):
        return False
    return any(re.search(pat, text) for pat in VA_TRAINING_PATTERNS)

def is_non_tech(title: str, description: str = "") -> bool:
    t_str = str(title or "")
    d_str = str(description or "")
    title_lower = t_str.lower()
    text = f"{t_str} {d_str}".lower()

    # Explicit software / IT engineering roles that should NEVER be flagged as non-tech
    explicit_software_role = re.search(
        r"\b(?:software|web|mobile|android|ios|frontend|front[- ]?end|backend|back[- ]?end|full[- ]?stack|firmware|embedded|devops|sre|site reliability|cloud engineer|sdet|qa automation|data engineer|machine learning|ai engineer|salesforce developer|marketing cloud developer)\b",
        title_lower
    )
    if explicit_software_role:
        # If it's specifically sales/presales engineering, still catch it below
        if not re.search(r"\b(?:sales|presales|pre-sales)\s+engineer\b", title_lower):
            return False

    # Physical, traditional engineering & construction roles (catches multi-word titles like Mechanical Design Engineer)
    physical_role = re.search(
        r"\b(?:civil|structural|mechanical|construction|chemical|mining|petroleum|sanitary|geotechnical|marine|architectural|draftsman|cad|hvac|refrigeration|plumbing|piping|electrical|electronics|instrumentation|site|field|facilities|building)\b.*?\b(?:engineer|engineering|technician|estimator|draftsman|inspector|supervisor)\b",
        title_lower
    )
    if physical_role and not ("site reliability" in title_lower or re.search(r"\bsre\b", title_lower)):
        return True

    # Non-software sales, presales, and marketing roles
    sales_role = re.search(
        r"\b(?:sales|presales|pre-sales|telemarketer|telemarketing|cold call(?:er|ing)?|account executive|account developer|business developer|business development|real estate|leasing|property management|broker|bidding)\b",
        title_lower
    )
    if sales_role and not re.search(r"\b(?:software|web|full[- ]?stack|salesforce developer)\b", title_lower):
        return True

    has_tech_override = any(re.search(pat, title_lower) for pat in TECH_WHITELIST_OVERRIDE)
    if has_tech_override:
        return False
    if is_virtual_assistant(t_str, d_str):
        return False
    return any(re.search(pat, text) for pat in NON_TECH_BLACKLIST)

def description_accepts_entry(description: str) -> bool:
    text = re.sub(r"[*_\u200b\ufeff]", "", description.lower())
    text = re.sub(r"[^.\n]*\b(?:fresh|new|recent)\s*[- ]?grad(?:uate)?s?\b[^.\n]*\b(?:not welcome|not accepted|not eligible|do not apply|should not apply)\b[^.\n]*", "", text)
    text = re.sub(r"[^.\n]*\bfreshers?\b[^.\n]*\b(?:not welcome|not accepted|not eligible|do not apply|should not apply)\b[^.\n]*", "", text)
    graduate_invitation = (
        r"\b(?:fresh|new|recent)\s*[- ]?grad(?:uate)?s?\b[^.\n]{0,240}\b(?:welcome|encouraged|accepted|considered|apply)\b",
        r"\b(?:open|welcomes?|accepts?)\b[^.\n]{0,160}\b(?:fresh|new|recent)\s*[- ]?grad(?:uate)?s?\b",
        r"\bfresh\s*[- ]?grad(?:uate)?s?\s*/\s*\d+",
        r"\b(?:college\s+graduates?|graduates?|graduating students?)\s+(?:are\s+|also\s+|very\s+|more than\s+)*welcome\s+to\s+apply\b",
        r"\b(?:accepting|open to|open for)\s+(?:applications from\s+)?(?:graduates?|graduating students?|career starters?|first[- ]time job\s*seekers?)\b",
        r"\bfreshers?\b[^.\n]{0,240}\b(?:welcome|encouraged|accepted|considered|apply|eligible)\b",
        r"\b(?:open\s+(?:for|to)|welcomes?|accepts?)\b[^.\n]{0,160}\bfreshers?\b",
        r"\bfreshers?\s+(?:are\s+|can\s+|also\s+|very\s+|more than\s+)*(?:welcome|encouraged|apply|eligible)\b",
        r"\b(?:freshers?|beginners?)\s+(?:welcome|encouraged|can\s+apply)\b",
    )
    if any(re.search(pattern, text) for pattern in graduate_invitation):
        return True
    # Do not mistake education, employee training, or contract length for eligibility.
    years = r"(?:years?|yrs?)"
    positive = (
        r"\bjob types?\s*:[^\n]*\bfresh\s+graduates?\b",
        r"\b(?:early[- ]career|entry[- ]level)\s+(?:role|position|opportunity|job|support specialist)\b",
        r"\b(?:software\s+engineer|developer|programmer)\s+j[uú]nior\b",
        r"\b(?:hire|hiring)\b[^.\n]{0,100}\bnot\s+(?:on\s+)?years\s+of\s+experience\b",
        r"\b(?:1|one)\s*\+?\s*(?:years?|yrs?)\s*\(\s*(?:required|preferred)\s*\)",
        r"\b(?:no|zero)\s+(?:prior\s+|previous\s+)?(?:work\s+|professional\s+)?experience\s+(?:is\s+)?(?:required|needed|necessary)\b",
        r"\b(?:this\s+(?:is\s+an?\s+|is\s+|role\s+is\s+|position\s+is\s+)|an?\s+)entry[- ]level\s+(?:role|position|opportunity|job)\b",
        r"\b(?:suitable|ideal|designed)\s+for\s+(?:entry[- ]level\s+(?:applicants|candidates)|career starters|those\s+(?:starting|beginning)\s+their\s+careers)\b",
        r"\b(?:start|begin|launch)\s+your\s+(?:first\s+)?career\s+in\s+(?:software|web|mobile|development|programming)\b",
        rf"\b[01]\s*[-–to]\s*[12]\s*{years}['’]?\s+(?:of\s+)?(?:\w+\s+){{0,4}}experience\b",
        rf"\b0\s*[-–]\s*0?[12]\s*{years}\b",
        r"\b(?:6|six)\s+months?\s+(?:of\s+)?(?:\w+\s+){0,4}experience\b",
        rf"\b(?:at least\s+|minimum(?: of)?\s+)?(?:1|one(?:\s*\(1\))?)\s*\+?\s*{years}(?:\s*\+)?['’]?\s+(?:of\s+)?(?:\w+\s+){{0,4}}experience\b",
        r"\b(?:less than|under)\s+(?:1|one)\s+year\s+(?:of\s+)?experience\b",
        r"\b(?:internship(?: experience)?|personal projects?|academic projects?|capstone projects?|project experience)\b[^.\n]{0,65}\b(?:accepted|considered|equivalent|counts? toward)\b",
        r"\b(?:accepts?|consider(?:s|ing)?)\s+(?:relevant\s+)?(?:internship|academic|personal|capstone)\s+(?:experience|projects?)\b",
        r"\bor\s+equivalent\s+project\s+background\b",
        r"\bearly[- ]career\s+(?:developers?|professionals?|candidates?)\b",
        r"\b(?:comprehensive\s+training\s+provided|full\s+training\s+(?:is\s+|will\s+be\s+)?provided|training\s+(?:will\s+be\s+|is\s+)provided\b(?!\s+to\b))",
        r"\bbeginners?\s+(?:welcome|encouraged|can\s+apply)\b",
    )
    return any(re.search(pattern, text) for pattern in positive)


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

    if is_senior and not re.search(r"\bjunior\s*(?:to|or|/|-)\s*senior\b", title_lower):
        return "Senior / Lead"
    if description_accepts_entry(desc_lower):
        return "Junior / Entry"
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
    matches_tech = any(re.search(pat, title_lower) for pat in WEB_PATTERNS + DATA_AI_PATTERNS + TECH_WHITELIST_OVERRIDE)
    return "Mid-Level" if matches_tech else "Unspecified"

def is_relevant_opportunity(title: str, description: str = "", allow_va_training: bool = True, matrix: list = None, location: str = "", platform: str = "") -> bool:
    t_str = str(title or "")
    d_str = str(description or "")
    if location and not is_work_authorized_location(location, t_str, platform, d_str):
        return False
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

    # If matrix list is passed, enforce match against user matrix
    if matrix:
        text_lower = f"{t_str} {d_str}".lower()
        if not any(k.lower().strip() in text_lower for k in matrix if k.strip()):
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
    matches_tech = any(re.search(pat, text) for pat in TECH_WHITELIST_OVERRIDE)

    if matches_web and matches_data:
        return "Both"
    if matches_data:
        return "Data/AI/ML"
    if matches_web or matches_tech:
        return "Web/Software Dev"
    return "Web/Software Dev"
