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

    def test_role_classification(self):
        self.assertEqual(classify_role("Frontend React Developer"), "Web/Software Dev")
        self.assertEqual(classify_role("Data Analyst - SQL/Python"), "Data/AI/ML")
        self.assertEqual(classify_role("Machine Learning Engineer"), "Data/AI/ML")
        self.assertEqual(classify_role("Fullstack Engineer - AI Products"), "Both")

if __name__ == "__main__":
    unittest.main()
