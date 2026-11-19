"""Role predicates shared by paginated feeds, exports, and result counts."""

TITLE = "(' ' || lower(replace(replace(replace(replace(title, '-', ' '), '/', ' '), '.', ' '), ',', ' ')) || ' ')"
VIDEO_ROLES = {"Video Editor", "Short-Form / CapCut Editor", "Long-Form / YouTube Editor"}

PATTERNS = {
    "Software Engineer / Developer": [
        "* software engineer *", "* software developer *", "* junior developer *", "* graduate developer *",
        "* trainee developer *", "* entry level developer *", "* associate developer *",
        "* software development *", "* software engineering *", "* programmer *", "* sde *",
        "* graduate engineer *", "* associate engineer *"
    ],
    "Application / Systems Dev": [
        "* application developer *", "* application engineer *", "* systems developer *", "* system developer *",
        "* systems programmer *", "* system programmer *", "* systems software *", "* desktop application *",
        "* desktop developer *", "* product engineer *", "* platform engineer *", "* embedded software *",
        "* embedded engineer *", "* firmware engineer *", "* iot developer *", "* iot engineer *"
    ],
    "Mobile": [
        "* mobile developer *", "* mobile engineer *", "* mobile app*", "* mobile software *",
        "* mobile development *", "* android *", "* ios *", "* flutter *", "* react native *",
        "* swift developer *", "* swift engineer *", "* kotlin developer *", "* kotlin engineer *",
        "* jetpack compose *", "* compose multiplatform *", "* kotlin multiplatform *", "* kmp *"
    ],
    "Frontend": [
        "* frontend *", "* front end *", "* react *", "* vue *", "* angular *", "* svelte *",
        "* ui developer *", "* web designer *", "* next js *", "* nextjs *", "* nuxt *", "* web developer *"
    ],
    "Backend": [
        "* backend *", "* back end *", "* node *", "* nodejs *", "* django *", "* fastapi *",
        "* golang *", "* go developer *", "* java *", "* net *", "* c# *", "* php *",
        "* laravel *", "* ruby *", "* api developer *", "* python developer *",
        "* express *", "* nestjs *", "* spring boot *", "* asp net *", "* dotnet *"
    ],
    "Full Stack": ["* full stack *", "* fullstack *", "* mern *"],
    "AI Development": [
        "* ai developer *", "* ai development *", "* ai engineer *", "* ai software *", "* ai application *",
        "* artificial intelligence developer *", "* artificial intelligence engineer *",
        "* llm developer *", "* llm engineer *", "* generative ai engineer *", "* genai developer *",
        "* genai engineer *", "* ai agent developer *", "* ai agent engineer *",
        "* ai automation *", "* ai assisted *", "* vibe coder *", "* ai agent *", "* agentic ai *",
        "* ai implementation *", "* ai integration *", "* ai workflow *", "* prompt engineer *",
        "* rag developer *", "* rag engineer *", "* llm application *", "* llm integration *",
        "* ai evaluation *", "* llm evaluator *", "* ai code evaluator *", "* chatbot developer *",
        "* mcp developer *"
    ],
    "API & Database Dev": [
        "* api developer *", "* api engineer *", "* integration developer *", "* integration engineer *",
        "* sql developer *", "* database developer *", "* pl sql *", "* middleware developer *"
    ],
    "CMS / ERP / Low-Code Dev": [
        "* wordpress *", "* shopify *", "* webflow *", "* drupal *", "* magento *",
        "* erp developer *", "* sap developer *", "* salesforce developer *", "* servicenow developer *",
        "* low code *", "* outsystems *", "* mendix *", "* power platform *", "* power apps *",
        "* game developer *", "* game programmer *", "* gameplay programmer *", "* unity developer *",
        "* unreal engine *"
    ],
    "DevOps / Cloud": [
        "* devops *", "* cloud engineer *", "* cloud architect *", "* aws engineer *", "* azure engineer *",
        "* sre *", "* site reliability *", "* platform engineer *", "* infrastructure engineer *",
        "* build engineer *", "* release engineer *", "* cloud administrator *", "* cloud infrastructure *"
    ],
    "QA / Testing": [
        "* qa *", "* quality assurance *", "* software test*", "* tester *", "* test automation *",
        "* automation test*", "* sdet *", "* software development engineer in test *",
        "* test analyst *", "* test engineer *", "* quality engineer *"
    ],
    "QA Engineer / Tester": [
        "* qa engineer *", "* qa tester *", "* software tester *", "* qa analyst *", "* software qa *",
        "* test analyst *", "* test engineer *", "* quality assurance *", "* quality engineer *", "* software test*"
    ],
    "Manual QA": [
        "* manual qa *", "* manual test*", "* functional test*", "* functional qa *",
        "* uat *", "* exploratory test*", "* qa tester *", "* software tester *", "* test analyst *"
    ],
    "QA Automation / SDET": [
        "* qa automation *", "* test automation *", "* automation test*", "* automation qa *",
        "* sdet *", "* software development engineer in test *", "* playwright *", "* cypress *",
        "* selenium *", "* appium *"
    ],
    "Mobile & API QA": [
        "* mobile qa *", "* android qa *", "* ios qa *", "* mobile test*",
        "* api test*", "* api qa *", "* performance test*", "* performance qa *",
        "* security test*", "* game test*", "* game qa *"
    ],
    "IT Support": [
        "* it support *", "* helpdesk *", "* help desk *", "* service desk *", "* desktop support *",
        "* systems administrator *", "* system administrator *", "* systems engineer *", "* it engineer *",
        "* network engineer *", "* network administrator *", "* database administrator *", "* dba *",
        "* it specialist *", "* it operations *"
    ],
    "Application & Product Support": [
        "* application support *", "* software support *", "* product support *",
        "* implementation engineer *", "* production support *"
    ],
    "Network & NOC": [
        "* network engineer *", "* network administrator *", "* network admin *", "* network support *",
        "* network operations *", "* noc engineer *", "* noc analyst *", "* noc technician *",
        "* network specialist *"
    ],
    "Systems & DB Admin": [
        "* systems administrator *", "* system administrator *", "* sysadmin *", "* systems engineer *",
        "* database administrator *", "* dba *", "* server administrator *",
        "* linux administrator *", "* windows administrator *"
    ],
    "CRM & Platform Admin": [
        "* salesforce administrator *", "* salesforce admin *", "* servicenow administrator *",
        "* servicenow admin *", "* crm administrator *", "* crm admin *"
    ],
    "Technical Support": ["* technical support *", "* tech support *", "* technical writer *"],
    "Cybersecurity": [
        "* cybersecurity *", "* cyber security *", "* security engineer *", "* security analyst *",
        "* soc analyst *", "* penetration test*", "* information security *",
        "* application security *", "* product security *", "* security software *",
        "* devsecops *", "* iam engineer *", "* it auditor *"
    ],
    "Cybersecurity / SOC Analyst": [
        "* cybersecurity *", "* cyber security *", "* security analyst *", "* soc analyst *",
        "* information security *", "* infosec *", "* threat analyst *", "* incident response *"
    ],
    "Security & DevSecOps Engineer": [
        "* security engineer *", "* application security *", "* product security *", "* security software *",
        "* devsecops *", "* penetration test*", "* pentest*", "* cloud security *", "* network security *"
    ],
    "IAM & IT Audit": [
        "* iam engineer *", "* iam analyst *", "* identity and access *",
        "* it auditor *", "* it audit *", "* security auditor *", "* grc *"
    ],
    "Data Analyst": [
        "* data analyst *", "* data analytics *", "* analytics analyst *", "* reporting analyst *",
        "* business intelligence *", "* bi analyst *", "* bi developer *", "* power bi *", "* tableau *"
    ],
    "Analyst": ["* analyst *", "* gis analyst *"],
    "Data Science": ["* data scientist *", "* data science *", "* decision scientist *", "* statistician *"],
    "Data Engineering": [
        "* data engineer *", "* data engineering *", "* analytics engineer *", "* etl *",
        "* data warehouse *", "* data platform *", "* datastage *", "* data developer *",
        "* data integration *", "* big data *"
    ],
    "AI / ML": [
        "* ai *", "* artificial intelligence *", "* machine learning *", "* ml engineer *", "* mlops *",
        "* llm *", "* generative ai *", "* genai *", "* nlp *", "* prompt engineer *", "* deep learning *"
    ],
    "Business / Systems Analyst": [
        "* business analyst *", "* systems analyst *", "* system analyst *", "* product analyst *",
        "* operations analyst *", "* process analyst *", "* technical business analyst *",
        "* it application analyst *"
    ],
    "Virtual Assistant": [
        "* virtual assistant *", "* administrative assistant *", "* executive assistant *",
        "* remote assistant *", "* virtual executive *", "* cyberbacker *"
    ],
    "General VA & Trainee": [
        "* virtual assistant *", "* va trainee *", "* remote assistant *", "* virtual executive *",
        "* cyberbacker *", "* athena *", "* virtudesk *", "* pineapple staffing *"
    ],
    "Administrative Support": [
        "* administrative assistant *", "* admin assistant *", "* administrative support *",
        "* hr admin assistant *", "* email management *", "* calendar management *", "* research assistant *"
    ],
    "Executive Assistance": ["* executive assistant *", "* executive virtual assistant *", "* executive assistance *"],
    "Customer Support": ["* customer support *", "* customer service *", "* chat support *", "* email support *"],
    "Data Entry": ["* data entry *", "* data encoder *", "* encoding clerk *"],
}

ALIASES = {
    "Data & AI": "Data/AI/ML", "Data & Analytics": "Data/AI/ML",
    "Tech & IT": "Web/Software Dev", "Technology & IT": "Web/Software Dev",
    "IT, Cloud & Infrastructure": "IT / Cloud / Infrastructure", "VA & Admin": "Virtual Assistant",
    "QA & Testing": "QA / Testing",
    "DevOps": "DevOps / Cloud", "Cloud": "DevOps / Cloud",
    "QA": "QA / Testing", "Testing": "QA / Testing",
    "VA": "Virtual Assistant", "VA (with training)": "Virtual Assistant",
}

SOFTWARE_DEV_EXCLUSIONS = (
    "QA / Testing", "IT / Cloud / Infrastructure", "Technical Support", "Cybersecurity",
    "Data Science", "Data Engineering", "Virtual Assistant", "Data Analyst", "Business / Systems Analyst",
)
PHYSICAL_DEV_NEGATIVE_GLOBS = (
    "* civil *", "* mechanical *", "* manufacturing *", "* construction *",
    "* cnc *", "* machinist *", "* account developer *", "* business developer *", "* property developer *"
)
QA_NEGATIVE_GLOBS = ("* mechanical *", "* electrical *", "* construction *", "* manufacturing *", "* supplier *", "* chemical *")
IT_CLOUD_MEMBERS = (
    "IT Support", "Application & Product Support", "Network & NOC",
    "Systems & DB Admin", "DevOps / Cloud", "CRM & Platform Admin",
)
VA_MEMBERS = (
    "General VA & Trainee", "Administrative Support", "Executive Assistance",
    "Customer Support", "Technical Support", "Data Entry",
)
QA_ROLES = ("QA / Testing", "QA Engineer / Tester", "Manual QA", "QA Automation / SDET", "Mobile & API QA")
SOFTWARE_DEV_DIRECT_SUBROLES = (
    "Software Engineer / Developer", "Application / Systems Dev", "API & Database Dev", "CMS / ERP / Low-Code Dev"
)


def _raw_pattern_predicate(role):
    patterns = PATTERNS.get(role, [])
    sql = "(role_category = ?" + "".join(f" OR {TITLE} GLOB ?" for _ in patterns) + ")"
    return sql, [role, *patterns]


def role_predicate(role):
    sql, params = _role_predicate(role)
    if role not in VIDEO_ROLES:
        sql = f"({sql} AND role_category != 'Video Editor')"
    return sql, params


def _role_predicate(role):
    role = ALIASES.get(role, role)
    if role == "Video Editor":
        return "(role_category = ?)", [role]
    if role == "Short-Form / CapCut Editor":
        text_expr = "lower(title || ' ' || coalesce(description, ''))"
        globs = ["*capcut*", "*short*", "*reel*", "*tiktok*"]
        sql = "(role_category = 'Video Editor' AND (" + " OR ".join(f"{text_expr} GLOB ?" for _ in globs) + " OR lower(title) GLOB ?))"
        return sql, [*globs, "*video editor*"]
    if role == "Long-Form / YouTube Editor":
        text_expr = "lower(title || ' ' || coalesce(description, ''))"
        globs = ["*youtube*", "*long*form*", "*vlog*", "*podcast*"]
        sql = "(role_category = 'Video Editor' AND (" + " OR ".join(f"{text_expr} GLOB ?" for _ in globs) + " OR lower(title) GLOB ?))"
        return sql, [*globs, "*video editor*"]
    if role == "Virtual Assistant":
        parts = [_raw_pattern_predicate(member) for member in VA_MEMBERS]
        sql = "(role_category = ?" + "".join(f" OR {TITLE} GLOB ?" for _ in PATTERNS[role])
        sql += " OR " + " OR ".join(part for part, _ in parts) + ")"
        return sql, [role, *PATTERNS[role], *[p for _, params in parts for p in params]]
    if role == "Web/Software Dev":
        sql, params = _role_predicate("Software Development")
        for pattern in PHYSICAL_DEV_NEGATIVE_GLOBS:
            sql += f" AND NOT {TITLE} GLOB ?"
            params.append(pattern)
        return f"({sql})", params
    if role == "IT / Cloud / Infrastructure":
        parts = [_raw_pattern_predicate(member) for member in IT_CLOUD_MEMBERS]
        support_sql, support_params = _raw_pattern_predicate("Technical Support")
        return "((" + " OR ".join(sql for sql, _ in parts) + ") AND NOT " + support_sql + ")", [p for _, values in parts for p in values] + support_params
    if role == "Data/AI/ML":
        members = ["Data Analyst", "Data Science", "Data Engineering", "AI / ML", "Business / Systems Analyst", "Analyst"]
        parts = [role_predicate(member) for member in members]
        ai_sql, ai_params = _raw_pattern_predicate("AI Development")
        return "((" + " OR ".join(sql for sql, _ in parts) + ") AND NOT " + ai_sql + ")", [p for _, params in parts for p in params] + ai_params
    if role == "Software Development":
        parts = [
            *(_raw_pattern_predicate(member) for member in SOFTWARE_DEV_DIRECT_SUBROLES),
            *(_role_predicate(member) for member in ("Frontend", "Backend", "Full Stack", "Mobile", "AI Development")),
        ]
        extra_globs = [
            "* software engineer *", "* software developer *", "* web developer *",
            "* programmer *", "* developer *", "* software development *",
            "* software engineering *", "* graduate engineer *", "* associate engineer *"
        ]
        sql = "(" + " OR ".join(s for s, _ in parts) + "".join(f" OR {TITLE} GLOB ?" for _ in extra_globs) + ")"
        params = [p for _, values in parts for p in values] + extra_globs
        for excluded in SOFTWARE_DEV_EXCLUSIONS:
            negative, values = _role_predicate(excluded)
            sql += f" AND NOT {negative}"
            params.extend(values)
        return f"({sql})", params
    sql, params = _raw_pattern_predicate(role)
    # Language keywords alone do not make mobile/testing/data jobs backend roles.
    exclusions = []
    if role in IT_CLOUD_MEMBERS:
        exclusions = ["Technical Support"]
    elif role in SOFTWARE_DEV_DIRECT_SUBROLES:
        exclusions = list(SOFTWARE_DEV_EXCLUSIONS)
    elif role == "AI / ML":
        exclusions = ["AI Development"]
    elif role == "Frontend":
        exclusions = ["Mobile", "QA / Testing"]
    elif role == "Backend":
        exclusions = ["Mobile", "QA / Testing", "Data Science", "Data Engineering", "AI / ML"]
    elif role in ("Data Analyst", "Analyst"):
        exclusions = ["QA / Testing", "IT Support", "Technical Support", "Cybersecurity", "Business / Systems Analyst", "AI Development"]
    for excluded in exclusions:
        negative, values = _role_predicate(excluded)
        sql += f" AND NOT {negative}"
        params.extend(values)
    if role in SOFTWARE_DEV_DIRECT_SUBROLES:
        for pattern in PHYSICAL_DEV_NEGATIVE_GLOBS:
            sql += f" AND NOT {TITLE} GLOB ?"
            params.append(pattern)
    if role in QA_ROLES:
        for pattern in QA_NEGATIVE_GLOBS:
            sql += f" AND NOT {TITLE} GLOB ?"
            params.append(pattern)
    if role == "Manual QA":
        for pattern in (
            "* automation *", "* sdet *", "* android qa *", "* ios qa *",
            "* mobile qa *", "* api qa *", "* api test*", "* performance *", "* security *"
        ):
            sql += f" AND NOT {TITLE} GLOB ?"
            params.append(pattern)
    if role == "AI / ML":
        for pattern in ["* marketer *", "* copywriter *", "* recruiter *", "* bookkeeper *"]:
            sql += f" AND NOT {TITLE} GLOB ?"
            params.append(pattern)
    return f"({sql})", params
