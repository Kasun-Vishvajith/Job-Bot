import tempfile
import unittest
from pathlib import Path

from utils.database import JobDatabase


def job(**overrides):
    value = {
        "id": "source-id-1",
        "title": "Junior Data Engineer",
        "company": "Example Labs",
        "location": "Colombo, Sri Lanka",
        "salary": "LKR 200,000 / month",
        "link": "https://example.com/jobs/123?source=board",
        "description": "Apply by 30 September 2026.",
        "work_type": "Hybrid",
        "employment_type": "Full-time",
        "source": "Board A",
    }
    value.update(overrides)
    return value


class DatabaseDuplicateGateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = JobDatabase(Path(self.temp_dir.name) / "seen_jobs.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_unchanged_repeat_is_rejected(self):
        first = self.db.get_new_jobs([job()])
        self.db.save_jobs(first)
        self.assertEqual(self.db.get_new_jobs([job()]), [])
        self.assertEqual(self.db.last_dedupe_stats["unchanged"], 1)

    def test_same_role_from_another_source_is_rejected(self):
        first = self.db.get_new_jobs([job()])
        self.db.save_jobs(first)
        duplicate = job(
            id="different-source-id",
            source="Board B",
            link="https://another.example/jobs/abc",
        )
        self.assertEqual(self.db.get_new_jobs([duplicate]), [])

    def test_salary_change_creates_marked_update(self):
        first = self.db.get_new_jobs([job()])
        self.db.save_jobs(first)
        updates = self.db.get_new_jobs([job(salary="LKR 250,000 / month")])
        self.assertEqual(len(updates), 1)
        self.assertTrue(updates[0]["is_updated"])
        self.assertIn("salary", updates[0]["changed_fields"])
        self.assertNotEqual(updates[0]["id"], "source-id-1")

    def test_position_change_on_same_url_creates_update(self):
        first = self.db.get_new_jobs([job()])
        self.db.save_jobs(first)
        updates = self.db.get_new_jobs([job(title="Associate Data Engineer")])
        self.assertEqual(len(updates), 1)
        self.assertIn("title", updates[0]["changed_fields"])

    def test_tracking_query_parameters_do_not_create_duplicate(self):
        first = self.db.get_new_jobs([job()])
        self.db.save_jobs(first)
        duplicate = job(
            id="new-id",
            link="https://example.com/jobs/123?utm_campaign=daily",
        )
        self.assertEqual(self.db.get_new_jobs([duplicate]), [])

    def test_same_run_cross_source_records_are_merged_once(self):
        sparse = job(salary="")
        richer = job(
            id="other-board-id",
            source="Board B",
            link="https://another.example/jobs/abc",
        )
        candidates = self.db.get_new_jobs([sparse, richer])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["salary"], "LKR 200,000 / month")

    def test_legacy_unverified_ai_rejection_is_reconsidered(self):
        rejected = job()
        self.db.data["ignored_jobs"] = {
            rejected["id"]: {
                "title": rejected["title"],
                "company": rejected["company"],
                "link": rejected["link"],
                "seen_at": "2026-09-09T00:00:00",
            }
        }
        candidates = self.db.get_new_jobs([rejected])
        self.assertEqual(len(candidates), 1)
        self.assertFalse(candidates[0]["is_updated"])


if __name__ == "__main__":
    unittest.main()
