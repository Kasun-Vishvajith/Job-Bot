import unittest

from utils.filter import JobFilter


PROFILE = {
    "keywords": ["ai engineer", "machine learning", "devops", "data engineer"],
    "exclude_keywords": ["4+ years", "senior", "staff", "principal"],
    "must_have_keywords": ["junior", "graduate", "entry level"],
    "work_types": ["remote", "hybrid", "on-site"],
    "location_rules": {
        "remote_worldwide": True,
        "onsite_allowed_cities": ["sri lanka", "colombo"],
    },
}

FILTERING = {
    "remote_only": True,
    "strict_keyword_filtering": False,
    "enforce_entry_level": True,
    "entry_level_keywords": ["junior", "graduate", "entry level", "early career"],
    "max_years_experience": 3,
    "permanent_only": True,
    "min_keyword_matches": 1,
}


class JobFilterTests(unittest.TestCase):
    def setUp(self):
        self.job_filter = JobFilter(PROFILE, FILTERING)

    def check(self, **overrides):
        job = {
            "title": "Junior AI Engineer",
            "company": "Example",
            "location": "Worldwide Remote",
            "description": "Early career role with 0-3 years of experience.",
            "work_type": "Remote",
            "employment_type": "Full-time",
        }
        job.update(overrides)
        return self.job_filter._check(job)

    def test_accepts_permanent_remote_early_career_role(self):
        accepted, _ = self.check()
        self.assertTrue(accepted)

    def test_accepts_explicit_three_year_requirement(self):
        accepted, _ = self.check(
            title="Data Engineer", description="Remote role requiring 3 years experience."
        )
        self.assertTrue(accepted)

    def test_rejects_internship(self):
        accepted, reason = self.check(
            title="AI Engineer Intern", employment_type="Internship"
        )
        self.assertFalse(accepted)
        self.assertIn("permanent", reason)

    def test_rejects_non_remote_role_outside_sri_lanka(self):
        accepted, _ = self.check(
            location="Berlin, Germany", work_type="On-site", description="Junior data engineer"
        )
        self.assertFalse(accepted)


if __name__ == "__main__":
    unittest.main()
