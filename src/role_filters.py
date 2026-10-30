"""Role predicates shared by paginated feeds, exports, and result counts."""

TITLE = "(' ' || lower(replace(replace(replace(replace(title, '-', ' '), '/', ' '), '.', ' '), ',', ' ')) || ' ')"

PATTERNS = {
    "Mobile": ["* mobile developer *", "* mobile engineer *", "* mobile app*", "* mobile software *", "* mobile development *", "* android *", "* ios *", "* flutter *", "* react native *", "* swift developer *", "* swift engineer *", "* kotlin developer *", "* kotlin engineer *"],
    "Frontend": ["* frontend *", "* front end *", "* react *", "* vue *", "* angular *", "* svelte *", "* ui developer *", "* web designer *"],
    "Backend": ["* backend *", "* back end *", "* node *", "* nodejs *", "* django *", "* fastapi *", "* golang *", "* go developer *", "* java *", "* net *", "* c# *", "* php *", "* laravel *", "* ruby *", "* api developer *", "* python developer *"],
    "Full Stack": ["* full stack *", "* fullstack *"],
    "DevOps / Cloud": ["* devops *", "* cloud engineer *", "* cloud architect *", "* aws engineer *", "* azure engineer *", "* sre *", "* site reliability *", "* platform engineer *", "* infrastructure engineer *"],
    "QA / Testing": ["* qa *", "* quality assurance *", "* software test*", "* tester *", "* test automation *", "* automation test*", "* sdet *", "* software development engineer in test *"],
    "IT Support": ["* it support *", "* helpdesk *", "* help desk *", "* service desk *", "* desktop support *", "* systems administrator *", "* system administrator *", "* systems engineer *", "* it engineer *", "* network engineer *", "* network administrator *", "* database administrator *", "* dba *", "* it specialist *"],
    "Technical Support": ["* technical support *", "* tech support *"],
    "AI Development": ["* ai developer *", "* ai development *", "* ai engineer *", "* ai software *", "* ai application *", "* artificial intelligence developer *", "* artificial intelligence engineer *", "* llm developer *", "* llm engineer *", "* generative ai engineer *", "* genai developer *", "* genai engineer *", "* ai agent developer *", "* ai agent engineer *"],
    "Cybersecurity": ["* cybersecurity *", "* cyber security *", "* security engineer *", "* security analyst *", "* soc analyst *", "* penetration test*", "* information security *"],
    "Data Analyst": ["* data analyst *", "* data analytics *", "* analytics analyst *", "* reporting analyst *", "* business intelligence *", "* bi analyst *", "* bi developer *", "* power bi *", "* tableau *"],
    "Analyst": ["* analyst *"],
    "Data Science": ["* data scientist *", "* data science *", "* decision scientist *", "* statistician *"],
    "Data Engineering": ["* data engineer *", "* data engineering *", "* analytics engineer *", "* etl *", "* data warehouse *", "* data platform *", "* datastage *", "* data developer *", "* data integration *"],
    "AI / ML": ["* ai *", "* artificial intelligence *", "* machine learning *", "* ml engineer *", "* mlops *", "* llm *", "* generative ai *", "* genai *", "* nlp *", "* prompt engineer *", "* deep learning *"],
    "Business / Systems Analyst": ["* business analyst *", "* systems analyst *", "* system analyst *", "* product analyst *", "* operations analyst *", "* process analyst *"],
    "Virtual Assistant": ["* virtual assistant *", "* administrative assistant *", "* executive assistant *", "* remote assistant *", "* virtual executive *", "* cyberbacker *"],
    "Administrative Support": ["* administrative assistant *", "* admin assistant *", "* administrative support *", "* hr admin assistant *"],
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


def role_predicate(role):
    sql, params = _role_predicate(role)
    if role != "Video Editor":
        sql = f"({sql} AND role_category != 'Video Editor')"
    return sql, params


def _role_predicate(role):
    role = ALIASES.get(role, role)
    if role == "Video Editor":
        return "(role_category = ?)", [role]
    if role == "Virtual Assistant":
        members = ["Administrative Support", "Executive Assistance", "Customer Support", "Technical Support", "Data Entry"]
        parts = [role_predicate(member) for member in members]
        sql = "(role_category = ?" + "".join(f" OR {TITLE} GLOB ?" for _ in PATTERNS[role])
        sql += " OR " + " OR ".join(part for part, _ in parts) + ")"
        return sql, [role, *PATTERNS[role], *[p for _, params in parts for p in params]]
    if role == "Web/Software Dev":
        members = ["Software Development"]
        parts = [role_predicate(member) for member in members]
        sql = "(" + " OR ".join(sql for sql, _ in parts) + ")"
        params = [p for _, values in parts for p in values]
        for pattern in ["* civil *", "* mechanical *", "* manufacturing *", "* construction *", "* cnc *", "* machinist *", "* account developer *", "* business developer *", "* property developer *"]:
            sql += f" AND NOT {TITLE} GLOB ?"
            params.append(pattern)
        return f"({sql})", params
    if role == "IT / Cloud / Infrastructure":
        parts = [role_predicate(member) for member in ("IT Support", "DevOps / Cloud")]
        support_sql, support_params = role_predicate("Technical Support")
        return "((" + " OR ".join(sql for sql, _ in parts) + ") AND NOT " + support_sql + ")", [p for _, values in parts for p in values] + support_params
    if role == "Data/AI/ML":
        members = ["Data Analyst", "Data Science", "Data Engineering", "AI / ML", "Business / Systems Analyst", "Analyst"]
        parts = [role_predicate(member) for member in members]
        ai_sql, ai_params = role_predicate("AI Development")
        return "((" + " OR ".join(sql for sql, _ in parts) + ") AND NOT " + ai_sql + ")", [p for _, params in parts for p in params] + ai_params
    if role == "Software Development":
        members = ["Frontend", "Backend", "Full Stack", "Mobile", "AI Development"]
        parts = [role_predicate(member) for member in members]
        sql = "(" + " OR ".join(s for s, _ in parts) + f" OR {TITLE} GLOB ? OR {TITLE} GLOB ? OR {TITLE} GLOB ? OR {TITLE} GLOB ? OR {TITLE} GLOB ?)"
        params = [p for _, values in parts for p in values] + ["* software engineer *", "* software developer *", "* web developer *", "* programmer *", "* developer *"]
        for excluded in ("QA / Testing", "IT Support", "Technical Support", "DevOps / Cloud", "Cybersecurity", "Data Science", "Data Engineering", "Virtual Assistant", "Data Analyst", "Business / Systems Analyst"):
            negative, values = role_predicate(excluded)
            sql += f" AND NOT {negative}"
            params.extend(values)
        return f"({sql})", params
    patterns = PATTERNS.get(role, [])
    sql = "(role_category = ?" + "".join(f" OR {TITLE} GLOB ?" for _ in patterns) + ")"
    params = [role, *patterns]
    # Language keywords alone do not make mobile/testing/data jobs backend roles.
    exclusions = []
    if role in ("IT Support", "DevOps / Cloud"):
        exclusions = ["Technical Support"]
    if role == "AI / ML":
        exclusions = ["AI Development"]
    if role == "Frontend":
        exclusions = ["Mobile", "QA / Testing"]
    elif role == "Backend":
        exclusions = ["Mobile", "QA / Testing", "Data Science", "Data Engineering", "AI / ML"]
    elif role in ("Data Analyst", "Analyst"):
        exclusions = ["QA / Testing", "IT Support", "Technical Support", "Cybersecurity", "Business / Systems Analyst", "AI Development"]
    for excluded in exclusions:
        negative, values = role_predicate(excluded)
        sql += f" AND NOT {negative}"
        params.extend(values)
    if role == "QA / Testing":
        for pattern in ["* mechanical *", "* electrical *", "* construction *", "* manufacturing *", "* supplier *", "* chemical *"]:
            sql += f" AND NOT {TITLE} GLOB ?"
            params.append(pattern)
    if role == "AI / ML":
        for pattern in ["* marketer *", "* copywriter *", "* recruiter *", "* bookkeeper *"]:
            sql += f" AND NOT {TITLE} GLOB ?"
            params.append(pattern)
    return f"({sql})", params
