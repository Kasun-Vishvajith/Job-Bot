import sys
import types
import unittest
from urllib.parse import quote


if "requests" not in sys.modules:
    sys.modules["requests"] = types.SimpleNamespace(
        utils=types.SimpleNamespace(quote=quote),
        get=None,
    )

if "bs4" not in sys.modules:
    class _Text:
        def __init__(self, value, *_args, **_kwargs):
            self.value = value or ""

        def get_text(self, *_args, **_kwargs):
            return self.value

    module = types.ModuleType("bs4")
    module.BeautifulSoup = _Text
    sys.modules["bs4"] = module

from scrapers.remote_scraper import RemoteJobBoardScraper


class AshbyScraperTests(unittest.TestCase):
    def test_reads_structured_job_and_salary(self):
        scraper = RemoteJobBoardScraper({
            "match_keywords": ["data engineer"],
            "max_results_per_source": 20,
        })
        scraper._get_json = lambda _url: {"jobs": [{
            "title": "Junior Data Engineer",
            "location": "Remote - Worldwide",
            "descriptionPlain": "Entry-level data engineer role",
            "jobUrl": "https://jobs.ashbyhq.com/example/123",
            "publishedAt": "2026-09-10T00:00:00Z",
            "employmentType": "FullTime",
            "isRemote": True,
            "compensation": {
                "scrapeableCompensationSalarySummary": "USD 60,000 - 75,000"
            },
        }]}

        jobs = scraper._scrape_ashby({
            "name": "Ashby",
            "companies": ["example-company"],
        })

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Example Company")
        self.assertEqual(jobs[0]["salary"], "USD 60,000 - 75,000")
        self.assertEqual(jobs[0]["work_type"], "Remote")

    def test_ignores_unrelated_roles(self):
        scraper = RemoteJobBoardScraper({"match_keywords": ["data engineer"]})
        scraper._get_json = lambda _url: {"jobs": [{
            "title": "Account Executive",
            "location": "Remote",
            "descriptionPlain": "Sales role",
            "jobUrl": "https://jobs.ashbyhq.com/example/456",
        }]}

        jobs = scraper._scrape_ashby({"name": "Ashby", "companies": ["example"]})
        self.assertEqual(jobs, [])


if __name__ == "__main__":
    unittest.main()
