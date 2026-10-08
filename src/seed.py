from typing import List
from src.models import Job
from src.classifier import classify_experience_level, classify_role
from src.database import insert_jobs

SAMPLE_DATA = [
    # Tier 1 — Apply heavily
    {
        "title": "Junior Frontend Developer (React / TypeScript)",
        "company": "Canva Philippines",
        "location": "Remote - Philippines",
        "platform": "LinkedIn",
        "tier": 1,
        "job_url": "https://www.linkedin.com/jobs/view/sample-1",
        "salary": "₱45,000 - ₱65,000 / month",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Senior Full Stack Architect (Node / Python)",
        "company": "Globe Telecom",
        "location": "Taguig / Hybrid",
        "platform": "LinkedIn",
        "tier": 1,
        "job_url": "https://www.linkedin.com/jobs/view/sample-2",
        "salary": "₱120,000 - ₱180,000 / month",
        "date_posted": "2026-10-07"
    },
    {
        "title": "Entry Level Data Analyst - SQL & Python",
        "company": "Accenture PH",
        "location": "Mandaluyong / Hybrid",
        "platform": "JobStreet",
        "tier": 1,
        "job_url": "https://www.jobstreet.com.ph/job/sample-3",
        "salary": "₱35,000 - ₱50,000 / month",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Mid-Level Backend Developer (Go / PostgreSQL)",
        "company": "Maya Philippines",
        "location": "Remote - PH",
        "platform": "JobStreet",
        "tier": 1,
        "job_url": "https://www.jobstreet.com.ph/job/sample-4",
        "salary": "₱80,000 - ₱110,000 / month",
        "date_posted": "2026-10-06"
    },
    {
        "title": "Junior Python Developer",
        "company": "Kumu Media",
        "location": "Remote PH",
        "platform": "Indeed",
        "tier": 1,
        "job_url": "https://ph.indeed.com/viewjob?jk=sample-5",
        "salary": "₱40,000 - ₱55,000 / month",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Senior Machine Learning Engineer",
        "company": "Coins.ph",
        "location": "BGC / Hybrid",
        "platform": "Indeed",
        "tier": 1,
        "job_url": "https://ph.indeed.com/viewjob?jk=sample-6",
        "salary": "₱140,000 - ₱200,000 / month",
        "date_posted": "2026-10-05"
    },
    {
        "title": "Associate Software Engineer (Graduate Track)",
        "company": "Monstar Lab PH",
        "location": "Cebu / Remote",
        "platform": "Kalibrr",
        "tier": 1,
        "job_url": "https://www.kalibrr.com/c/sample/jobs/7",
        "salary": "₱38,000 - ₱48,000 / month",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Mid-Level React & Next.js Developer",
        "company": "Sprout Solutions",
        "location": "Remote - PH",
        "platform": "Kalibrr",
        "tier": 1,
        "job_url": "https://www.kalibrr.com/c/sample/jobs/8",
        "salary": "₱70,000 - ₱95,000 / month",
        "date_posted": "2026-10-07"
    },

    # Tier 2 — Very worth checking
    {
        "title": "Junior AI Engineer - LLM & Agent Applications",
        "company": "Synthesia Partner",
        "location": "Remote APAC",
        "platform": "Wellfound",
        "tier": 2,
        "job_url": "https://wellfound.com/jobs/sample-9",
        "salary": "$2,500 - $3,500 / month",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Senior Backend Engineer (FastAPI / Redis)",
        "company": "Fintech Startup Lab",
        "location": "Remote Worldwide",
        "platform": "Wellfound",
        "tier": 2,
        "job_url": "https://wellfound.com/jobs/sample-10",
        "salary": "$5,000 - $7,000 / month",
        "date_posted": "2026-10-07"
    },
    {
        "title": "Junior Web Developer (Vue / PHP)",
        "company": "Innovate Manila Corp",
        "location": "Ortigas, Pasig",
        "platform": "Bossjob",
        "tier": 2,
        "job_url": "https://bossjob.ph/job/sample-11",
        "salary": "₱35,000 - ₱45,000 / month",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Data Analyst (Power BI & SQL)",
        "company": "Global Logistics PH",
        "location": "Makati City",
        "platform": "Bossjob",
        "tier": 2,
        "job_url": "https://bossjob.ph/job/sample-12",
        "salary": "₱50,000 - ₱70,000 / month",
        "date_posted": "2026-10-06"
    },
    {
        "title": "Junior Cloud / DevOps Engineer",
        "company": "CloudTech Systems",
        "location": "Clark / Remote",
        "platform": "Foundit",
        "tier": 2,
        "job_url": "https://foundit.com.ph/job/sample-13",
        "salary": "₱45,000 - ₱60,000 / month",
        "date_posted": "2026-10-07"
    },

    # Tier 3 — For international/remote opportunities
    {
        "title": "Junior Full Stack Engineer (Python & React)",
        "company": "Automattic",
        "location": "Remote Worldwide",
        "platform": "Remote OK",
        "tier": 3,
        "job_url": "https://remoteok.com/remote-jobs/sample-14",
        "salary": "$4,000 - $5,500 / month",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Senior AI & Machine Learning Researcher",
        "company": "Stability AI Lab",
        "location": "Remote Worldwide",
        "platform": "Remote OK",
        "tier": 3,
        "job_url": "https://remoteok.com/remote-jobs/sample-15",
        "salary": "$9,000 - $13,000 / month",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Junior Python / Django Developer",
        "company": "Zapier",
        "location": "Remote Worldwide",
        "platform": "We Work Remotely",
        "tier": 3,
        "job_url": "https://weworkremotely.com/jobs/sample-16",
        "salary": "$50,000 - $70,000 / year",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Senior React Frontend Architect",
        "company": "DuckDuckGo",
        "location": "Remote Worldwide",
        "platform": "We Work Remotely",
        "tier": 3,
        "job_url": "https://weworkremotely.com/jobs/sample-17",
        "salary": "$120,000 - $150,000 / year",
        "date_posted": "2026-10-07"
    },
    {
        "title": "Junior Full Stack Developer",
        "company": "Remote Health Tech",
        "location": "Remote APAC",
        "platform": "Arc",
        "tier": 3,
        "job_url": "https://arc.dev/job/sample-18",
        "salary": "$3,000 - $4,500 / month",
        "date_posted": "2026-10-08"
    },

    # Tier 4 — Backup / freelance
    {
        "title": "Full Stack Web Developer (Long-term Contract)",
        "company": "E-Commerce Growth Agency",
        "location": "Remote",
        "platform": "Upwork",
        "tier": 4,
        "job_url": "https://www.upwork.com/jobs/sample-19",
        "salary": "$25 - $45 / hr",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Junior Data Analyst & Dashboard Builder",
        "company": "SaaS Analytics Studio",
        "location": "Remote",
        "platform": "Upwork",
        "tier": 4,
        "job_url": "https://www.upwork.com/jobs/sample-20",
        "salary": "$18 - $30 / hr",
        "date_posted": "2026-10-08"
    },
    {
        "title": "Junior Software Engineer - Core Services",
        "company": "Shopee International",
        "location": "Bonifacio Global City",
        "platform": "Glassdoor",
        "tier": 4,
        "job_url": "https://www.glassdoor.com/job/sample-21",
        "salary": "₱50,000 - ₱70,000 / month",
        "date_posted": "2026-10-07"
    },
    {
        "title": "Senior Data Scientist (Deep Learning & NLP)",
        "company": "Grab Philippines",
        "location": "Makati City / Hybrid",
        "platform": "Glassdoor",
        "tier": 4,
        "job_url": "https://www.glassdoor.com/job/sample-22",
        "salary": "₱130,000 - ₱175,000 / month",
        "date_posted": "2026-10-06"
    }
]

def seed_sample_data(db_path: str = "data/jobs.db") -> int:
    jobs: List[Job] = []
    for item in SAMPLE_DATA:
        title = item["title"]
        job = Job(
            title=title,
            company=item["company"],
            location=item["location"],
            platform=item["platform"],
            tier=item["tier"],
            job_url=item["job_url"],
            salary=item["salary"],
            role_category=classify_role(title),
            experience_level=classify_experience_level(title),
            date_posted=item["date_posted"],
            status="new"
        )
        jobs.append(job)

    added, _ = insert_jobs(db_path, jobs)
    return added
