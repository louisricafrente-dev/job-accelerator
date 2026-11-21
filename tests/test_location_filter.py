import unittest
from unittest.mock import MagicMock, patch
from src.classifier import is_work_authorized_location, is_relevant_opportunity
from src.models import Job
from src.database import init_db, insert_jobs, get_jobs
import os
import tempfile
import sqlite3

class TestLocationFilter(unittest.TestCase):
    def test_philippine_locations_allowed(self):
        # Major PH cities and regions
        self.assertTrue(is_work_authorized_location("Manila City, Metro Manila", "Junior Web Developer", "JobStreet"))
        self.assertTrue(is_work_authorized_location("Makati, P00, Philippines", "Junior Data Engineer", "Indeed"))
        self.assertTrue(is_work_authorized_location("Taguig, National Capital Region, Philippines", "Salesforce Developer", "LinkedIn"))
        self.assertTrue(is_work_authorized_location("Bonifacio Global City, Metro Manila", "Junior QA Engineer", "JobStreet"))
        self.assertTrue(is_work_authorized_location("Cebu City, Cebu", "Frontend Developer", "Bossjob"))
        self.assertTrue(is_work_authorized_location("Davao City", "Junior Android Developer", "Kalibrr"))
        self.assertTrue(is_work_authorized_location("Mariveles, Bataan", "Application Support Engineer", "JobStreet"))
        self.assertTrue(is_work_authorized_location("Clark, Pampanga", "Junior Cloud Engineer", "Indeed"))
        self.assertTrue(is_work_authorized_location("Bacoor, Cavite", "Web Developer Intern", "Indeed"))
        self.assertTrue(is_work_authorized_location("Santa Rosa, Laguna", "Software Developer Trainee", "Indeed"))
        self.assertTrue(is_work_authorized_location("Subic Bay Freeport Zone, P03, Philippines", "Junior Engineer", "Indeed"))

    def test_remote_locations_allowed(self):
        # Global remote and WFH keywords
        self.assertTrue(is_work_authorized_location("Remote Worldwide", "Full Stack Developer", "Himalayas"))
        self.assertTrue(is_work_authorized_location("Remote", "Software Engineer", "We Work Remotely"))
        self.assertTrue(is_work_authorized_location("Remote / Contract", "Software Engineer in Network Infrastructure", "Upwork"))
        self.assertTrue(is_work_authorized_location("Work from home", "Python Developer", "Indeed"))
        self.assertTrue(is_work_authorized_location("Telecommute", "React Developer", "LinkedIn"))
        self.assertTrue(is_work_authorized_location("", "Junior Software Engineer (Remote)", "LinkedIn"))
        self.assertTrue(is_work_authorized_location("Anywhere", "Mobile Engineer", "Remote OK"))
        self.assertTrue(is_work_authorized_location("Remoto", "Software Engineer II Golang", "Remote OK"))

    def test_dedicated_remote_platforms_allowed(self):
        self.assertFalse(is_work_authorized_location("Vancouver", "Associate Data Scientist", "Remote OK"))
        self.assertFalse(is_work_authorized_location("Cincinnati", "Software Deployment Engineer", "Remote OK"))
        self.assertTrue(is_work_authorized_location("", "Software Engineer", "We Work Remotely"))

    def test_foreign_onsite_rejected(self):
        # India onsite
        self.assertFalse(is_work_authorized_location("Palampur, India", "Junior Software Developer", "Naukri"))
        self.assertFalse(is_work_authorized_location("Mumbai, India", "Web Developer Associate", "Naukri"))
        self.assertFalse(is_work_authorized_location("Pune, India", "Backend Engineer Junior", "Naukri"))
        self.assertFalse(is_work_authorized_location("Kochi, India", "Associate Engineer", "Naukri"))
        self.assertFalse(is_work_authorized_location("Hyderabad, Chennai, Bengaluru, India", "Software Engineer", "Naukri"))
        self.assertFalse(is_work_authorized_location("Mumbai, Delhi / NCR, India", "Data Analyst Intern", "Naukri"))
        self.assertFalse(is_work_authorized_location("New Delhi(Nehru Place), India", "Coding Intern", "Naukri"))
        self.assertFalse(is_work_authorized_location("Noida, India", "Junior .PHP Developer", "Naukri"))
        self.assertFalse(is_work_authorized_location("Bengaluru, India", "Apprentice - Apps DBA", "Naukri"))

        # Bangladesh onsite
        self.assertFalse(is_work_authorized_location("Dhaka, Bangladesh", "Software Test Intern", "BDJobs"))
        self.assertFalse(is_work_authorized_location("GULSHAN 1, Bangladesh", "AI Trainer - Intern", "BDJobs"))
        self.assertFalse(is_work_authorized_location("Uttara Sector 3, Bangladesh", "Intern", "BDJobs"))
        self.assertFalse(is_work_authorized_location("Bangladesh", "Junior Web Developer", "BDJobs"))

        # Other foreign onsite
        self.assertFalse(is_work_authorized_location("Dubai, UAE", "Junior Developer", "Bayt"))
        self.assertFalse(is_work_authorized_location("Paris, France", "Développeur Web Junior", "HelloWork"))
        self.assertFalse(is_work_authorized_location("Tokyo, Japan", "Software Engineer", "LinkedIn"))
        self.assertFalse(is_work_authorized_location("Sydney, Australia", "Junior Java Developer", "Indeed"))

    def test_foreign_board_remote_allowed(self):
        # Remote does not override a foreign hiring location.
        self.assertFalse(is_work_authorized_location("Remote, India", "Python Developer", "Naukri"))
        self.assertFalse(is_work_authorized_location("India", "Python Developer (Remote)", "Naukri"))
        self.assertFalse(is_work_authorized_location("Bangladesh", "Full Stack Developer (WFH / Remote)", "BDJobs"))

    def test_remote_country_restrictions_override_board_and_remote_labels(self):
        for location, platform, description in [
            ("United States (Remote)", "LinkedIn", ""),
            ("Poland", "Jobicy", ""),
            ("Remote Worldwide", "Remotive", "Remote within Poland only."),
            ("Remote", "Upwork", "x " * 300 + "Applicants must reside in the United States."),
            ("Remote", "Glassdoor", "You must be authorized to work in the US."),
            ("Remote - Europe", "Himalayas", ""),
            ("Sweden (Remote)", "Remote OK", ""),
            ("San Francisco Bay Area, Los Angeles", "Greenhouse", ""),
            ("San Mateo (Remote)", "Ashby", ""),
            ("Santa Rosa, CA", "Ashby", ""),
            ("Remote, AMER", "Ashby", ""),
            ("Ukraine Anywhere", "Greenhouse", ""),
            ("Mumbai, Delhi / NCR, India", "LinkedIn", ""),
            ("Singapore", "Greenhouse", ""),
            ("Remote (Worldwide)", "Web3.career", "Location: London/Hybrid."),
            ("Remote (Worldwide)", "Web3.career", "Location: New York, NY (Hybrid)."),
        ]:
            with self.subTest(location=location, description=description):
                self.assertFalse(is_work_authorized_location(location, "Developer", platform, description))
        for location, title, platform, description in [
            ("Remote (Worldwide)", "Software Engineer - RUST (London based)", "Web3.career", "Location: London/Hybrid."),
            ("Remote (Worldwide)", "Software Engineer (Golang) - London", "Web3.career", ""),
            ("Remote (Worldwide)", "Incident Operations Commander - EMEA", "Web3.career", ""),
            ("Remote Worldwide", "[Remote] [Europe] - Python-based jobs across Europe", "Reddit", ""),
            ("Remote Worldwide", "[Remote] [US] - AI, full stack, and software engineers", "Reddit", ""),
            ("Remote", "Cloud Software Engineer (TS/SCI w/ Poly)", "VueJobs", ""),
            ("Remote", "Profissional Fullstack (.NET+Vue) Sênior - Remoto", "VueJobs", ""),
            ("Remote Worldwide", "Java 开发工程师", "Bossjob", ""),
            ("Remote (Global)", "Quality Assurance Rater - Spanish speakers in Spain", "Working Nomads", ""),
            ("Remote (Global)", "Quality Assurance Rater - German speakers in Germany", "Working Nomads", ""),
        ]:
            with self.subTest(title=title):
                self.assertFalse(is_work_authorized_location(location, title, platform, description))
        for location, title, platform in [
            ("Remote (Worldwide)", "Web Developer (US Client)", "OnlineJobs.ph"),
            ("Manila, Philippines", "Software Engineer - US Shift", "JobStreet"),
            ("Remote Worldwide", "Freelance Shopify Developer for 5-SKU Menswear Store (Qatar/GCC Gateway)", "Reddit"),
        ]:
            with self.subTest(allowed_title=title):
                self.assertTrue(is_work_authorized_location(location, title, platform))
        for location, platform in [
            ("Philippines (Remote)", "LinkedIn"),
            ("Angeles, Pampanga", "JobStreet"),
            ("San Mateo, Rizal", "Indeed"),
            ("Santa Rosa, Laguna", "Indeed"),
            ("Manila, Philippines", "Greenhouse"),
            ("Indonesia; Malaysia; Philippines; Singapore; Taiwan", "Greenhouse"),
            ("Bangkok, Thailand; India; Jakarta, Indonesia; Kuala Lumpur, Malaysia; Manila, Philippines", "Greenhouse"),
            ("Singapore; Philippines", "LinkedIn"),
            ("Remote, Global", "Ashby"),
            ("APAC - Remote", "Greenhouse"),
            ("Global", "Greenhouse"),
            ("APAC", "Ashby"),
        ]:
            with self.subTest(allowed_location=location):
                self.assertTrue(is_work_authorized_location(location, "Developer", platform))
        self.assertTrue(is_work_authorized_location("Remote Worldwide", "Developer", "Remotive", "Our clients are in the US."))

    def test_database_insert_skips_foreign_onsite(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_db = tmp.name
        try:
            init_db(tmp_db)
            jobs_to_insert = [
                Job(
                    title="Junior Web Developer",
                    company="PH Company Inc",
                    location="Makati, Philippines",
                    platform="JobStreet",
                    tier=1,
                    job_url="https://example.com/ph-job",
                    date_posted="2026-10-21"
                ),
                Job(
                    title="Junior Software Developer",
                    company="Datanimics Technologies",
                    location="Palampur, India",
                    platform="Naukri",
                    tier=2,
                    job_url="https://example.com/india-job",
                    date_posted="2026-10-21"
                ),
                Job(
                    title="Software Test Intern",
                    company="Samsung R&D",
                    location="Dhaka, Bangladesh",
                    platform="BDJobs",
                    tier=2,
                    job_url="https://example.com/bd-job",
                    date_posted="2026-10-21"
                ),
                Job(
                    title="Remote Software Engineer",
                    company="Global Tech",
                    location="Remote Worldwide",
                    platform="Himalayas",
                    tier=3,
                    job_url="https://example.com/remote-job",
                    date_posted="2026-10-21"
                )
            ]

            added, skipped = insert_jobs(tmp_db, jobs_to_insert)
            self.assertEqual(added, 2, "Only 2 valid jobs (PH and Remote) should be added")
            self.assertEqual(skipped, 2, "2 foreign onsite jobs should be skipped")

            inserted = get_jobs(tmp_db)
            titles = [j["title"] for j in inserted]
            self.assertIn("Junior Web Developer", titles)
            self.assertIn("Remote Software Engineer", titles)
            self.assertNotIn("Junior Software Developer", titles)
            self.assertNotIn("Software Test Intern", titles)
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

if __name__ == "__main__":
    unittest.main()
