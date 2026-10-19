import unittest
from src.classifier import classify_experience_level, classify_role

class TestClassifier(unittest.TestCase):
    def test_experience_level_junior(self):
        self.assertEqual(classify_experience_level("Junior Full Stack Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Jr. Software Engineer - Python"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Entry Level Data Analyst"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Associate Web Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Data Science Intern"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Fresh Graduate Web Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Software Engineer I"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Early Career Software Engineer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("OJT Android Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Software Developer Trainee"), "Junior / Entry")
        self.assertEqual(classify_experience_level("Junior / Senior Full Stack Developer"), "Junior / Entry")
        self.assertEqual(classify_experience_level("0-2 Years Experience Web Developer"), "Junior / Entry")

    def test_experience_level_senior(self):
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
        self.assertEqual(classify_experience_level("Python Developer"), "Mid-Level")
        self.assertEqual(classify_experience_level("C# Developer"), "Mid-Level")
        self.assertEqual(classify_experience_level("Operations Engineer II"), "Mid-Level")
        self.assertEqual(classify_experience_level("Shopify Developer"), "Mid-Level")
        self.assertEqual(classify_experience_level("Database Administrator"), "Mid-Level")

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

if __name__ == "__main__":
    unittest.main()
