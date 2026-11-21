import unittest
from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity

class TestClassifier(unittest.TestCase):
    def test_technical_titles_with_no_description(self):
        for title in ("Prompt Engineer", "NOC Engineer", "Network Administrator", "SOC Analyst",
                      "Product Support Engineer", "Test Analyst", "AI Agent Builder", "RAG Developer"):
            with self.subTest(title=title):
                self.assertTrue(is_relevant_opportunity(title, location="Philippines"))
                self.assertFalse(is_relevant_opportunity(f"Senior {title}", location="Philippines"))
        self.assertFalse(is_relevant_opportunity("Mechanical Test Analyst", location="Philippines"))
        self.assertEqual(classify_role("Prompt Engineer"), "Data/AI/ML")

    def test_description_entry_eligibility(self):
        for title, description in [
            ("Front-End Developer", "At least 1 year of web development experience, or equivalent project background."),
            ("Software Engineer", "0 - 2 years of experience in software development."),
            ("Developer II", "Fresh graduates are welcome to apply. Python: 3 years (Required)"),
            ("Web Developer", "Fresh graduates with relevant internships are encouraged to apply."),
            ("AI Developer", "Years of Experience: Fresh Graduates / 1-3 years experience."),
            ("Full Stack Developer", "Open to recent graduates with strong projects."),
            ("Web Developer", "1-2 years of web development experience preferred."),
            ("Web Developer", "6 months of development experience required."),
            ("Software Developer", "Graduating students are welcome to apply."),
            ("Software Developer", "College graduates are also welcome to apply. Minimum 3 years of experience."),
            ("Software Developer", "This is an entry-level position on the web team."),
            ("Software Developer", "No previous professional experience is required."),
            ("Software Developer", "Ideal for career starters."),
            ("Software Developer", "Open to first-time job seekers."),
            ("Software Developer", "Relevant academic projects are accepted."),
            ("Software Developer", "Minimum 3 years of experience. Internship experience accepted."),
            ("Software Developer", "Minimum of 3 years of professional software development experience. AI coding tools: 1 year (Preferred)"),
            ("Software Developer", "Job Types: Full-time, Permanent, Fresh graduate"),
            ("Solutions Engineer", "In this early-career role, you will collaborate with our team."),
            ("Software Engineer", "1+ years of experience on large scale distributed systems"),
            ("QA Tester", "SQL: 1 year (Required)"),
            ("Software Engineer II Golang", "Como é ser uma pessoa Software Engineer Júnior:"),
            ("AI Product Engineer", "We hire on AI fluency, judgment, and velocity, not years of experience."),
            ("Database Administrator", "At least 2 years. Freshers are also encouraged to apply."),
            ("Software Developer", "Freshers with relevant technical knowledge are welcome."),
            ("Application Engineer", "Freshers and candidates with 0-2 years of experience are welcome to apply."),
            ("Software Engineer", "Comprehensive training provided for all new hires."),
            ("Web Developer", "Beginners welcome to apply."),
            ("Data Analyst", "0 - 1 year experience required."),
        ]:
            with self.subTest(description=description):
                self.assertEqual(classify_experience_level(title, description), "Junior / Entry")

    def test_description_does_not_confuse_training_with_eligibility(self):
        for description in [
            "Bachelor's degree required. Provide training to junior developers.",
            "One year contract. Mentor graduate developers.",
            "Graduate of Computer Science. 3 years experience required.",
            "Fresh graduates are not welcome to apply.",
        ]:
            with self.subTest(description=description):
                self.assertEqual(classify_experience_level("Software Developer", description), "Mid-Level")

    def test_experience_level_junior(self):
        self.assertEqual(classify_experience_level("Junior Full Stack Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Jr. Software Engineer - Python"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Entry Level Data Analyst"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Associate Web Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Data Science Intern"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Fresh Graduate Web Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Software Engineer I"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Software Quality Assurance Tester I"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Technical Support Analyst I"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Early Career Software Engineer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("OJT Android Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Software Developer Trainee"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Junior / Senior Full Stack Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("0-2 Years Experience Web Developer"), "Junior / Entry")

    def test_experience_level_senior(self):
        for description in ["Requires 7 years of experience. Comprehensive training provided.",
                            "Minimum 5 years of experience. Fresh graduates are welcome to apply."]:
            self.assertEqual(classify_experience_level("Senior Software Engineer", description), "Senior / Lead")
        self.assertEqual(classify_experience_level("Senior Backend Engineer"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Sr AI Engineer"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Lead Data Architect"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Principal Software Engineer"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Engineering Manager"), "Senior / Lead")
        self.assertEqual(classify_experience_level("JR-213105 BI Consultant Senior"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Director, Financial Reporting & Internal Controls"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Contracts Manager - International"), "Senior / Lead")

    def test_false_positive_prevention(self):
        self.assertNotEqual(classify_experience_level("Data Entry Administrator"), "Junior / Entry")

    def test_experience_level_mid(self):
        self.assertEqual(classify_experience_level("Mid-Level React Developer"), "Mid-Level")
        self.assertEqual(classify_experience_level("Intermediate Data Engineer"), "Mid-Level")
        self.assertEqual(classify_experience_level("Operations Engineer II"), "Mid-Level")
        self.assertEqual(classify_experience_level("Information Security Analyst II"), "Mid-Level")
        self.assertEqual(classify_experience_level("Python Developer", "At least 3 years of backend experience."), "Mid-Level")
        self.assertEqual(classify_experience_level("C# Developer", raw_level="Mid-Level"), "Mid-Level")
        self.assertEqual(classify_experience_level("Shopify Developer", salary="PHP 50,000 - PHP 65,000"), "Mid-Level")

    def test_unspecified_when_no_seniority_signals(self):
        for title in ("Python Developer", "C# Developer", "Shopify Developer", "Database Administrator", "Web Developer"):
            self.assertEqual(classify_experience_level(title, allow_skill_fallback=False), "Unspecified")
        self.assertEqual(
            classify_experience_level("Quality Assurance Engineer", "Ensure project deliverables meet quality standards.", allow_skill_fallback=False),
            "Unspecified",
        )
        # Layer 6: Skill-Match Split (Zero Unspecified by default)
        for title in ("C# Developer", "Web Developer", "Quality Assurance Engineer", "React Frontend Developer", "Android Kotlin Developer"):
            self.assertEqual(classify_experience_level(title), "Junior / Entry")
        for title in ("Python Developer", "Shopify Developer", "Database Administrator", "Mulesoft Developer", "Salesforce Developer"):
            self.assertEqual(classify_experience_level(title), "Mid-Level")

    def test_five_layer_seniority_detection(self):
        # Layer 1B: Native API raw_level
        self.assertEqual(classify_experience_level("Software Engineer", raw_level="Entry level"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Web Developer", raw_level="200"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Backend Developer", raw_level="Mid-Weight"), "Mid-Level")
        self.assertEqual(classify_experience_level("Backend Developer", raw_level="Senior"), "Senior / Lead")
        # LinkedIn Mid-Senior level yields to explicit JD years before soft fallback
        self.assertEqual(
            classify_experience_level("Software Engineer", "Minimum 5+ years of production Java.", raw_level="Mid-Senior level"),
            "Senior / Lead",
        )
        self.assertEqual(
            classify_experience_level("Software Engineer", "Build APIs.", raw_level="Mid-Senior level"),
            "Mid-Level",
        )

        # Layer 2: Explicit JD years
        self.assertEqual(
            classify_experience_level("Data Engineer", "Experience Required: 3+ Years in ETL pipelines."),
            "Mid-Level",
        )
        self.assertEqual(
            classify_experience_level("QA Automation Tester", "Minimum 5 years work experience as QA Tester."),
            "Senior / Lead",
        )
        self.assertEqual(
            classify_experience_level("Full Stack Developer", "0-5 years of experience welcome.", allow_skill_fallback=False),
            "Unspecified",
        )
        self.assertEqual(
            classify_experience_level("Full Stack Developer", "0-5 years of experience welcome."),
            "Junior / Entry",
        )

        # Layer 4: Semantic JD responsibility scoring (no years mentioned)
        self.assertEqual(
            classify_experience_level(
                "Software Developer",
                "Assist in developing features under the guidance of senior engineers. Strong fundamentals in OOP and willingness to learn.",
            ),
            "Junior / Entry",
        )
        self.assertEqual(
            classify_experience_level(
                "Software Developer",
                "Seeking an experienced developer to independently design, build, and deploy scalable production-grade APIs end-to-end.",
            ),
            "Mid-Level",
        )
        self.assertEqual(
            classify_experience_level(
                "Full Stack Engineer",
                "Define engineering standards and technical roadmap, lead architectural decisions, and mentor junior and mid-level engineers.",
            ),
            "Senior / Lead",
        )

        # Layer 5: Conservative salary band heuristics
        self.assertEqual(classify_experience_level("QA Analyst", salary="₱25,000 – ₱27,500 per month"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Web Developer", salary="5 USD/hr"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Wordpress Developer", salary="7/hour"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Systems Administrator", salary="PHP 45,000 - PHP 55,000"), "Mid-Level")
        self.assertEqual(classify_experience_level("DevOps Engineer", salary="$135,000 / year"), "Senior / Lead")
        # Do not guess on bare numbers or Freelancer fixed budgets
        self.assertEqual(classify_experience_level("Web Developer", salary="USD 150 fixed", allow_skill_fallback=False), "Unspecified")
        self.assertEqual(classify_experience_level("Software Engineer", salary="130000.0", allow_skill_fallback=False), "Unspecified")
        self.assertEqual(classify_experience_level("Web Developer", salary="USD 150 fixed"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Software Engineer", salary="130000.0"), "Junior / Entry")

        # #6 improvements: Jobgether badges, embedded JD salary, bare PH salaries, expanded JD semantics
        self.assertEqual(
            classify_experience_level("Frontend Developer", "Remote from Asia | Full time | Senior (5-10 years) | React"),
            "Senior / Lead",
        )
        self.assertEqual(
            classify_experience_level("Web Developer", "Remote from PH | Junior (1-2 years) | HTML CSS"),
            "Junior / Entry",
        )
        self.assertEqual(
            classify_experience_level("QA Collector", "Pay: Php15,000.00 - Php18,000.00 per month", salary="15000.0", platform="Indeed"),
            "Junior / Entry",
        )
        self.assertEqual(
            classify_experience_level("Technical SEO Analyst", "Explore site speed.", salary="50000.0", platform="Indeed"),
            "Mid-Level",
        )
        self.assertEqual(
            classify_experience_level(
                "Partnerships Specialist",
                "Compensation: 25,000 PHP base salary + commission.",
                salary="TBD",
                platform="OnlineJobs.ph",
            ),
            "Junior / Entry",
        )
        self.assertEqual(
            classify_experience_level(
                "QA Engineer",
                "You will build the QA practice from the ground up, defining test strategies and release criteria.",
            ),
            "Mid-Level",
        )

    def test_role_classification(self):
        self.assertEqual(classify_role("Frontend React Developer"), "Web/Software Dev")
        self.assertEqual(classify_role("Data Analyst - SQL/Python"), "Data/AI/ML")
        self.assertEqual(classify_role("Machine Learning Engineer"), "Data/AI/ML")
        self.assertEqual(classify_role("Fullstack Engineer - AI Products"), "Both")

    def test_is_relevant_opportunity_matrix(self):
        from src.classifier import is_relevant_opportunity
        # Candidate core match tracks
        self.assertTrue(is_relevant_opportunity("Android Developer"))
        self.assertTrue(is_relevant_opportunity("Kotlin Developer"))
        self.assertTrue(is_relevant_opportunity("Junior Mobile Engineer"))
        self.assertTrue(is_relevant_opportunity("React Frontend Developer"))
        self.assertTrue(is_relevant_opportunity("Node.js Backend Developer"))
        self.assertTrue(is_relevant_opportunity("Full Stack Web Developer"))
        self.assertTrue(is_relevant_opportunity("PHP / MySQL Developer"))
        self.assertTrue(is_relevant_opportunity("QA Automation Engineer"))
        self.assertTrue(is_relevant_opportunity("Junior Software Engineer"))

        # Rejection of Senior / Lead / Architect / Principal
        self.assertFalse(is_relevant_opportunity("Senior Backend Engineer"))
        self.assertFalse(is_relevant_opportunity("Lead Mobile Architect"))
        self.assertFalse(is_relevant_opportunity("Principal Software Engineer"))
        self.assertFalse(is_relevant_opportunity("Engineering Director"))

        # Rejection of Non-Tech
        self.assertFalse(is_relevant_opportunity("Registered Nurse"))
        self.assertFalse(is_relevant_opportunity("Chief Accountant"))
        self.assertFalse(is_relevant_opportunity("Medical Biller"))
        self.assertFalse(is_relevant_opportunity("Cashier"))

        # VA matrix: only entry or training allowed
        self.assertTrue(is_relevant_opportunity("Virtual Assistant (Paid Training)"))
        self.assertTrue(is_relevant_opportunity("Entry Level Virtual Assistant"))
        self.assertTrue(is_relevant_opportunity("Cyberbacker - Virtual Assistant (Training Provided)"))
        self.assertFalse(is_relevant_opportunity("Executive Assistant (5 years exp required)"))
        self.assertFalse(is_relevant_opportunity("Senior Real Estate Virtual Assistant"))

    def test_is_within_14_days(self):
        from datetime import datetime, timezone, timedelta
        from src.models import is_within_14_days

        ref = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
        # Today
        self.assertTrue(is_within_14_days("2026-10-16", ref_date=ref))
        self.assertTrue(is_within_14_days("today", ref_date=ref))
        # 14 days ago (2026-10-02)
        self.assertTrue(is_within_14_days("2026-10-02", ref_date=ref))
        # 15 days ago (2026-10-01) -> Out
        self.assertFalse(is_within_14_days("2026-10-01", ref_date=ref))
        # 30 days ago -> Out
        self.assertFalse(is_within_14_days("2026-09-16", ref_date=ref))
        # Years ago -> Out
        self.assertFalse(is_within_14_days("2021-05-12", ref_date=ref))
        self.assertFalse(is_within_14_days("2019-02-28", ref_date=ref))
        # Timezone buffer (+1 day)
        self.assertTrue(is_within_14_days("2026-10-17", ref_date=ref))
        # Future beyond +1 day -> Out
        self.assertFalse(is_within_14_days("2026-10-25", ref_date=ref))
        # Empty/missing -> Out
        self.assertFalse(is_within_14_days("", ref_date=ref))
        self.assertFalse(is_within_14_days(None, ref_date=ref))

    def test_title_normalization_and_extended_patterns(self):
        self.assertEqual(
            classify_experience_level("GDS Consulting_Digital Engineering_Senior Full Stack DotNet-React Developer"),
            "Senior / Lead",
        )
        self.assertEqual(classify_experience_level("Quality Assurance Team Leader"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Executive Vice President, Testing Segment"), "Senior / Lead")
        self.assertEqual(classify_experience_level("QA Engineer - Level II"), "Mid-Level")
        self.assertEqual(classify_experience_level("Software Engineer Level III-ServiceNow Developer"), "Mid-Level")
        self.assertEqual(classify_experience_level("DevSecOps Engineer (Mid)"), "Mid-Level")
        self.assertEqual(classify_experience_level("Cybersecurity Assessor III"), "Mid-Level")

    def test_platform_salary_heuristics_and_junk_rejection(self):
        self.assertEqual(classify_experience_level("Software Engineer", salary="115000.0", platform="Glassdoor"), "Mid-Level")
        self.assertEqual(classify_experience_level("Software Engineer", salary="183997.0", platform="Glassdoor"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Software Engineer", salary="53.28", platform="Glassdoor"), "Senior / Lead")

        self.assertEqual(classify_experience_level("Software Engineer", salary="$30,000 - $35,000", platform="Himalayas"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Software Engineer", salary="$55,000 - $65,000", platform="Himalayas"), "Mid-Level")
        self.assertEqual(classify_experience_level("Software Engineer", salary="$120,000 - $130,000", platform="Himalayas"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Software Engineer", salary="$1,500 - $1,800", platform="Himalayas"), "Mid-Level")

        self.assertEqual(classify_experience_level("Web Developer", salary="49,000 per Month", platform="OnlineJobs.ph"), "Mid-Level")
        self.assertEqual(classify_experience_level("Web Developer", salary="500", platform="OnlineJobs.ph"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Web Developer", salary="$800-1000", platform="OnlineJobs.ph"), "Junior / Entry")

        self.assertEqual(classify_experience_level("Software Engineer", salary="₱70,000 – ₱90,000 per month", platform="JobStreet"), "Mid-Level")
        self.assertEqual(classify_experience_level("Software Engineer", salary="₱95,000 – ₱99,000 per month", platform="JobStreet"), "Senior / Lead")
        self.assertEqual(classify_experience_level("Software Engineer", salary="₱180 – ₱220 per hour", platform="JobStreet"), "Junior / Entry")

        self.assertEqual(classify_experience_level("Software Engineer", salary="＄2.2K-2.8K", platform="Bossjob"), "Mid-Level")
        self.assertEqual(classify_experience_level("Software Engineer", salary="$6 - $65", platform="Himalayas", allow_skill_fallback=False), "Unspecified")
        self.assertEqual(classify_experience_level("Software Engineer", salary="$6 - $65", platform="Himalayas"), "Junior / Entry")

if __name__ == "__main__":
    unittest.main()
