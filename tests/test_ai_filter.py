import os
import sys
import types
import unittest
from unittest.mock import patch

# The bundled test runtime intentionally has no third-party packages. These
# tests replace network evaluation, so a minimal import stub is sufficient.
if "requests" not in sys.modules:
    sys.modules["requests"] = types.SimpleNamespace(
        exceptions=types.SimpleNamespace(Timeout=TimeoutError),
        post=None,
    )

from utils.ai_filter import AIFilter


class SalaryExtractionTests(unittest.TestCase):
    def make_filter(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            return AIFilter({}, {"enabled": True, "min_suitability_score": 70})

    def test_explicit_salary_is_saved(self):
        ai_filter = self.make_filter()
        ai_filter._evaluate_jobs = lambda jobs: {
            "job-1": {
                "suitability_score": 90,
                "reason": "Good match",
                "salary_found": True,
                "extracted_salary": "USD 70,000-85,000 per year",
            }
        }
        result = ai_filter.filter([{"id": "job-1", "title": "Data Engineer"}])
        self.assertEqual(result[0]["salary"], "USD 70,000-85,000 per year")
        self.assertEqual(result[0]["salary_status"], "listed")

    def test_unverified_salary_is_not_saved(self):
        ai_filter = self.make_filter()
        ai_filter._evaluate_jobs = lambda jobs: {
            "job-1": {
                "suitability_score": 90,
                "reason": "Good match",
                "salary_found": False,
                "extracted_salary": "USD 100,000 per year",
            }
        }
        result = ai_filter.filter([{"id": "job-1", "title": "Data Engineer"}])
        self.assertEqual(result[0]["salary"], "")
        self.assertEqual(result[0]["salary_status"], "not_mentioned")

    def test_missing_ai_response_does_not_discard_job(self):
        ai_filter = self.make_filter()
        ai_filter._evaluate_jobs = lambda jobs: {}
        result = ai_filter.filter([{"id": "job-1", "title": "Data Engineer"}])
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["ai_evaluated"])
        self.assertIsNone(result[0]["suitability_score"])


if __name__ == "__main__":
    unittest.main()
